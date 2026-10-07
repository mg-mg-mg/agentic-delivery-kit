"""Portable governance checks for the kit's own policy surface."""

import argparse
from pathlib import Path

from .config import load


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('kit.toml'))
    args = parser.parse_args(argv)
    config = load(args.config)
    for relative in config.section('guards')['required_docs']:
        path = config.path.parent / relative
        if path.resolve().parent != config.path.parent and config.path.parent not in path.resolve().parents:
            raise ValueError('policy path escapes kit root')
        if not path.is_file():
            raise ValueError('required policy document missing')
    print('Configuration and maintained policy paths passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
