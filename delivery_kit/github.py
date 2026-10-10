"""Trusted metadata transport. Never pass this environment to a model role."""

import hashlib
import json
import os
import re
import subprocess
import time

from .config import Config


class GitHub:
    def __init__(self, config: Config, deadline: float | None = None):
        self.config = config
        self.deadline = deadline

    def command(self, *args: str, cwd=None) -> str:
        seconds = self.config.section('runtime')['command_seconds']
        if self.deadline is not None:
            seconds = min(seconds, self.deadline - time.monotonic())
        if seconds <= 0:
            raise TimeoutError('pass budget exhausted')
        env = dict(os.environ, GH_PROMPT_DISABLED='1', GIT_TERMINAL_PROMPT='0')
        result = subprocess.run(args, cwd=cwd or self.config.checkout, env=env,
                                capture_output=True, text=True, timeout=seconds)
        if result.returncode:
            raise RuntimeError(f'{args[0]} {args[1]} failed ({result.returncode})')
        return result.stdout.strip()

    def json(self, *args: str):
        return json.loads(self.command(*args))

    def pages(self, endpoint: str) -> list[dict]:
        pages = self.json('gh', 'api', endpoint, '--paginate', '--slurp')
        if not isinstance(pages, list) or not all(isinstance(page, list) for page in pages):
            raise RuntimeError('incomplete paginated metadata')
        values = [item for page in pages for item in page]
        if len(values) >= self.config.section('queue')['max_items']:
            raise RuntimeError('metadata snapshot limit reached')
        if not all(isinstance(item, dict) for item in values):
            raise RuntimeError('invalid metadata rows')
        return values

    def issue(self, number: int) -> dict:
        issue = self.json('gh', 'api', f'repos/{self.config.repo}/issues/{number}')
        if issue.get('number') != number or not all(
                isinstance(issue.get(key), str) for key in ('title', 'body', 'updated_at', 'state')):
            raise RuntimeError('incomplete issue metadata')
        return issue

    def blockers(self, number: int) -> list[dict]:
        return self.pages(f'repos/{self.config.repo}/issues/{number}/dependencies/blocked_by?per_page=100')

    def project_rows(self) -> dict[int, dict]:
        project = self.config.section('project')
        if project['number'] == 0:
            return {}
        limit = self.config.section('queue')['max_items']
        definition = self.json('gh', 'project', 'field-list', str(project['number']),
                               '--owner', project['owner'], '--format', 'json', '--limit', str(limit))
        fields = definition.get('fields')
        if (not isinstance(fields, list) or len(fields) >= limit
                or definition.get('totalCount') != len(fields)):
            raise RuntimeError('Project field snapshot incomplete')
        options = {}
        for name, required in (
                (project['status_field'], set(project['ready_options'])),
                (project['dispatch_field'], {project['deferred_option']})):
            matches = [field for field in fields if field.get('name') == name]
            if len(matches) != 1 or not isinstance(matches[0].get('options'), list):
                raise RuntimeError('Project configured field unavailable or misconfigured')
            values = matches[0]['options']
            if not all(isinstance(value, dict) and isinstance(value.get('name'), str)
                       for value in values):
                raise RuntimeError('Project field options unavailable')
            options[name] = {value['name'] for value in values}
            if not required <= options[name] or len(options[name]) != len(values):
                raise RuntimeError('Project configured field options misconfigured')
        result = self.json('gh', 'project', 'item-list', str(project['number']),
                           '--owner', project['owner'], '--format', 'json', '--limit', str(limit))
        rows = result.get('items')
        if not isinstance(rows, list) or len(rows) >= limit or result.get('totalCount') != len(rows):
            raise RuntimeError('Project snapshot incomplete')
        matches = {}
        for row in rows:
            content = row.get('content', {})
            if content.get('repository') != self.config.repo or content.get('type') != 'Issue':
                continue
            number = content.get('number')
            if type(number) is not int or number in matches:
                raise RuntimeError('Project membership ambiguous')
            status_key = project['status_field'][:1].lower() + project['status_field'][1:]
            dispatch_key = project['dispatch_field'][:1].lower() + project['dispatch_field'][1:]
            status = row.get(status_key)
            dispatch = row.get(dispatch_key)
            if not isinstance(status, str) or status not in options[project['status_field']]:
                raise RuntimeError('Project status unavailable')
            if dispatch is not None and dispatch not in options[project['dispatch_field']]:
                raise RuntimeError('Project dispatch value unavailable')
            matches[number] = {'status': status, 'dispatch': dispatch}
        return matches

    def pr(self, number: int) -> dict:
        return self.json('gh', 'pr', 'view', str(number), '--repo', self.config.repo,
                         '--json', 'number,state,isDraft,headRefName,baseRefName,headRefOid,baseRefOid,title,body,closingIssuesReferences,mergeCommit')


def fingerprint(issue: dict) -> str:
    labels = sorted(label['name'] for label in issue['labels'])
    return hashlib.sha256(json.dumps([issue['title'], issue['body'], labels],
                                    sort_keys=True).encode()).hexdigest()


def eligible(config: Config, issue: dict, blockers: list[dict], project_rows: dict) -> bool:
    queue = config.section('queue')
    if issue.get('state') != 'open' or 'pull_request' in issue:
        return False
    labels = issue.get('labels')
    if not isinstance(labels, list) or not all(isinstance(label, dict) and
                                              isinstance(label.get('name'), str) for label in labels):
        raise RuntimeError('incomplete labels')
    names = {label['name'] for label in labels}
    if queue['opt_in_label'] not in names or names.intersection(queue['hold_labels']):
        return False
    for prefix, allowed in ((queue['type_prefix'], queue['allowed_types']),
                            (queue['priority_prefix'], queue['priorities']),
                            (queue['track_prefix'], queue['tracks'])):
        values = [name for name in names if name.startswith(prefix)]
        if len(values) != 1 or values[0] not in allowed:
            return False
    if not any(name.startswith(queue['surface_prefix']) for name in names):
        return False
    for blocker in blockers:
        if type(blocker.get('number')) is not int or blocker.get('state') not in {'open', 'closed'}:
            raise RuntimeError('incomplete prerequisite metadata')
        if blocker['state'] != 'closed' or blocker.get('state_reason') != 'completed':
            return False
    if config.section('project')['number']:
        row = project_rows.get(issue['number'])
        if row is None:
            return False
        if row['status'] not in config.section('project')['ready_options']:
            return False
        if row['dispatch'] == config.section('project')['deferred_option']:
            return False
    return True


def select(config: Config, github: GitHub, claimed: set[int]) -> dict | None:
    issues = github.pages(f'repos/{config.repo}/issues?state=open&per_page=100')
    pulls = github.pages(f'repos/{config.repo}/pulls?state=open&per_page=100')
    branches = github.pages(f'repos/{config.repo}/branches?per_page=100')
    project_rows = github.project_rows()
    local = github.command('git', 'for-each-ref', '--format=%(refname:short)', 'refs/heads').splitlines()
    local += github.command('git', 'worktree', 'list', '--porcelain').splitlines()
    local += [row.get('name', '') for row in branches]
    queue = config.section('queue')
    candidates = []
    for issue in issues:
        number = issue.get('number')
        if type(number) is not int or number <= 0:
            raise RuntimeError('invalid issue number')
        if number in claimed or 'pull_request' in issue:
            continue
        owned_prefix = config.section('repository')['branch_template'].split('{slug}')[0].format(number=number)
        numeric_component = re.compile(rf'(?:^|[/-]){number}(?:[/-]|$)')
        if any(name.startswith(owned_prefix) or numeric_component.search(name) for name in local):
            continue
        declared = re.compile(rf'\b(?:refs|part\s+of|close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s*#{number}\b', re.I)
        if any(declared.search(pr.get('body') or '') or numeric_component.search(pr.get('head', {}).get('ref', ''))
               for pr in pulls):
            continue
        if eligible(config, issue, github.blockers(number), project_rows):
            labels = {label['name'] for label in issue['labels']}
            priority = next(index for index, value in enumerate(queue['priorities']) if value in labels)
            candidates.append((priority, number, issue))
    return min(candidates, default=(None, None, None), key=lambda row: row[:2])[2]
