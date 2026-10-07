import os
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.fixture
def scan_repo(tmp_path):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    subprocess.run(['git', '-C', str(tmp_path), 'config', 'user.name', 'Fixture'], check=True)
    subprocess.run(['git', '-C', str(tmp_path), 'config', 'user.email', ''], check=True)
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
