import json
from types import SimpleNamespace

import pytest

from delivery_kit import dispatcher as dispatcher_module
from delivery_kit.dispatcher import Dispatcher, save
from delivery_kit.github import GitHub
from delivery_kit.lease import main_lease


def lane(config, monkeypatch, worker=1):
    dispatcher = Dispatcher(config, worker)
    dispatcher.directory.mkdir(parents=True, exist_ok=True)
    dispatcher.state = {'number': worker, 'pr': worker, 'phase': 'review', 'head': 'head',
                        'base': 'base', 'branch': f'fix/{worker}-helper', 'repairs': 0}
    dispatcher.persist()
    monkeypatch.setattr(dispatcher, 'preflight', lambda: None)
    monkeypatch.setattr(dispatcher, 'claim', lambda: setattr(
        dispatcher, 'state', json.loads(dispatcher.active.read_text())))
    monkeypatch.setattr(dispatcher, 'worktree', lambda: config.checkout)
    monkeypatch.setattr(dispatcher, 'current_issue', lambda: {'title': 'Synthetic task', 'body': 'Test'})
    monkeypatch.setattr(dispatcher, 'git', lambda *args, **kwargs: 'head' if args[0] == 'rev-parse' else '')
    return dispatcher


@pytest.mark.parametrize('failure', ['author_blocked', 'review_rejected', 'verification_failed',
                                     'repair_budget_exhausted'])
def test_failed_phase_stops_later_ticks(config, monkeypatch, failure):
    dispatcher = lane(config, monkeypatch)
    if failure == 'author_blocked':
        dispatcher.state['phase'] = 'author'
    if failure == 'repair_budget_exhausted':
        dispatcher.state['repairs'] = config.section('runtime')['max_repairs']
    dispatcher.persist()
    calls = []
    def phase(role, *args):
        calls.append(role)
        if role == 'author':
            return {'status': 'blocked'}
        if role == 'review':
            return {'head': 'head', 'base': 'base',
                    'verdict': 'changes_required' if failure == 'repair_budget_exhausted' else 'accepted',
                    'findings': ['Unresolved'] if failure == 'review_rejected' else [],
                    'remaining': [], 'checks': [['true']]}
        return {'head': 'head', 'base': 'base', 'checks': [{'argv': ['true'], 'exit_code': 1}]}
    monkeypatch.setattr(dispatcher, 'phase', phase)
    with pytest.raises(RuntimeError):
        dispatcher.turn()
    saved = json.loads(dispatcher.active.read_text())
    assert saved['phase'] == 'blocked'
    assert saved['reason'] == failure
    if failure == 'repair_budget_exhausted':
        assert saved['repairs'] == config.section('runtime')['max_repairs'] + 1
    previous = calls.copy()
    assert dispatcher.turn() == 'stopped'
    assert calls == previous


def test_failure_file_blocks_before_any_external_operation(config, monkeypatch):
    dispatcher = lane(config, monkeypatch)
    save(dispatcher.directory / 'failure.json', {'message': 'Private failure'})
    monkeypatch.setattr(dispatcher, 'preflight', lambda: pytest.fail('must not retry'))
    assert dispatcher.turn() == 'stopped'


def open_pr(head='head'):
    return {'state': 'OPEN', 'isDraft': False, 'headRefOid': head, 'baseRefOid': 'base',
            'baseRefName': 'main', 'closingIssuesReferences': [], 'title': 'Synthetic task', 'body': ''}


@pytest.mark.parametrize('movement', ['before_lease', 'inside_base', 'inside_head', 'issue', 'qualification_head'])
def test_merge_refusals_leave_lease_free(config, git_repo, monkeypatch, movement):
    first = lane(config, monkeypatch, 1)
    second = lane(config, monkeypatch, 2)
    live = {'base': 'base'}
    mutations = []
    def setup(dispatcher):
        reads = []
        def git(*args, **kwargs):
            return live['base'] if args[0] == 'rev-parse' else ''
        def pr(number):
            reads.append(number)
            head = 'changed' if (dispatcher is second and
                   (movement == 'qualification_head' or movement == 'inside_head' and len(reads) > 1)) else 'head'
            return open_pr(head)
        def ref(*args):
            base = 'changed' if dispatcher is second and movement == 'inside_base' else live['base']
            return {'object': {'sha': base}}
        monkeypatch.setattr(dispatcher, 'git', git)
        monkeypatch.setattr(dispatcher.github, 'pr', pr)
        monkeypatch.setattr(dispatcher.github, 'json', ref)
        monkeypatch.setattr(dispatcher.github, 'command', lambda *args: mutations.append(dispatcher.worker))
        monkeypatch.setattr(dispatcher, 'reconcile', lambda **kwargs: live.update(base='changed'))
    setup(first)
    setup(second)
    first.merge()
    assert mutations == [1]
    if movement != 'before_lease':
        live['base'] = 'base'
    if movement == 'issue':
        def held():
            raise RuntimeError('issue held')
        monkeypatch.setattr(second, 'current_issue', held)
    assert second.merge() == 'refused'
    assert mutations == [1]
    assert second.state['phase'] == 'needs_rebase'
    with main_lease(git_repo):
        pass
    assert not (git_repo / '.git' / 'delivery-main-lease').exists()
    assert second.turn() == 'stopped'


def test_mutation_failure_retains_lease(config, git_repo, monkeypatch):
    dispatcher = lane(config, monkeypatch)
    monkeypatch.setattr(dispatcher, 'git', lambda *args, **kwargs: 'base' if args[0] == 'rev-parse' else '')
    monkeypatch.setattr(dispatcher.github, 'pr', lambda number: open_pr())
    monkeypatch.setattr(dispatcher.github, 'json', lambda *args: {'object': {'sha': 'base'}})
    def failed(*args):
        raise RuntimeError('uncertain merge outcome')
    monkeypatch.setattr(dispatcher.github, 'command', failed)
    with pytest.raises(RuntimeError, match='uncertain'):
        dispatcher.merge()
    assert (git_repo / '.git' / 'delivery-main-lease' / 'failed').exists()


def test_command_stderr_is_bounded_and_private(config, monkeypatch, capsys):
    config.data['runtime']['enabled'] = True
    config.data['agent'].update(permissions_validated=True, process_containment_validated=True)
    monkeypatch.setattr(dispatcher_module, 'load', lambda path: config)
    monkeypatch.setattr('delivery_kit.github.subprocess.run', lambda *args, **kwargs:
                        SimpleNamespace(returncode=1, stderr='x' * 500 + ' private-stderr-sentinel'))
    def failed(self):
        GitHub(config).command('gh', 'api')
    monkeypatch.setattr(Dispatcher, 'turn', failed)
    assert dispatcher_module.main(['--execute']) == 1
    failure = json.loads((config.state / 'workers' / '1' / 'failure.json').read_text())
    assert len(failure['stderr_tail']) == 300
    assert failure['stderr_tail'].endswith(' private-stderr-sentinel')
    assert 'private-stderr-sentinel' not in failure['message']
    assert 'private-stderr-sentinel' not in capsys.readouterr().out


@pytest.mark.parametrize('resource, phase', [
    ('queue.lock', 'review'), ('merge.lock', 'merge_pending'), ('lease', 'merge_pending'),
    ('run.lock', 'merge_pending'), ('merge.lock', 'merge_ready'), ('lease', 'merge_ready'),
])
def test_peer_contention_is_busy_and_next_tick_resumes(config, git_repo, monkeypatch, capsys, resource, phase):
    dispatcher = lane(config, monkeypatch)
    config.data['runtime']['enabled'] = True
    config.data['agent'].update(permissions_validated=True, process_containment_validated=True)
    monkeypatch.setattr(dispatcher_module, 'load', lambda path: config)
    monkeypatch.setattr(dispatcher_module, 'Dispatcher', lambda config, worker: dispatcher)
    mutations = []
    if resource == 'queue.lock':
        dispatcher.active.unlink()
        dispatcher.state = {}
        monkeypatch.setattr(dispatcher, 'claim', lambda: Dispatcher.claim(dispatcher))
        monkeypatch.setattr(dispatcher_module, 'select', lambda *args: None)
    else:
        dispatcher.state.update(phase=phase, evidence={'head': 'head', 'base': 'base'})
        dispatcher.persist()
        monkeypatch.setattr(dispatcher, 'git', lambda *args, **kwargs:
                            'base' if args[0] == 'rev-parse' else '')
        monkeypatch.setattr(dispatcher.github, 'pr', lambda number: open_pr())
        monkeypatch.setattr(dispatcher.github, 'json', lambda *args: {'object': {'sha': 'base'}})
        monkeypatch.setattr(dispatcher.github, 'command', lambda *args: mutations.append('merge'))
        monkeypatch.setattr(dispatcher, 'reconcile', lambda **kwargs:
                            mutations.append('reconcile') if phase == 'merge_pending' else None)
        monkeypatch.setattr(dispatcher, 'phase', lambda *args: pytest.fail('must reuse fixed-SHA evidence'))
    before = dispatcher.active.read_bytes() if dispatcher.active.exists() else None
    held = main_lease(git_repo) if resource == 'lease' else dispatcher_module.lock(
        dispatcher.directory / resource if resource == 'run.lock' else config.state / resource)
    with held:
        assert dispatcher_module.main(['--execute']) == 0
        assert capsys.readouterr().out == 'busy\n'
        assert not (dispatcher.directory / 'failure.json').exists()
        assert (dispatcher.active.read_bytes() if dispatcher.active.exists() else None) == before
        assert mutations == []
        if resource == 'lease':
            assert (git_repo / '.git' / 'delivery-main-lease').exists()
    assert dispatcher_module.main(['--execute']) == 0
    assert capsys.readouterr().out == ('idle\n' if resource == 'queue.lock' else 'merged\n')
    assert not (dispatcher.directory / 'failure.json').exists()
    expected = 'reconcile' if phase == 'merge_pending' else 'merge'
    assert mutations == ([] if resource == 'queue.lock' else [expected])


@pytest.mark.parametrize('change', [{'state': 'CLOSED'}, {'baseRefName': 'other'}])
def test_in_lease_pr_admission_change_refuses_without_mutation(config, git_repo, monkeypatch, change):
    dispatcher = lane(config, monkeypatch)
    monkeypatch.setattr(dispatcher, 'git', lambda *args, **kwargs:
                        'base' if args[0] == 'rev-parse' else '')
    reads = []
    def pr(number):
        reads.append(number)
        return open_pr() | (change if len(reads) > 1 else {})
    monkeypatch.setattr(dispatcher.github, 'pr', pr)
    monkeypatch.setattr(dispatcher.github, 'json', lambda *args: {'object': {'sha': 'base'}})
    monkeypatch.setattr(dispatcher.github, 'command', lambda *args: pytest.fail('must not attempt merge'))
    assert dispatcher.merge() == 'refused'
    assert dispatcher.state['phase'] == 'needs_rebase'
    assert not (git_repo / '.git' / 'delivery-main-lease').exists()
