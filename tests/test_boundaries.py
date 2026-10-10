from copy import deepcopy
import json
from pathlib import Path
import plistlib
import subprocess

import pytest

from delivery_kit.agent import arguments, environment
from delivery_kit.config import load
from delivery_kit.dispatcher import Dispatcher, lock, main, save
from delivery_kit.github import GitHub, eligible, fingerprint, select
from delivery_kit.guards import remote_gate, review_evidence, staged, verification_evidence
from delivery_kit.launch import documents
from delivery_kit.lease import LeaseBusy, main_lease


def test_defaults_are_disabled():
    config = load(Path(__file__).resolve().parents[1] / 'kit.toml')
    assert config.section('runtime')['enabled'] is False
    assert config.section('agent')['permissions_validated'] is False
    assert config.section('agent')['process_containment_validated'] is False


def test_preview_never_calls_network(monkeypatch, capsys):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('unexpected subprocess'))
    assert main(['--config', str(Path(__file__).resolve().parents[1] / 'kit.toml')]) == 0
    assert json.loads(capsys.readouterr().out)['mode'] == 'configuration-only'


def test_execute_disabled_before_any_subprocess(monkeypatch):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('unexpected subprocess'))
    with pytest.raises(SystemExit) as error:
        main(['--config', str(Path(__file__).resolve().parents[1] / 'kit.toml'), '--execute'])
    assert error.value.code == 2


def test_environment_is_allowlisted(monkeypatch, tmp_path):
    monkeypatch.setenv('GH_TOKEN', 'synthetic-not-a-credential')
    monkeypatch.setenv('DATABASE_URL', 'synthetic')
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic')
    result = environment(tmp_path)
    assert not {'GH_TOKEN', 'DATABASE_URL', 'OPENAI_API_KEY'} & result.keys()
    assert result['GIT_CONFIG_GLOBAL'] == '/dev/null'
    assert result['UV_OFFLINE'] == '1'


@pytest.mark.parametrize('role,write', [('author', True), ('review', False), ('verify', True)])
def test_profiles_deny_tools_and_git(config, git_repo, tmp_path, role, write):
    config.data['agent']['permissions_validated'] = True
    args = arguments(config, git_repo, role, tmp_path / 'scratch',
                     tmp_path / 'schema.json', tmp_path / 'result.json', 'Synthetic task')
    assert '--ignore-user-config' in args
    profile = next(arg for arg in args if '.filesystem=' in arg)
    assert '".git"="read"' in profile
    assert '".env"="deny"' in profile
    assert f'"."="{"write" if write else "read"}"' in profile
    assert f'permissions.delivery-{role}.network.enabled=false' in args
    assert 'features.hooks=false' in args


def test_profile_requires_explicit_validation(config, git_repo, tmp_path):
    with pytest.raises(RuntimeError, match='validated'):
        arguments(config, git_repo, 'author', tmp_path, tmp_path / 's', tmp_path / 'o', 'task')


def test_eligibility_and_label_holds(config, issue):
    assert eligible(config, issue, [], {})
    issue['labels'].append({'name': 'hold'})
    assert not eligible(config, issue, [], {})


@pytest.mark.parametrize('label', ['agent:ready', 'type:bug', 'priority:p1', 'track:platform', 'surface:tooling'])
def test_missing_required_label_rejects(config, issue, label):
    issue['labels'] = [item for item in issue['labels'] if item['name'] != label]
    assert not eligible(config, issue, [], {})


def test_duplicate_type_rejects(config, issue):
    issue['labels'].append({'name': 'type:maintenance'})
    assert not eligible(config, issue, [], {})


@pytest.mark.parametrize('state,reason,expected', [
    ('open', None, False), ('closed', 'not_planned', False), ('closed', 'completed', True),
])
def test_only_completed_prerequisites_unblock(config, issue, state, reason, expected):
    assert eligible(config, issue, [{'number': 2, 'state': state, 'state_reason': reason}], {}) is expected


def test_malformed_metadata_fails_closed(config, issue):
    with pytest.raises(RuntimeError):
        eligible(config, issue, [{'state': 'open'}], {})
    issue['labels'] = None
    with pytest.raises(RuntimeError):
        eligible(config, issue, [], {})


def test_project_gate(config, issue):
    config.data['project']['number'] = 1
    assert not eligible(config, issue, [], {})
    assert eligible(config, issue, [], {1: {'status': 'Ready', 'dispatch': None}})
    assert not eligible(config, issue, [], {1: {'status': 'Ready', 'dispatch': 'Deferred'}})
    assert not eligible(config, issue, [], {1: {'status': 'Done', 'dispatch': None}})


def test_fingerprint_binds_criteria_and_labels(issue):
    original = fingerprint(issue)
    issue['body'] += ' Changed.'
    assert fingerprint(issue) != original
    changed = fingerprint(issue)
    issue['labels'].append({'name': 'hold'})
    assert fingerprint(issue) != changed


def test_pagination_rejects_limit(config, monkeypatch):
    github = GitHub(config)
    config.data['queue']['max_items'] = 1
    monkeypatch.setattr(github, 'json', lambda *a: [[{'number': 1}]])
    with pytest.raises(RuntimeError, match='limit'):
        github.pages('synthetic')


def test_selection_excludes_owned_and_claimed(config, issue):
    second = deepcopy(issue)
    second['number'] = 2
    class Snapshot:
        def pages(self, endpoint):
            if '/issues?' in endpoint:
                return [second, issue]
            return []
        def project_rows(self):
            return {}
        def command(self, *args):
            return 'fix/1-existing-owner'
        def blockers(self, number):
            return []
    assert select(config, Snapshot(), set())['number'] == 2
    assert select(config, Snapshot(), {2}) is None


def test_lock_rejects_second_writer(tmp_path):
    with lock(tmp_path / 'run.lock'):
        with pytest.raises(BlockingIOError):
            with lock(tmp_path / 'run.lock'):
                pytest.fail('second writer acquired lane')


def test_atomic_private_state(tmp_path):
    path = tmp_path / 'active.json'
    save(path, {'phase': 'author'})
    save(path, {'phase': 'review'})
    assert json.loads(path.read_text()) == {'phase': 'review'}
    assert path.stat().st_mode & 0o777 == 0o600
    assert not path.with_suffix('.tmp').exists()


def test_successful_lease_releases(git_repo):
    with main_lease(git_repo) as path:
        assert path.exists()
        assert (path / 'owner.json').stat().st_mode & 0o777 == 0o600
        with pytest.raises(LeaseBusy):
            with main_lease(git_repo):
                pass
    assert not path.exists()


def test_failed_lease_is_sticky(git_repo):
    with pytest.raises(RuntimeError, match='synthetic'):
        with main_lease(git_repo) as path:
            raise RuntimeError('synthetic failure')
    assert (path / 'failed').exists()
    with pytest.raises(LeaseBusy):
        with main_lease(git_repo):
            pass


def test_verification_requires_exact_checks():
    review = {'head': 'a' * 40, 'base': 'b' * 40, 'verdict': 'accepted',
              'findings': [], 'remaining': [], 'checks': [['python', '-m', 'pytest']]}
    checks = review_evidence(review, 'a' * 40, 'b' * 40)
    valid = {'head': 'a' * 40, 'base': 'b' * 40, 'checks': [{'argv': checks[0], 'exit_code': 0}]}
    verification_evidence(valid, 'a' * 40, 'b' * 40, checks)
    for key, value in [('head', 'c' * 40), ('checks', [])]:
        with pytest.raises(RuntimeError):
            verification_evidence(valid | {key: value}, 'a' * 40, 'b' * 40, checks)
    with pytest.raises(RuntimeError):
        review_evidence(review | {'remaining': ['manual release']}, 'a' * 40, 'b' * 40)
    with pytest.raises(RuntimeError):
        verification_evidence(valid | {'checks': [{'argv': checks[0], 'exit_code': False}]},
                              'a' * 40, 'b' * 40, checks)


@pytest.mark.parametrize('changed', [
    {'isDraft': True}, {'state': 'MERGED'}, {'headRefOid': 'c' * 40},
    {'baseRefOid': 'd' * 40}, {'body': 'Closes #1'}, {'closingIssuesReferences': [{'number': 1}]},
])
def test_remote_drift_rejects(config, changed):
    pr = {'state': 'OPEN', 'isDraft': False, 'headRefOid': 'a' * 40, 'baseRefOid': 'b' * 40,
          'baseRefName': 'main', 'closingIssuesReferences': [], 'title': 'Synthetic change', 'body': 'Refs #1'}
    remote_gate(config, pr, 'a' * 40, 'b' * 40)
    with pytest.raises(RuntimeError):
        remote_gate(config, pr | changed, 'a' * 40, 'b' * 40)


def test_staged_secret_path_is_rejected(config, git_repo):
    (git_repo / '.env').write_text('SYNTHETIC=fixture\n')
    subprocess.run(['git', '-C', str(git_repo), 'add', '.env'], check=True)
    with pytest.raises(RuntimeError, match='forbidden'):
        staged(config, GitHub(config), git_repo)


def test_launch_documents_escape_paths_and_bound_pool(config, tmp_path):
    config.data['launch']['python'] = 'python3'
    output = list(documents(config, tmp_path / 'root with spaces'))
    assert len(output) == config.data['runtime']['workers']
    for label, document in output:
        assert label.startswith('com.example.agentic-delivery.')
        assert '--execute' in document['ProgramArguments']
        assert document['RunAtLoad'] is False
        assert plistlib.loads(plistlib.dumps(document)) == document


def test_worker_limit(config):
    with pytest.raises(ValueError):
        Dispatcher(config, 0)
    with pytest.raises(ValueError):
        Dispatcher(config, config.data['runtime']['workers'] + 1)


@pytest.mark.parametrize('fault', ['missing', 'wrong_option', 'wrong_type', 'duplicate', None])
def test_project_schema_distinguishes_empty_dispatch(config, monkeypatch, fault):
    config.data['project']['number'] = 1
    project = config.section('project')
    fields = [
        {'name': project['status_field'],
         'options': [{'name': value} for value in project['ready_options']]},
        {'name': project['dispatch_field'], 'options': [{'name': project['deferred_option']}]},
    ]
    if fault == 'missing':
        fields.pop()
    elif fault == 'wrong_option':
        fields[1]['options'] = [{'name': 'Other'}]
    elif fault == 'wrong_type':
        fields[1].pop('options')
    elif fault == 'duplicate':
        fields.append(deepcopy(fields[1]))
    status_key = project['status_field'][:1].lower() + project['status_field'][1:]
    row = {'content': {'repository': config.repo, 'type': 'Issue', 'number': 1},
           status_key: 'Ready'}
    github = GitHub(config)
    monkeypatch.setattr(github, 'json', lambda *args:
                        {'fields': fields, 'totalCount': len(fields)} if 'field-list' in args
                        else {'items': [row], 'totalCount': 1})
    if fault:
        with pytest.raises(RuntimeError, match='field'):
            github.project_rows()
    else:
        assert github.project_rows()[1]['dispatch'] is None


def test_execute_requires_containment_validation(config, monkeypatch):
    config.data['runtime']['enabled'] = True
    config.data['agent']['permissions_validated'] = True
    monkeypatch.setattr('delivery_kit.dispatcher.load', lambda path: config)
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: pytest.fail('execution begun'))
    with pytest.raises(SystemExit) as error:
        main(['--execute'])
    assert error.value.code == 2
