"""Review staged changes and fixed-SHA evidence without trusting model claims."""

import fnmatch
from pathlib import Path
import re
import subprocess

CLOSING = re.compile(r'\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s*(?:[\w.-]+/[\w.-]+)?#\d+', re.I)


def check_paths(config, paths, worktree):
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


def staged(config, github, worktree):
    github.command('git', 'diff', '--cached', '--check', cwd=worktree)
    paths = github.command('git', 'diff', '--cached', '--name-only', '-z', cwd=worktree).split('\0')
    return check_paths(config, paths, worktree)


def publication(config, github, worktree, base: str, head: str):
    github.command('git', 'merge-base', '--is-ancestor', base, head, cwd=worktree)
    commits = github.command('git', 'rev-list', f'{base}..{head}', cwd=worktree).splitlines()
    if not commits or len(commits) > config.section('runtime')['max_commits']:
        raise RuntimeError('empty or oversized publication history')
    paths = set()
    for commit in commits:
        changes = github.command('git', 'diff-tree', '--root', '-m', '-r', '--no-commit-id',
                                 '--no-renames', '-z', commit, cwd=worktree).split('\0')
        for index in range(0, len(changes) - 1, 2):
            header, path = changes[index:index + 2]
            modes = header.removeprefix(':').split()[:2]
            if '120000' in modes:
                raise RuntimeError('new or changed historical symbolic links require manual review')
            paths.add(path)
    check_paths(config, sorted(paths), worktree)
    github.command('git', 'diff', '--check', f'{base}..{head}', cwd=worktree)
    if CLOSING.search(github.command('git', 'log', '--format=%B', f'{base}..{head}', cwd=worktree)):
        raise RuntimeError('publication commits could prematurely close work')


def safe_git_metadata(config, worktree):
    allowed = re.compile(
        r'^(?:core\.(?:repositoryformatversion|filemode|bare|logallrefupdates|ignorecase|'
        r'precomposeunicode|worktree)|extensions\.(?:worktreeconfig|objectformat|refstorage)|'
        r'user\.(?:name|email)|remote\.origin\.(?:url|fetch)|branch\..+\.(?:remote|merge))$'
    )
    common = Path(subprocess.run(
        ['git', '-C', str(worktree), 'rev-parse', '--path-format=absolute', '--git-common-dir'],
        capture_output=True, text=True, check=True,
        timeout=config.section('runtime')['command_seconds'],
    ).stdout.strip()).resolve()
    files = [common / 'config', common / 'config.worktree',
             *sorted((common / 'worktrees').glob('*/config.worktree'))]
    if len(files) > config.section('queue')['max_items']:
        raise RuntimeError('Git metadata snapshot limit reached')
    for path in files:
        if path.is_symlink():
            raise RuntimeError('Git configuration symlink requires manual inspection')
        if not path.exists():
            continue
        result = subprocess.run(['git', 'config', '--file', str(path), '--null', '--list'],
                                capture_output=True, text=True, check=True,
                                timeout=config.section('runtime')['command_seconds'])
        for record in result.stdout.split('\0'):
            if not record:
                continue
            key, _, value = record.partition('\n')
            if not allowed.fullmatch(key.lower()):
                raise RuntimeError('local Git configuration is not credentialless, manual inspection required')
            if key.lower() == 'remote.origin.url' and value not in {
                f'https://github.com/{config.repo}', f'https://github.com/{config.repo}.git',
            }:
                raise RuntimeError('local Git origin differs from the configured publication target')


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
    observed = result.get('checks')
    if (not isinstance(observed, list) or not all(isinstance(item, dict) and
            type(item.get('exit_code')) is int for item in observed)
            or result.get('head') != head or result.get('base') != base or observed != expected):
        raise RuntimeError('independent verification missing, failed or mismatched')


def remote_gate(config, pr: dict, head: str, base: str):
    if (pr.get('state') != 'OPEN' or pr.get('isDraft') is not False
            or pr.get('headRefOid') != head or pr.get('baseRefOid') != base
            or pr.get('baseRefName') != config.section('repository')['base_branch']
            or pr.get('closingIssuesReferences') != []):
        raise RuntimeError('remote PR changed or could prematurely close work')
    if CLOSING.search(pr.get('title', '')) or CLOSING.search(pr.get('body', '')):
        raise RuntimeError('automatic issue closing forbidden')
