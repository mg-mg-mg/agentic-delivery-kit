import os
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.fixture
def scan_repo(tmp_path):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    subprocess.run(['git', '-C', str(tmp_path), 'config', 'user.name', 'Fixture'], check=True)
    subprocess.run(['git', '-C', str(tmp_path), 'config', 'user.email', 'ci@example.invalid'], check=True)
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    source = Path(__file__).resolve().parents[1] / 'scripts/check-publication.sh'
    shutil.copyfile(source, scripts / 'check-publication.sh')
    return tmp_path


def scan(repo):
    return subprocess.run(['bash', str(repo / 'scripts/check-publication.sh')],
                          capture_output=True, text=True,
                          env=dict(os.environ, DENIED_TERMS='owner-only-fixture'))


def test_scan_clean_tree(scan_repo):
    assert scan(scan_repo).returncode == 0


def test_scan_clean_committed_decorator_is_not_an_email(scan_repo):
    (scan_repo / 'fixture.py').write_text('@fixture.decorator\ndef helper():\n    return 1\n')
    subprocess.run(['git', '-C', str(scan_repo), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(scan_repo), 'commit', '-qm', 'Create decorated fixture'], check=True)
    assert scan(scan_repo).returncode == 0


def test_scan_catches_recognizable_email_without_echo(scan_repo):
    synthetic = 'person' + '@' + 'example.invalid'
    (scan_repo / 'unsafe.txt').write_text(synthetic)
    result = scan(scan_repo)
    assert result.returncode != 0
    assert synthetic not in result.stderr


def test_scan_denied_untracked_file(scan_repo):
    (scan_repo / 'unsafe.txt').write_text('owner-only-fixture')
    result = scan(scan_repo)
    assert result.returncode != 0
    assert 'denied terms in files' in result.stderr
    assert 'owner-only-fixture' not in result.stderr


def test_scan_catches_removed_content_in_history(scan_repo):
    unsafe = scan_repo / 'unsafe.txt'
    unsafe.write_text('owner-only-fixture')
    subprocess.run(['git', '-C', str(scan_repo), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(scan_repo), 'commit', '-qm', 'Create fixture'], check=True)
    unsafe.unlink()
    subprocess.run(['git', '-C', str(scan_repo), 'add', '-u'], check=True)
    subprocess.run(['git', '-C', str(scan_repo), 'commit', '-qm', 'Remove fixture'], check=True)
    result = scan(scan_repo)
    assert result.returncode != 0
    assert 'denied terms in history' in result.stderr


def test_scan_catches_credential_shape_without_echo(scan_repo):
    synthetic = 'gh' + 'p_' + 'x' * 35
    (scan_repo / 'unsafe.txt').write_text(synthetic)
    result = scan(scan_repo)
    assert result.returncode != 0
    assert 'credential patterns in files' in result.stderr
    assert synthetic not in result.stderr


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def test_staged_unsafe_masked_by_safe_worktree(scan_repo):
    path = scan_repo / 'fixture'
    path.write_text('owner-only-fixture')
    git(scan_repo, 'add', 'fixture')
    path.write_text('safe')
    result = scan(scan_repo)
    assert result.returncode != 0
    assert 'owner-only-fixture' not in result.stderr


@pytest.mark.parametrize('inventory', ['untracked', 'index', 'history'])
def test_denied_filename(scan_repo, inventory):
    path = scan_repo / 'owner-only-fixture'
    path.write_text('safe')
    if inventory != 'untracked':
        git(scan_repo, 'add', path.name)
    if inventory == 'history':
        git(scan_repo, 'commit', '-qm', 'Create fixture')
        path.unlink()
        git(scan_repo, 'add', '-u')
        git(scan_repo, 'commit', '-qm', 'Remove fixture')
    result = scan(scan_repo)
    assert result.returncode != 0
    assert 'owner-only-fixture' not in result.stderr


def test_removed_binary_history(scan_repo):
    path = scan_repo / 'binary'
    path.write_bytes(b'\0owner-only-fixture\0')
    git(scan_repo, 'add', '.')
    git(scan_repo, 'commit', '-qm', 'Create binary')
    path.unlink()
    git(scan_repo, 'add', '-u')
    git(scan_repo, 'commit', '-qm', 'Remove binary')
    assert scan(scan_repo).returncode != 0


def test_merge_only_tree_history(scan_repo):
    git(scan_repo, 'add', '.')
    git(scan_repo, 'commit', '-qm', 'Create root')
    root = git(scan_repo, 'rev-parse', 'HEAD')
    tree = git(scan_repo, 'rev-parse', 'HEAD^{tree}')
    side = git(scan_repo, 'commit-tree', tree, '-p', root, '-m', 'Side')
    (scan_repo / 'fixture').write_text('owner-only-fixture')
    git(scan_repo, 'add', '.')
    unsafe_tree = git(scan_repo, 'write-tree')
    merge = git(scan_repo, 'commit-tree', unsafe_tree, '-p', root, '-p', side, '-m', 'Merge')
    clean = git(scan_repo, 'commit-tree', tree, '-p', merge, '-p', side, '-m', 'Clean merge')
    git(scan_repo, 'reset', '--hard', clean)
    assert scan(scan_repo).returncode != 0


@pytest.mark.parametrize('identity', [
    'ci@example.invalid', '14136835+mg-mg-mg@users.noreply.github.com',
])
def test_exact_approved_identities(scan_repo, identity):
    (scan_repo / 'fixture').write_text(identity)
    git(scan_repo, 'config', 'user.email', identity)
    git(scan_repo, 'add', '.')
    git(scan_repo, 'commit', '-qm', 'Approved identity')
    assert scan(scan_repo).returncode == 0


@pytest.mark.parametrize('identity', [
    'xci' + '@' + 'example.invalid', 'ci' + '@' + 'example.invalid.evil',
    'ci' + '@' + 'example.invalid-evil', 'ci+other' + '@' + 'example.invalid',
    'person' + '@' + 'example.invalid',
])
def test_allowlist_does_not_accept_lookalikes(scan_repo, identity):
    (scan_repo / 'fixture').write_text(identity)
    assert scan(scan_repo).returncode != 0


def test_approved_email_does_not_hide_same_line_credential(scan_repo):
    (scan_repo / 'fixture').write_text('ci@example.invalid gh' + 'p_' + 'x' * 35)
    assert scan(scan_repo).returncode != 0


def test_historical_identity_boundary_and_new_identity(scan_repo):
    identity = 'person' + '@' + 'example.invalid'
    git(scan_repo, 'config', 'user.email', identity)
    git(scan_repo, 'add', '.')
    git(scan_repo, 'commit', '-qm', 'Historical identity')
    boundary = git(scan_repo, 'rev-parse', 'HEAD')
    script = scan_repo / 'scripts/check-publication.sh'
    script.write_text(script.read_text().replace(
        "history_identity_boundary='1217e0b8ded0c12840076713ded8bbaedaacb55e'",
        f"history_identity_boundary='{boundary}'",
    ))
    assert scan(scan_repo).returncode == 0
    git(scan_repo, 'add', '.')
    git(scan_repo, 'commit', '-qm', 'Unapproved new identity')
    result = scan(scan_repo)
    assert result.returncode != 0
    assert 'unapproved new commit identity' in result.stderr
    assert identity not in result.stderr


def test_unapproved_commit_message_email(scan_repo):
    git(scan_repo, 'add', '.')
    git(scan_repo, 'commit', '-qm', 'Contact person' + '@' + 'example.invalid')
    result = scan(scan_repo)
    assert result.returncode != 0
    assert 'email patterns in commit text' in result.stderr


def test_default_nonsecret_policy(scan_repo):
    (scan_repo / 'fixture').write_text('/home/' + 'fixture/private')
    environment = dict(os.environ)
    environment.pop('DENIED_TERMS', None)
    result = subprocess.run(['bash', str(scan_repo / 'scripts/check-publication.sh')],
                            capture_output=True, text=True, env=environment)
    assert result.returncode != 0
    assert 'denied terms in files' in result.stderr


def test_github_merge_committer_is_allowed(scan_repo):
    git(scan_repo, 'config', 'user.email', '14136835+mg-mg-mg@users.noreply.github.com')
    git(scan_repo, 'add', '.')
    subprocess.run(['git', '-C', str(scan_repo), 'commit', '-qm', 'GitHub merge'],
                   check=True, env=dict(os.environ, GIT_COMMITTER_EMAIL='noreply' + '@github.com'))
    assert scan(scan_repo).returncode == 0


def test_github_committer_identity_is_not_an_author_exception(scan_repo):
    git(scan_repo, 'config', 'user.email', 'noreply' + '@github.com')
    git(scan_repo, 'add', '.')
    git(scan_repo, 'commit', '-qm', 'Unapproved author')
    assert 'unapproved new commit identity (author)' in scan(scan_repo).stderr


def test_new_annotated_tag_identity(scan_repo):
    git(scan_repo, 'add', '.')
    git(scan_repo, 'commit', '-qm', 'Root')
    git(scan_repo, 'tag', '-am', 'Approved release', 'approved')
    assert scan(scan_repo).returncode == 0
    git(scan_repo, 'config', 'user.email', 'person' + '@' + 'example.invalid')
    git(scan_repo, 'tag', '-am', 'Unapproved release', 'unapproved')
    result = scan(scan_repo)
    assert result.returncode != 0
    assert 'unapproved new tag identity' in result.stderr


def test_annotated_tag_historical_target_does_not_exempt_tagger(scan_repo):
    git(scan_repo, 'add', '.')
    git(scan_repo, 'commit', '-qm', 'Historical root')
    boundary = git(scan_repo, 'rev-parse', 'HEAD')
    script = scan_repo / 'scripts/check-publication.sh'
    script.write_text(script.read_text().replace(
        "history_identity_boundary='1217e0b8ded0c12840076713ded8bbaedaacb55e'",
        f"history_identity_boundary='{boundary}'",
    ))
    git(scan_repo, 'config', 'user.email', 'person' + '@' + 'example.invalid')
    git(scan_repo, 'tag', '-am', 'Historical release', 'historical', boundary)
    assert 'unapproved new tag identity' in scan(scan_repo).stderr
