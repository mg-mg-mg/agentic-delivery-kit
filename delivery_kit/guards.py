"""Review staged changes and fixed-SHA evidence without trusting model claims."""

import fnmatch
import re

CLOSING = re.compile(r'\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s*(?:[\w.-]+/[\w.-]+)?#\d+', re.I)


def staged(config, github, worktree):
    github.command('git', 'diff', '--cached', '--check', cwd=worktree)
    paths = github.command('git', 'diff', '--cached', '--name-only', '-z', cwd=worktree).split('\0')
    paths = [path for path in paths if path]
    if not paths or len(paths) > config.section('runtime')['max_changed_files']:
        raise RuntimeError('empty or oversized staged change')
    for path in paths:
        if any(fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(path.rsplit('/', 1)[-1], pattern)
               for pattern in config.section('guards')['forbidden_paths']):
            raise RuntimeError('staged path forbidden by publication guard')
        item = worktree / path
        if item.is_symlink():
            raise RuntimeError('new or changed symbolic links require manual review')
    return paths


def review_evidence(review: dict, head: str, base: str) -> list[list[str]]:
    checks = review.get('checks')
    if (review.get('head') != head or review.get('base') != base or review.get('verdict') != 'accepted'
            or review.get('findings') != [] or review.get('remaining') != []):
        raise RuntimeError('independent review rejected or incomplete')
    if not isinstance(checks, list) or not 1 <= len(checks) <= 12:
        raise RuntimeError('independent check list missing')
    if not all(isinstance(argv, list) and argv and all(isinstance(arg, str) and arg for arg in argv)
               for argv in checks):
        raise RuntimeError('check commands must be nonempty argv lists')
    return checks


def verification_evidence(result: dict, head: str, base: str, checks: list[list[str]]):
    expected = [{'argv': argv, 'exit_code': 0} for argv in checks]
    if result.get('head') != head or result.get('base') != base or result.get('checks') != expected:
        raise RuntimeError('independent verification missing, failed or mismatched')


def remote_gate(config, pr: dict, head: str, base: str):
    if (pr.get('state') != 'OPEN' or pr.get('isDraft') is not False
            or pr.get('headRefOid') != head or pr.get('baseRefOid') != base
            or pr.get('baseRefName') != config.section('repository')['base_branch']
            or pr.get('closingIssuesReferences') != []):
        raise RuntimeError('remote PR changed or could prematurely close work')
    if CLOSING.search(pr.get('title', '')) or CLOSING.search(pr.get('body', '')):
        raise RuntimeError('automatic issue closing forbidden')
