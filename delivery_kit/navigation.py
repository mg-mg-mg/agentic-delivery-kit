"""Compare independent source evidence with normalized graph edges.

Runtime dependencies are limited to the Python standard library.
"""

from __future__ import annotations

import argparse
import ast
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import importlib
import json
import math
from pathlib import Path
import sys
from typing import Callable


class NavigationError(ValueError):
    """Invalid input or an unusable evaluation configuration."""


@dataclass(frozen=True, order=True)
class Edge:
    """A directed relationship with stable, source-relative symbol names."""

    source: str
    relation: str
    target: str

    def __post_init__(self) -> None:
        if any(not isinstance(value, str) or not value.strip()
               for value in (self.source, self.relation, self.target)):
            raise NavigationError("edge fields must be nonempty strings")

    def to_dict(self) -> dict[str, str]:
        return {"source": self.source, "relation": self.relation, "target": self.target}


def normalize_edges(values: Iterable) -> set[Edge]:
    """Accept Edge objects, three-item sequences, or normalized mappings."""
    result = set()
    try:
        for value in values:
            if isinstance(value, Edge):
                edge = value
            elif isinstance(value, Mapping):
                if set(value) != {"source", "relation", "target"}:
                    raise NavigationError("edge mappings require source, relation, and target only")
                edge = Edge(value["source"], value["relation"], value["target"])
            elif isinstance(value, (tuple, list)) and len(value) == 3:
                edge = Edge(*value)
            else:
                raise NavigationError("expected a normalized edge")
            result.add(edge)
    except TypeError as error:
        raise NavigationError("edge provider must return an iterable of normalized edges") from error
    return result


def evaluate(source_edges: Iterable, graph_edges: Iterable) -> dict:
    """Compute micro precision/recall over unique directed edge triples."""
    truth = normalize_edges(source_edges)
    graph = normalize_edges(graph_edges)
    matched = truth & graph
    missing = truth - graph
    unexpected = graph - truth
    return {
        "schema_version": 1,
        "source_count": len(truth),
        "graph_count": len(graph),
        "true_positive": len(matched),
        "false_positive": len(unexpected),
        "false_negative": len(missing),
        "precision": len(matched) / len(graph) if graph else 1.0,
        "recall": len(matched) / len(truth) if truth else 1.0,
        "missing": [edge.to_dict() for edge in sorted(missing)],
        "unexpected": [edge.to_dict() for edge in sorted(unexpected)],
    }


def load_plugin(spec: str) -> Callable[[Path], Iterable]:
    """Load one explicitly selected module:callable, without discovery."""
    module_name, separator, name = spec.partition(":")
    if not separator or not module_name or not name or ":" in name:
        raise NavigationError("plugin must be specified as module:callable")
    try:
        plugin = getattr(importlib.import_module(module_name), name)
    except (ImportError, AttributeError) as error:
        raise NavigationError("could not load the selected plugin") from error
    if not callable(plugin):
        raise NavigationError("selected plugin is not callable")
    return plugin


def _read_json(path: Path, label: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        raise NavigationError(f"could not read valid {label} JSON") from error


def json_edges(path: Path) -> set[Edge]:
    """Adapt a JSON object containing an edges array to normalized edges."""
    document = _read_json(path, "graph")
    if not isinstance(document, dict) or not isinstance(document.get("edges"), list):
        raise NavigationError("graph must be an object containing an edges array")
    return normalize_edges(document["edges"])


class _BodyCalls(ast.NodeVisitor):
    """Collect lexical call names without entering a nested definition."""

    def __init__(self) -> None:
        self.names: set[str] = set()

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            self.names.add(node.func.id)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        pass

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        pass

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        pass

    def visit_Lambda(self, node: ast.Lambda) -> None:
        pass


def python_calls(source: Path) -> set[Edge]:
    """Extract same-file bare-name calls in top-level Python function bodies.

    This small syntactic extractor is not a general Python call resolver.
    It never reads a graph or executes the source.
    """
    if not source.is_dir():
        raise NavigationError("source must be a directory")
    result = set()
    for path in sorted(source.rglob("*.py")):
        relative = path.relative_to(source)
        if path.is_symlink() or any(part.startswith(".") for part in relative.parts):
            continue
        # Do not follow a directory link into a different source tree.
        if any(parent.is_symlink() for parent in path.parents if parent != source
               and source in parent.parents):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, SyntaxError) as error:
            raise NavigationError("could not parse a Python source file") from error
        functions = [node for node in tree.body
                     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        names = {node.name for node in functions}
        module = relative.with_suffix("").as_posix()
        for function in functions:
            visitor = _BodyCalls()
            for statement in function.body:
                visitor.visit(statement)
            for name in visitor.names & names:
                result.add(Edge(f"{module}:{function.name}", "calls", f"{module}:{name}"))
    return result


def check_baseline(result: Mapping, baseline: Mapping) -> list[str]:
    """Return metric names that decreased, rejecting invalid baselines."""
    if (not isinstance(baseline, Mapping)
            or type(baseline.get("schema_version")) is not int
            or baseline["schema_version"] != 1):
        raise NavigationError("baseline requires schema_version 1")
    for metric in ("precision", "recall"):
        value = baseline.get(metric)
        if (type(value) not in (int, float) or not 0 <= value <= 1
                or not math.isfinite(value)):
            raise NavigationError(f"baseline {metric} must be a finite number between 0 and 1")
    return [metric for metric in ("precision", "recall")
            if result[metric] < baseline[metric]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="source directory")
    parser.add_argument("--graph", type=Path, required=True, help="graph input file")
    parser.add_argument("--baseline", type=Path, help="read-only precision/recall baseline")
    parser.add_argument("--extractor", default="delivery_kit.navigation:python_calls",
                        help="trusted source plugin as module:callable")
    parser.add_argument("--adapter", default="delivery_kit.navigation:json_edges",
                        help="trusted graph plugin as module:callable")
    args = parser.parse_args(argv)
    try:
        extractor = load_plugin(args.extractor)
        adapter = load_plugin(args.adapter)
        truth = normalize_edges(extractor(args.source))
        if not truth:
            raise NavigationError("extractor returned no ground-truth edges")
        result = evaluate(truth, adapter(args.graph))
        result["regressions"] = (check_baseline(result, _read_json(args.baseline, "baseline"))
                                 if args.baseline else [])
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        return 1 if result["regressions"] else 0
    except NavigationError as error:
        print(f"navigation error: {error}", file=sys.stderr)
        return 2
    except Exception:
        # Plugin exceptions may contain private paths or arbitrary payloads.
        print("navigation error: provider failed while evaluating inputs", file=sys.stderr)
        return 2


if __name__ == "__main__":
    # Plugins import the canonical module, so evaluate with its Edge class too.
    entry_main = importlib.import_module("delivery_kit.navigation").main
    raise SystemExit(entry_main())
