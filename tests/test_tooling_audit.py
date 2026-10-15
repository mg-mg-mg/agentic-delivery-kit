from pathlib import Path
import shutil
import subprocess

import pytest

from delivery_kit.config import load
from delivery_kit.launch import documents


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('value', ['[]', '["relative"]', '["/bin:/usr/bin"]', '"/bin"', '[42]'])
def test_timer_path_rejects_invalid_configuration(tmp_path, value):
    text = (ROOT / 'kit.toml').read_text()
    # Insert into the section so this also exercises older configurations.
    lines = [line for line in text.splitlines() if not line.startswith('path = ')]
    text = '\n'.join(lines).replace('[launch]', f'[launch]\npath = {value}')
    config_path = tmp_path / 'kit.toml'
    config_path.write_text(text)
    with pytest.raises(ValueError, match='launch.path'):
        load(config_path)


def test_timer_renders_configured_path(config):
    config.data['launch']['path'] = ['/opt/tools/bin', '/usr/bin', '/bin']
    for _, document in documents(config, ROOT):
        assert document['EnvironmentVariables'] == {'PATH': '/opt/tools/bin:/usr/bin:/bin'}


def test_publication_script_passes_shellcheck():
    if shutil.which('shellcheck') is None:
        pytest.skip('ShellCheck not installed; CI installs it')
    subprocess.run(['shellcheck', 'scripts/check-publication.sh'], cwd=ROOT, check=True)


def test_ci_enforces_documented_gates():
    workflow = (ROOT / '.github/workflows/ci.yml').read_text()
    assert 'uv sync --locked --group dev' in workflow
    assert 'uv run make verify' in workflow
    assert 'apt-get install -y ripgrep shellcheck' in workflow
    assert "python: ['3.11', '3.12']" in workflow
    assert 'python-version: ${{ matrix.python }}' in workflow
    assert 'python -m delivery_kit.navigation --source examples/navigation --graph examples/navigation/graph.json --baseline examples/navigation/baseline.json' in workflow
    assert '# v4.4.0' in workflow
    assert 'ref: ${{ github.event.pull_request.head.sha || github.sha }}' in workflow
    assert 'fetch-depth: 0' in workflow
    assert 'persist-credentials: false' in workflow
