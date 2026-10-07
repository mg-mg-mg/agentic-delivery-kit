from copy import deepcopy
from pathlib import Path
import subprocess

import pytest

from delivery_kit.config import Config, load


@pytest.fixture
def config(tmp_path):
    original = load(Path(__file__).resolve().parents[1] / 'kit.toml')
    data = deepcopy(original.data)
    data['repository']['checkout'] = str(tmp_path / 'repo')
    data['repository']['worktree_dir'] = str(tmp_path / 'lanes')
    data['runtime']['state_dir'] = str(tmp_path / 'state')
    return Config(tmp_path / 'kit.toml', data)


@pytest.fixture
def git_repo(config):
    repo = config.checkout
    repo.mkdir()
    subprocess.run(['git', 'init', '-q', '-b', 'main', str(repo)], check=True)
    subprocess.run(['git', '-C', str(repo), 'config', 'user.name', 'Fixture'], check=True)
    subprocess.run(['git', '-C', str(repo), 'config', 'user.email', ''], check=True)
    (repo / 'README.md').write_text('Synthetic fixture\n')
    subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(repo), 'commit', '-qm', 'Create synthetic fixture'], check=True)
    return repo


@pytest.fixture
def issue():
    return {'number': 1, 'title': 'Fix a synthetic helper', 'body': 'Add a regression test.',
            'state': 'open', 'updated_at': '2026-01-01T00:00:00Z',
            'labels': [{'name': name} for name in
                       ['agent:ready', 'type:bug', 'priority:p1', 'track:platform', 'surface:tooling']]}
