"""Bounded Codex roles, with no general host credentials or tool networking."""

import json
import os
from pathlib import Path
import signal
import subprocess
import time
import sys

from .config import Config
from .guards import safe_git_metadata


def environment(scratch: Path) -> dict[str, str]:
    allowed = ('PATH', 'HOME', 'LANG', 'LC_ALL', 'LC_CTYPE')
    return {key: os.environ[key] for key in allowed if key in os.environ} | {
        'TMPDIR': str(scratch), 'GIT_CONFIG_GLOBAL': os.devnull,
        'GIT_CONFIG_NOSYSTEM': '1', 'GIT_OPTIONAL_LOCKS': '0',
        'UV_OFFLINE': '1', 'UV_CACHE_DIR': str(scratch / 'cache'),
    }


def arguments(config: Config, worktree: Path, role: str, scratch: Path,
              schema: Path, output: Path, prompt: str) -> list[str]:
    if role not in {'author', 'review', 'verify'}:
        raise ValueError('unknown agent role')
    if not config.section('agent')['permissions_validated']:
        raise RuntimeError('installed CLI permissions must be validated before execution')
    safe_git_metadata(config, worktree)
    permission = 'write' if role in {'author', 'verify'} else 'read'
    roots = {'.': permission, '.git': 'read', '.codex': 'read', '.env': 'deny',
             '**/*.env': 'deny', '**/.env*': 'deny', '**/*credential*': 'deny',
             '**/*secret*': 'deny', '**/*.pem': 'deny', '**/*.key': 'deny'}
    filesystem = {':minimal': 'read', ':tmpdir': 'write', ':workspace_roots': roots,
                  str(scratch): 'write'}
    for root in config.section('agent')['read_roots']:
        filesystem[str(Path(root).expanduser().resolve())] = 'read'
    # Git metadata must never be writable by any model role.
    common = subprocess.run(
        ['git', '-C', str(worktree), 'rev-parse', '--path-format=absolute', '--git-common-dir'],
        check=True, text=True, capture_output=True, timeout=30,
    ).stdout.strip()
    filesystem[common] = 'read'
    def toml(value):
        if isinstance(value, dict):
            return '{' + ','.join(f'{json.dumps(key)}={toml(item)}' for key, item in value.items()) + '}'
        return json.dumps(value)
    profile = f'delivery-{role}'
    return [config.section('agent')['command'], 'exec', '--ignore-user-config',
            '-m', config.section('agent')['model'],
            '-c', f'model_reasoning_effort={json.dumps(config.section("agent")["effort"])}',
            '-c', 'approval_policy="never"', '-c', f'default_permissions="{profile}"',
            '-c', f'permissions.{profile}.filesystem={toml(filesystem)}',
            '-c', f'permissions.{profile}.network.enabled=false',
            '-c', 'web_search="disabled"', '-c', 'features.apps=false',
            '-c', 'features.hooks=false', '-c', 'features.multi_agent=false',
            '-C', str(worktree), '--output-schema', str(schema), '-o', str(output), prompt]


def group_alive(pid: int) -> bool:
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def run(config: Config, worktree: Path, role: str, scratch: Path, schema: dict,
        prompt: str, timeout: float, started, finished) -> dict:
    if config.section('agent').get('process_containment_validated') is not True:
        raise RuntimeError('descendant process containment must be validated before execution')
    scratch.mkdir(mode=0o700)
    schema_path, output = scratch / 'schema.json', scratch / 'result.json'
    schema_path.write_text(json.dumps(schema))
    args = arguments(config, worktree, role, scratch, schema_path, output, prompt)
    # A blocked exec wrapper closes the spawn/registration crash window.
    started(None)
    read_fd, write_fd = os.pipe()
    wrapper = ('import os,sys; fd=int(sys.argv[1]); token=os.read(fd,1); os.close(fd); '
               'token == b"1" or sys.exit(125); os.execvpe(sys.argv[2],sys.argv[2:],os.environ)')
    try:
        process = subprocess.Popen([sys.executable, '-c', wrapper, str(read_fd), *args],
                                   cwd=worktree, env=environment(scratch), pass_fds=(read_fd,),
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   start_new_session=True)
    except BaseException:
        os.close(write_fd)
        raise
    finally:
        os.close(read_fd)
    completed = False
    interrupted = 0
    def stop(signum, _frame):
        nonlocal interrupted
        interrupted = signum
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    handlers = {signum: signal.signal(signum, stop) for signum in (signal.SIGTERM, signal.SIGINT)}
    try:
        started(process.pid)
        os.write(write_fd, b'1')
        os.close(write_fd)
        write_fd = None
        status = process.wait(timeout=timeout)
        if interrupted or status:
            raise RuntimeError(f'{role} exited abnormally ({status})')
        result = json.loads(output.read_text())
        if not isinstance(result, dict):
            raise RuntimeError('role returned no structured result')
        completed = True
    finally:
        if write_fd is not None:
            os.close(write_fd)
        if group_alive(process.pid):
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            for _ in range(50):
                process.poll()
                if not group_alive(process.pid):
                    break
                time.sleep(0.1)
            if group_alive(process.pid):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        process.wait()
        for signum, handler in handlers.items():
            signal.signal(signum, handler)
        if group_alive(process.pid):
            raise RuntimeError('child group termination unconfirmed, preserve lane')
        if completed and not interrupted:
            finished()
    return result
