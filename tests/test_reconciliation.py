import json
import subprocess
import sys

import pytest

from delivery_kit import agent
from delivery_kit.dispatcher import Dispatcher, save


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True,
                          text=True, capture_output=True).stdout.strip()


@pytest.mark.parametrize('mismatch', ['none', 'parent', 'tree', 'head', 'target', 'ancestor'])
def test_squash_reconciliation_uses_real_git_objects(config, git_repo, issue, monkeypatch, mismatch):
    base = git(git_repo, 'rev-parse', 'HEAD')
    (git_repo / 'helper.py').write_text('def helper():\n    return 1\n')
    git(git_repo, 'add', '.')
    git(git_repo, 'commit', '-qm', 'Implement synthetic helper')
    head = git(git_repo, 'rev-parse', 'HEAD')
    tree = git(git_repo, 'rev-parse', f'{head}^{{tree}}')
    if mismatch == 'tree':
        tree = git(git_repo, 'rev-parse', f'{base}^{{tree}}')
    parent = head if mismatch == 'parent' else base
    merged = git(git_repo, 'commit-tree', tree, '-p', parent, '-m', 'Integrate synthetic helper')
    git(git_repo, 'update-ref', 'refs/remotes/origin/main', base if mismatch == 'ancestor' else merged)
    dispatcher = Dispatcher(config, 1)
    dispatcher.directory.mkdir(parents=True)
    dispatcher.state = {'number': 1, 'pr': 1, 'branch': 'fix/1-helper', 'phase': 'merge_pending',
                        'evidence': {'head': head, 'base': base}}
    save(dispatcher.active, dispatcher.state)
    monkeypatch.setattr(dispatcher.github, 'pr', lambda number: {
        'state': 'MERGED', 'headRefOid': base if mismatch == 'head' else head,
        'headRefName': 'fix/1-helper', 'baseRefName': 'other' if mismatch == 'target' else 'main',
        'mergeCommit': {'oid': merged},
    })
    monkeypatch.setattr(dispatcher, 'current_issue', lambda: issue)
    original = dispatcher.git
    monkeypatch.setattr(dispatcher, 'git', lambda *args, **kwargs:
                        '' if args[0] == 'fetch' else original(*args, **kwargs))
    if mismatch == 'none':
        dispatcher.reconcile()
        assert not dispatcher.active.exists()
        assert json.loads((dispatcher.directory / 'completed.json').read_text())['merged'] == merged
    else:
        with pytest.raises(RuntimeError):
            dispatcher.reconcile()
        assert dispatcher.active.exists()
        assert dispatcher.state['phase'] == 'merge_pending'


def test_timeout_terminates_group_and_retains_marker(config, git_repo, tmp_path, monkeypatch):
    config.data['agent']['process_containment_validated'] = True
    monkeypatch.setattr(agent, 'arguments', lambda *args:
                        [sys.executable, '-c', 'import time; time.sleep(60)'])
    seen = []
    with pytest.raises(subprocess.TimeoutExpired):
        agent.run(config, git_repo, 'author', tmp_path / 'scratch', {}, 'Synthetic task', 0.05,
                  lambda pid: seen.append(pid), lambda: seen.append('finished'))
    assert 'finished' not in seen
    assert seen[0] is None
    assert not agent.group_alive(seen[1])


def test_failed_launch_marker_prevents_spawn(config, git_repo, tmp_path, monkeypatch):
    config.data['agent']['process_containment_validated'] = True
    monkeypatch.setattr(agent, 'arguments', lambda *args:
                        [sys.executable, '-c', 'import time; time.sleep(60)'])
    seen = []
    def started(pid):
        seen.append(pid)
        raise RuntimeError('synthetic state write failure')
    with pytest.raises(RuntimeError, match='synthetic'):
        agent.run(config, git_repo, 'author', tmp_path / 'scratch', {}, 'Synthetic task', 1,
                  started, lambda: seen.append('finished'))
    assert seen == [None]


def test_unrelated_replacement_repository_is_rejected(config, git_repo):
    parent = config.location('repository', 'worktree_dir')
    parent.mkdir()
    foreign = parent / 'task-1-counterfeit'
    subprocess.run(['git', 'init', '-q', '-b', 'fix/1-counterfeit', str(foreign)], check=True)
    dispatcher = Dispatcher(config, 1)
    dispatcher.state = {'number': 1, 'branch': 'fix/1-counterfeit', 'worktree': str(foreign)}
    with pytest.raises(RuntimeError, match='repository identity'):
        dispatcher.worktree()


def test_legitimate_linked_worktree_retains_identity(config, git_repo):
    parent = config.location('repository', 'worktree_dir')
    parent.mkdir()
    lane = parent / 'task-1-linked'
    git(git_repo, 'worktree', 'add', '-b', 'fix/1-linked', str(lane), 'HEAD')
    dispatcher = Dispatcher(config, 1)
    dispatcher.state = {'number': 1, 'branch': 'fix/1-linked', 'worktree': str(lane)}
    assert dispatcher.worktree() == lane
