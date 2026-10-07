import subprocess

import pytest

from delivery_kit.agent import arguments
from delivery_kit.github import GitHub
from delivery_kit.guards import publication, safe_git_metadata


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], capture_output=True,
                          text=True, check=True).stdout.strip()


def commit_file(repo, name, text, message='Update synthetic fixture'):
    (repo / name).write_text(text)
    git(repo, 'add', '--all')
    git(repo, 'commit', '-qm', message)
    return git(repo, 'rev-parse', 'HEAD')


def test_clean_committed_forbidden_path_is_rejected(config, git_repo):
    base = git(git_repo, 'rev-parse', 'HEAD')
    head = commit_file(git_repo, '.env', 'SYNTHETIC=fixture\n')
    assert not git(git_repo, 'status', '--porcelain')
    with pytest.raises(RuntimeError, match='forbidden'):
        publication(config, GitHub(config), git_repo, base, head)


def test_deleted_forbidden_path_still_rejects_history(config, git_repo):
    base = git(git_repo, 'rev-parse', 'HEAD')
    commit_file(git_repo, '.env', 'SYNTHETIC=fixture\n')
    (git_repo / '.env').unlink()
    head = commit_file(git_repo, 'helper.py', 'def helper():\n    return 1\n')
    assert not git(git_repo, 'diff', '--name-only', base, head).startswith('.env')
    with pytest.raises(RuntimeError, match='forbidden'):
        publication(config, GitHub(config), git_repo, base, head)


def test_valid_history_is_accepted_and_commit_budget_enforced(config, git_repo):
    base = git(git_repo, 'rev-parse', 'HEAD')
    commit_file(git_repo, 'helper.py', 'def helper():\n    return 1\n')
    head = commit_file(git_repo, 'helper.py', 'def helper():\n    return 2\n')
    publication(config, GitHub(config), git_repo, base, head)
    config.data['runtime']['max_commits'] = 1
    with pytest.raises(RuntimeError, match='oversized'):
        publication(config, GitHub(config), git_repo, base, head)


def test_unrelated_base_is_rejected_before_publication(config, git_repo):
    head = git(git_repo, 'rev-parse', 'HEAD')
    base = git(git_repo, 'commit-tree', git(git_repo, 'rev-parse', 'HEAD^{tree}'),
               '-m', 'Unrelated synthetic root')
    with pytest.raises(RuntimeError):
        publication(config, GitHub(config), git_repo, base, head)


@pytest.mark.parametrize('key', ['http.extraHeader', 'credential.helper', 'include.path',
                               'alias.helper', 'remote.other.url'])
def test_credential_capable_local_metadata_is_rejected(config, git_repo, key):
    git(git_repo, 'config', '--local', key, 'synthetic')
    with pytest.raises(RuntimeError, match='credentialless'):
        safe_git_metadata(config, git_repo)


def test_standard_metadata_and_matching_origin_are_accepted(config, git_repo):
    git(git_repo, 'remote', 'add', 'origin', f'https://github.com/{config.repo}.git')
    safe_git_metadata(config, git_repo)


def test_origin_mismatch_is_rejected(config, git_repo):
    git(git_repo, 'remote', 'add', 'origin', 'https://example.invalid/repo')
    with pytest.raises(RuntimeError, match='publication target'):
        safe_git_metadata(config, git_repo)


def test_role_launch_rechecks_metadata_before_broker(config, git_repo, tmp_path):
    config.data['agent']['permissions_validated'] = True
    git(git_repo, 'config', '--local', 'http.extraHeader', 'synthetic')
    with pytest.raises(RuntimeError, match='credentialless'):
        arguments(config, git_repo, 'author', tmp_path, tmp_path / 's', tmp_path / 'o', 'task')


def test_worktree_specific_credentials_are_rejected(config, git_repo, tmp_path):
    git(git_repo, 'config', 'extensions.worktreeConfig', 'true')
    lane = tmp_path / 'lane'
    git(git_repo, 'worktree', 'add', '-b', 'fixture', str(lane))
    git(lane, 'config', '--worktree', 'http.extraHeader', 'synthetic')
    with pytest.raises(RuntimeError, match='credentialless'):
        safe_git_metadata(config, lane)


def test_other_worktree_credentials_block_shared_metadata_grant(config, git_repo, tmp_path):
    git(git_repo, 'config', 'extensions.worktreeConfig', 'true')
    other = tmp_path / 'other'
    git(git_repo, 'worktree', 'add', '-b', 'other', str(other))
    git(other, 'config', '--worktree', 'http.extraHeader', 'synthetic')
    with pytest.raises(RuntimeError, match='credentialless'):
        safe_git_metadata(config, git_repo)
