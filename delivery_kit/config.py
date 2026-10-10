"""Load one configuration file without consulting repository-local settings."""

from dataclasses import dataclass
from pathlib import Path
import re
import tomllib


@dataclass(frozen=True)
class Config:
    path: Path
    data: dict

    def section(self, name: str) -> dict:
        return self.data[name]

    def location(self, section: str, name: str) -> Path:
        value = Path(self.data[section][name]).expanduser()
        return (self.path.parent / value).resolve()

    @property
    def repo(self) -> str:
        return f"{self.data['repository']['owner']}/{self.data['repository']['name']}"

    @property
    def checkout(self) -> Path:
        return self.location('repository', 'checkout')

    @property
    def state(self) -> Path:
        return self.location('runtime', 'state_dir')


def load(path: Path) -> Config:
    path = path.resolve()
    with path.open('rb') as stream:
        data = tomllib.load(stream)
    for section in ('repository', 'queue', 'project', 'runtime', 'agent', 'launch', 'guards'):
        if not isinstance(data.get(section), dict):
            raise ValueError(f'missing configuration section: {section}')
    config = Config(path, data)
    repo = data['repository']
    for name in ('owner', 'name', 'base_branch'):
        if not isinstance(repo.get(name), str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', repo[name]):
            raise ValueError(f'invalid repository {name}')
    runtime = data['runtime']
    for name in ('workers', 'pass_seconds', 'phase_seconds', 'merge_reserve_seconds',
                 'minimum_free_bytes', 'max_changed_files', 'max_repairs',
                 'max_commits', 'command_seconds', 'retained_failures'):
        if type(runtime.get(name)) is not int or runtime[name] < 1:
            raise ValueError(f'invalid positive budget: {name}')
    if runtime['merge_reserve_seconds'] >= runtime['pass_seconds']:
        raise ValueError('merge reserve must be less than pass budget')
    for section, names in {
        'queue': ('hold_labels', 'allowed_types', 'priorities', 'tracks'),
        'project': ('ready_options',), 'agent': ('read_roots',),
        'guards': ('forbidden_paths', 'required_docs'),
    }.items():
        for name in names:
            if not isinstance(data[section].get(name), list) or not all(
                    isinstance(value, str) and value for value in data[section][name]):
                raise ValueError(f'invalid string list: {section}.{name}')
    if (type(runtime.get('enabled')) is not bool
            or any(type(data['agent'].get(name)) is not bool
                   for name in ('permissions_validated', 'process_containment_validated'))):
        raise ValueError('execution gates must be booleans')
    for name in ('branch_template', 'worktree_template'):
        if '{number}' not in repo[name] or '{slug}' not in repo[name]:
            raise ValueError(f'naming template must identify task and outcome: {name}')
        rendered = repo[name].format(number=1, slug='sample')
        if '..' in rendered or not re.fullmatch(r'[A-Za-z0-9_./-]+', rendered):
            raise ValueError(f'unsafe naming template: {name}')
        if name == 'worktree_template' and '/' in rendered:
            raise ValueError('worktree template must be one directory name')
    if type(data['project'].get('number')) is not int or data['project']['number'] < 0:
        raise ValueError('Project number must be zero or positive')
    if type(data['queue'].get('max_items')) is not int or data['queue']['max_items'] < 1:
        raise ValueError('invalid snapshot limit')
    for name in ('opt_in_label', 'surface_prefix', 'type_prefix', 'priority_prefix', 'track_prefix'):
        if not isinstance(data['queue'].get(name), str) or not data['queue'][name]:
            raise ValueError(f'invalid queue policy: {name}')
    if config.state == config.checkout or config.checkout in config.state.parents:
        raise ValueError('private state must be outside the target checkout')
    worktrees = config.location('repository', 'worktree_dir')
    if worktrees == config.checkout or config.checkout in worktrees.parents:
        raise ValueError('task worktrees must be outside the target checkout')
    return config
