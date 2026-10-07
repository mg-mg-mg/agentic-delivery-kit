"""Behavior checks for the portable navigation evaluator."""

import json
from pathlib import Path
import subprocess
import sys

import pytest

from delivery_kit import navigation as nav


EXAMPLE = Path("examples/navigation")


def test_metrics_deduplicate_and_return_directional_mismatches():
    a = nav.Edge("one", "calls", "two")
    b = nav.Edge("two", "calls", "three")
    extra = nav.Edge("one", "calls", "three")
    result = nav.evaluate([a, b, a], [a, extra, extra])
    assert result["precision"] == 0.5
    assert result["recall"] == 0.5
    assert result["true_positive"] == 1
    assert result["false_positive"] == 1
    assert result["false_negative"] == 1
    assert result["missing"] == [b.to_dict()]
    assert result["unexpected"] == [extra.to_dict()]


@pytest.mark.parametrize("truth,graph,precision,recall", [
    ([], [], 1.0, 1.0),
    ([nav.Edge("a", "calls", "b")], [], 1.0, 0.0),
    ([], [nav.Edge("a", "calls", "b")], 0.0, 1.0),
])
def test_empty_metric_conventions(truth, graph, precision, recall):
    result = nav.evaluate(truth, graph)
    assert (result["precision"], result["recall"]) == (precision, recall)


def test_relation_and_direction_are_part_of_identity():
    truth = [nav.Edge("a", "calls", "b")]
    result = nav.evaluate(truth, [nav.Edge("b", "calls", "a"),
                                  nav.Edge("a", "imports", "b")])
    assert result["true_positive"] == 0
    assert result["false_positive"] == 2


def test_source_truth_is_independent_of_graph(tmp_path):
    (tmp_path / "toy.py").write_text(
        "def leaf():\n    return 1\n\ndef root():\n    return leaf()\n",
        encoding="utf-8",
    )
    (tmp_path / "graph.json").write_text("not a graph", encoding="utf-8")
    assert set(nav.python_calls(tmp_path)) == {nav.Edge("toy:root", "calls", "toy:leaf")}


def test_extractor_ignores_nested_functions_classes_and_unresolved_calls(tmp_path):
    (tmp_path / "toy.py").write_text(
        "def leaf():\n    return 1\n\n"
        "async def root():\n"
        "    def inner():\n        return leaf()\n"
        "    class Box:\n        value = leaf()\n"
        "    print('hello')\n    return leaf()\n",
        encoding="utf-8",
    )
    assert set(nav.python_calls(tmp_path)) == {nav.Edge("toy:root", "calls", "toy:leaf")}


def test_example_has_independently_known_calls():
    expected = {nav.Edge("workshop:build", "calls", "workshop:prepare"),
                nav.Edge("workshop:build", "calls", "workshop:decorate")}
    assert set(nav.python_calls(EXAMPLE)) == expected
    assert set(nav.json_edges(EXAMPLE / "graph.json")) == expected


def test_explicit_plugin_contract(tmp_path, monkeypatch):
    (tmp_path / "toy_plugin.py").write_text(
        "def extract(path):\n"
        "    return [{'source': 'a', 'relation': 'links', 'target': 'b'}]\n"
        "def adapt(path):\n"
        "    return [('a', 'links', 'b')]\n"
        "not_callable = 3\n", encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    source = nav.load_plugin("toy_plugin:extract")
    adapter = nav.load_plugin("toy_plugin:adapt")
    assert nav.evaluate(source(tmp_path), adapter(tmp_path))["recall"] == 1.0
    for name in ("toy_plugin", "toy_plugin:not_callable", "toy_plugin:missing"):
        with pytest.raises(nav.NavigationError):
            nav.load_plugin(name)


@pytest.mark.parametrize("value", [None, "abc", ("a", "calls"),
    {"source": "a", "target": "b"}, ("a", "", "b"), ("a", "calls", 3)])
def test_bad_normalized_edges_are_rejected(value):
    with pytest.raises(nav.NavigationError):
        nav.evaluate([], [value])


def test_baseline_regression_and_equality():
    result = nav.evaluate([("a", "calls", "b")], [("a", "calls", "b")])
    baseline = {"schema_version": 1, "precision": 1.0, "recall": 1.0}
    assert nav.check_baseline(result, baseline) == []
    result["recall"] = 0.5
    assert nav.check_baseline(result, baseline) == ["recall"]


@pytest.mark.parametrize("baseline", [
    {}, {"schema_version": 2, "precision": 1, "recall": 1},
    {"schema_version": 1, "precision": -1, "recall": 1},
    {"schema_version": 1, "precision": 1, "recall": 2},
    {"schema_version": 1, "precision": True, "recall": 1},
    {"schema_version": 1, "precision": float("nan"), "recall": 1},
    {"schema_version": 1, "precision": 1, "recall": float("inf")},
])
def test_invalid_baselines_fail_closed(baseline):
    with pytest.raises(nav.NavigationError):
        nav.check_baseline({"precision": 1.0, "recall": 1.0}, baseline)


def run_cli(*args):
    return subprocess.run([sys.executable, "-B", "-m", "delivery_kit.navigation", *args],
                          capture_output=True, text=True, check=False)


def test_required_cli_and_unchanged_baseline():
    baseline = EXAMPLE / "baseline.json"
    before = baseline.read_bytes()
    process = run_cli("--source", str(EXAMPLE), "--graph", str(EXAMPLE / "graph.json"),
                      "--baseline", str(baseline))
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    assert result["precision"] == result["recall"] == 1.0
    assert result["regressions"] == []
    assert baseline.read_bytes() == before


def test_cli_regression_exits_one(tmp_path):
    graph = tmp_path / "graph.json"
    graph.write_text('{"edges": []}', encoding="utf-8")
    process = run_cli("--source", str(EXAMPLE), "--graph", str(graph),
                      "--baseline", str(EXAMPLE / "baseline.json"))
    assert process.returncode == 1
    assert json.loads(process.stdout)["regressions"] == ["recall"]


@pytest.mark.parametrize("data", ['{"edges": [null]}', '{"edges": {}}', '{}', 'not json'])
def test_bad_graph_is_actionable_without_traceback(tmp_path, data):
    graph = tmp_path / "graph.json"
    graph.write_text(data, encoding="utf-8")
    process = run_cli("--source", str(EXAMPLE), "--graph", str(graph))
    assert process.returncode == 2
    assert "navigation error:" in process.stderr
    assert "Traceback" not in process.stderr
    assert process.stdout == ""


def test_empty_source_fails_closed(tmp_path):
    process = run_cli("--source", str(tmp_path), "--graph", str(EXAMPLE / "graph.json"))
    assert process.returncode == 2
    assert "no ground-truth edges" in process.stderr


def test_invalid_python_fails_closed(tmp_path):
    (tmp_path / "bad.py").write_text("def broken(\n", encoding="utf-8")
    with pytest.raises(nav.NavigationError):
        nav.python_calls(tmp_path)


def test_huge_baseline_number_is_rejected():
    with pytest.raises(nav.NavigationError):
        nav.check_baseline({"precision": 1.0, "recall": 1.0},
                           {"schema_version": 1, "precision": 10 ** 400, "recall": 1})


def test_generator_outputs_and_stable_order():
    values = [("z", "links", "a"), ("a", "links", "z")]
    result = nav.evaluate(iter(values), iter([]))
    assert result["missing"] == [nav.Edge(*values[1]).to_dict(), nav.Edge(*values[0]).to_dict()]
    with pytest.raises(nav.NavigationError):
        nav.normalize_edges(None)


def test_nested_paths_recursion_and_nonexecution(tmp_path):
    folder = tmp_path / "parts"
    folder.mkdir()
    (folder / "toy.py").write_text(
        "raise RuntimeError('source must not execute')\n"
        "def leaf():\n    return leaf()\n"
        "def root(value=leaf()):\n    return lambda: leaf()\n",
        encoding="utf-8",
    )
    assert nav.python_calls(tmp_path) == {nav.Edge("parts/toy:leaf", "calls", "parts/toy:leaf")}


def test_hidden_and_linked_files_are_skipped(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("not valid Python!", encoding="utf-8")
    (source / "link.py").symlink_to(outside)
    hidden = source / ".hidden"
    hidden.mkdir()
    (hidden / "broken.py").write_text("not valid Python!", encoding="utf-8")
    assert nav.python_calls(source) == set()


def test_cli_precision_regression_preserves_baseline(tmp_path):
    graph = tmp_path / "graph.json"
    data = json.loads((EXAMPLE / "graph.json").read_text(encoding="utf-8"))
    data["edges"].append({"source": "workshop:prepare", "relation": "calls", "target": "workshop:build"})
    graph.write_text(json.dumps(data), encoding="utf-8")
    baseline = EXAMPLE / "baseline.json"
    before = baseline.read_bytes()
    process = run_cli("--source", str(EXAMPLE), "--graph", str(graph), "--baseline", str(baseline))
    assert process.returncode == 1
    assert json.loads(process.stdout)["regressions"] == ["precision"]
    assert baseline.read_bytes() == before


def test_cli_custom_extractor_and_adapter(tmp_path, monkeypatch):
    (tmp_path / "cli_plugin.py").write_text(
        "import json\n"
        "from delivery_kit.navigation import Edge\n"
        "def extract(path):\n"
        "    for name in (path / 'evidence.txt').read_text().splitlines():\n"
        "        yield Edge('root', 'links', name)\n"
        "def adapt(path):\n"
        "    for name in json.loads(path.read_text())['neighbors']:\n"
        "        yield ('root', 'links', name)\n", encoding="utf-8",
    )
    (tmp_path / "evidence.txt").write_text("leaf\n", encoding="utf-8")
    graph = tmp_path / "custom.json"
    graph.write_text('{"neighbors": ["leaf"]}', encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    process = run_cli("--source", str(tmp_path), "--graph", str(graph),
                      "--extractor", "cli_plugin:extract", "--adapter", "cli_plugin:adapt")
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout)["true_positive"] == 1


def test_provider_exception_has_generic_cli_error(tmp_path, monkeypatch):
    (tmp_path / "failing_plugin.py").write_text(
        "def extract(path):\n    raise RuntimeError('private detail')\n", encoding="utf-8",
    )
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    process = run_cli("--source", str(tmp_path), "--graph", str(EXAMPLE / "graph.json"),
                      "--extractor", "failing_plugin:extract")
    assert process.returncode == 2
    assert process.stderr == "navigation error: provider failed while evaluating inputs\n"
    assert process.stdout == ""


@pytest.mark.parametrize("kind", ["graph", "baseline", "source"])
def test_missing_inputs_fail_with_no_path_echo(tmp_path, kind):
    missing = tmp_path / "absent"
    source = missing if kind == "source" else EXAMPLE
    graph = missing if kind == "graph" else EXAMPLE / "graph.json"
    baseline = missing if kind == "baseline" else EXAMPLE / "baseline.json"
    process = run_cli("--source", str(source), "--graph", str(graph), "--baseline", str(baseline))
    assert process.returncode == 2
    assert str(missing) not in process.stderr
    assert "Traceback" not in process.stderr
