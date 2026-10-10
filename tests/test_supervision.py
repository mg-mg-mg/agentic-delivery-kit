import json
import os
import signal
import sys
import subprocess
import time

import pytest

from delivery_kit import agent
from delivery_kit.dispatcher import Dispatcher


def test_uncontained_immediate_exit_detaches_descendant(config, tmp_path):
    """Control: process groups alone cannot contain even a single detached fork."""
    assert config.section('agent')['process_containment_validated'] is False
    pid_file = tmp_path / 'descendant'
    script = ("import subprocess,sys,pathlib; "
              "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'], "
              "start_new_session=True); "
              f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid))")
    process = subprocess.Popen([sys.executable, '-c', script], start_new_session=True)
    try:
        assert process.wait(timeout=5) == 0
        assert not agent.group_alive(process.pid)
        os.kill(int(pid_file.read_text()), 0)
    finally:
        if pid_file.exists():
            os.kill(int(pid_file.read_text()), signal.SIGKILL)


@pytest.mark.parametrize('assertion', [False, None, 'true'])
def test_run_requires_containment_assertion(config, tmp_path, monkeypatch, assertion):
    config.data['agent']['process_containment_validated'] = assertion
    monkeypatch.setattr(agent, 'arguments', lambda *args: pytest.fail('role prepared'))
    with pytest.raises(RuntimeError, match='containment'):
        agent.run(config, tmp_path, 'author', tmp_path / 'scratch', {}, '', 5,
                  lambda pid: pytest.fail('launch begun'), lambda: pytest.fail('marker cleared'))


def test_registration_failure_never_executes_role(config, tmp_path, monkeypatch):
    executed = tmp_path / 'executed'
    config.data['agent']['process_containment_validated'] = True
    monkeypatch.setattr(agent, 'arguments', lambda *args:
                        [sys.executable, '-c',
                         f'import time; open({str(executed)!r}, "w").close(); time.sleep(60)'])
    calls = []
    def started(pid):
        calls.append(pid)
        if pid is not None:
            # Leave time for an unguarded child to execute before simulating a crash.
            time.sleep(0.2)
            raise RuntimeError('registration crash')
    with pytest.raises(RuntimeError):
        agent.run(config, tmp_path, 'author', tmp_path / 'scratch', {}, '', 5,
                  started, lambda: pytest.fail('ownership cleared'))
    assert not executed.exists()
    assert calls[0] is None


def test_launching_state_blocks_replacement(config, monkeypatch):
    dispatcher = Dispatcher(config, 1)
    dispatcher.state = {'launching': True, 'phase': 'author'}
    monkeypatch.setattr(dispatcher, 'preflight', lambda: None)
    monkeypatch.setattr(dispatcher, 'claim', lambda: None)
    with pytest.raises(RuntimeError, match='ownership'):
        dispatcher.turn()


def test_launch_marker_durable_before_spawn(config, tmp_path, monkeypatch):
    dispatcher = Dispatcher(config, 1)
    config.data['agent']['process_containment_validated'] = True
    dispatcher.directory.mkdir(parents=True, exist_ok=True)
    dispatcher.state = {'phase': 'author'}
    monkeypatch.setattr(dispatcher, 'worktree', lambda: tmp_path)
    monkeypatch.setattr(agent, 'arguments', lambda *args: ['unused'])
    def crash(*args, **kwargs):
        assert json.loads(dispatcher.active.read_text())['launching'] is True
        raise RuntimeError('spawn crash')
    monkeypatch.setattr(agent.subprocess, 'Popen', crash)
    with pytest.raises(RuntimeError, match='spawn crash'):
        dispatcher.phase('author', {}, '')
    assert dispatcher.state['launching'] is True
