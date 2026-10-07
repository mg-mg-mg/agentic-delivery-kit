"""A cooperative lease never expires automatically after a failed operation."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import subprocess


class LeaseBusy(RuntimeError):
    """Another operation or an interrupted operation owns integration."""


@contextmanager
def main_lease(repo: Path):
    result = subprocess.run(
        ['git', '-C', str(repo), 'rev-parse', '--path-format=absolute', '--git-common-dir'],
        check=True, capture_output=True, text=True, timeout=30,
    )
    path = Path(result.stdout.strip()) / 'delivery-main-lease'
    try:
        path.mkdir(mode=0o700)
    except FileExistsError as error:
        raise LeaseBusy('integration lease busy or retained, manual inspection required') from error
    nonce = secrets.token_hex(16)
    owner = {'pid': os.getpid(), 'nonce': nonce}
    descriptor = os.open(path / 'owner.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(owner, stream)
    try:
        yield path
    except BaseException:
        (path / 'failed').touch(mode=0o600)
        raise
    else:
        if json.loads((path / 'owner.json').read_text()) != owner:
            raise RuntimeError('integration lease owner changed, preserve marker')
        (path / 'owner.json').unlink()
        path.rmdir()
