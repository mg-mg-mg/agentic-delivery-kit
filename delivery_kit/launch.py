"""Render or explicitly install macOS timers while all worker lanes are idle."""

import argparse
from contextlib import ExitStack
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys

from .config import load
from .dispatcher import lock


def documents(config, kit_root: Path):
    launch = config.section('launch')
    if not re.fullmatch(r'[A-Za-z0-9.-]+', launch['label_prefix']):
        raise ValueError('invalid LaunchAgent label prefix')
    if type(launch['interval_seconds']) is not int or launch['interval_seconds'] <= 0:
        raise ValueError('invalid timer interval')
    python = Path(launch['python']).expanduser()
    if not python.is_absolute():
        import shutil
        executable = shutil.which(str(python))
        if executable is None:
            raise ValueError('configured Python is unavailable')
        python = Path(executable)
    for worker in range(1, config.section('runtime')['workers'] + 1):
        label = f'{launch["label_prefix"]}.{worker}'
        directory = config.state / 'workers' / str(worker)
        yield label, {
            'Label': label,
            'ProgramArguments': [str(python), '-m', 'delivery_kit.dispatcher',
                                 '--config', str(config.path), '--worker', str(worker), '--execute'],
            'WorkingDirectory': str(kit_root), 'StartInterval': launch['interval_seconds'],
            'RunAtLoad': False, 'ProcessType': 'Background', 'Umask': 0o077,
            'StandardOutPath': str(directory / 'timer.out'),
            'StandardErrorPath': str(directory / 'timer.err'),
        }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('kit.toml'))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--render', type=Path)
    mode.add_argument('--install', action='store_true')
    args = parser.parse_args(argv)
    config = load(args.config)
    root = Path(__file__).resolve().parent.parent
    if args.install and (sys.platform != 'darwin' or not config.section('runtime')['enabled']
                         or not config.section('agent')['permissions_validated']):
        parser.error('installation requires macOS and explicitly enabled, validated execution')
    destination = args.render or Path.home() / 'Library/LaunchAgents'
    destination.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        for worker in range(1, config.section('runtime')['workers'] + 1):
            stack.enter_context(lock(config.state / 'workers' / str(worker) / 'run.lock'))
        for label, document in documents(config, root):
            path = destination / f'{label}.plist'
            if path.exists():
                raise RuntimeError('existing timer preserved, remove explicitly before reinstalling')
            path.write_bytes(plistlib.dumps(document))
            path.chmod(0o600)
            if args.install:
                subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(path)], check=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
