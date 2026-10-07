# Source-versus-graph navigation evaluation

The evaluator compares source-derived relationships with graph relationships. Its
runtime uses only the Python standard library (Python 3.11 or newer). The example
is a fictional paper craft workflow, written solely for this demonstration.

## Run the example

From the repository root:

```sh
python -m delivery_kit.navigation --source examples/navigation --graph examples/navigation/graph.json --baseline examples/navigation/baseline.json
```

The JSON output contains two source edges, two graph edges, precision `1.0`,
recall `1.0`, and no regressions. Standard output contains only this JSON.
Exit status is `0` for a successful evaluation, `1` for a baseline regression,
and `2` for invalid inputs, missing evidence, or a provider failure. Without a
baseline, a successful run outputs measurements but does not enforce quality.
The command never writes source files, graph files, or baselines.

## Ground truth must be independent

The source extractor receives only the source directory. The graph adapter
receives only the graph file. The default extractor parses Python syntax and
never reads the graph or executes the sample. The graph cannot define what
counts as correct evidence.

The expected relationships can be determined by reading `workshop.py` before
opening the graph: the body of `build` calls `prepare` and `decorate`. Neither
helper calls another locally defined function. Tests spell out these two
relationships independently, rather than using graph entries as expectations.
Changing, deleting, or corrupting the graph must not change source evidence.
Custom extractors must preserve that independence too. The interface separates
the inputs, but cannot sandbox a plugin or enforce its honesty.

## Normalized relationships and metrics

Each directed edge has exactly three nonempty string fields:

```json
{"source": "workshop:build", "relation": "calls", "target": "workshop:prepare"}
```

Use stable source-relative symbol names, not backend record identifiers. The
example convention is `relative/module:function`, with forward slashes and no
file suffix. Relation labels and both endpoints participate in identity.
Matching is exact and case-sensitive, with no implicit alias or whitespace
rewriting. Duplicate triples collapse into a set. The JSON graph adapter accepts
an object with an `edges` array and rejects malformed normalized edges. Extra
top-level graph fields are ignored, but edge mappings have only the three keys.

For source set `S` and graph set `G`:

- True positives: `S` intersect `G`.
- False positives: `G` minus `S`, returned as sorted `unexpected` edges.
- False negatives: `S` minus `G`, returned as sorted `missing` edges.
- Precision: true positives divided by the size of `G`.
- Recall: true positives divided by the size of `S`.

An empty denominator yields `1.0` for that metric in the library API. For example,
an empty graph with nonempty source evidence has precision `1.0` and recall
`0.0`. The CLI rejects empty source evidence to prevent a vacuous quality pass.
Metrics are micro-averaged across all supplied relationships. An adapter should
select the same language, relation, and source scope as its extractor. Otherwise
out-of-scope graph edges are false positives, not silently ignored.

## Explicit plugins

Select importable trusted callables with `module:callable` syntax:

```sh
python -m delivery_kit.navigation --source examples/navigation --graph examples/navigation/graph.json --extractor delivery_kit.navigation:python_calls --adapter delivery_kit.navigation:json_edges --baseline examples/navigation/baseline.json
```

An extractor has the contract `extract(source: pathlib.Path) -> Iterable[Edge]`.
An adapter has the contract `adapt(graph: pathlib.Path) -> Iterable[Edge]`.
Both may instead yield `(source, relation, target)` tuples or mappings with
exactly those keys. Generators are supported. Provider outputs are validated
and deduplicated before comparison. A plugin can translate any backend schema
into this contract without changing the evaluator.

The containing module must be importable in the active Python environment.
There is no automatic plugin discovery, shell execution, or file-path plugin
loading. Importing and calling a plugin executes trusted Python code. Only use
plugins you have reviewed. Built-in input errors are concise and do not include
input paths. Unexpected plugin exceptions become a generic provider error
without a traceback. Relationship strings still appear in outputs, so plugins
must emit only information appropriate for the output's audience.

## Default Python extractor scope

The default extractor recursively parses non-hidden `.py` files and skips
symbolic links. It records bare-name calls inside the bodies of top-level
synchronous and asynchronous functions when the called name is another function
defined at that file's top level. Recursive calls are included. It does not
enter nested function, class, or lambda bodies. Decorators and function defaults
are outside its scope. Syntax errors fail the run instead of reducing evidence
silently. Source code is never imported or executed.

This is intentionally a small syntactic reference, not a full Python resolver.
It does not resolve imports, methods, aliases, dynamic dispatch, variable
rebinding, local shadowing, conditional definitions, or runtime reachability.
Same-name lexical calls can be inaccurate when names are rebound. Use a richer,
independently verified extractor for projects requiring semantic resolution.

## Baseline review and explicit updates

A baseline is a JSON object with `schema_version: 1` and finite numeric
`precision` and `recall` values between `0` and `1`. A decrease in either metric
fails the command even if the other improves. Equality passes. Comparison uses
unrounded values with no tolerance. The baseline is never rewritten on failure
or success, and there is no automatic update flag.

To deliberately update a baseline:

1. Keep the existing baseline and run the command without `--baseline` to obtain
   current measurements.
2. Review source evidence independently and inspect every missing or unexpected
   edge. Confirm extractor and adapter scopes have not changed accidentally.
3. Explicitly edit the baseline's two numeric values only after accepting the
   quality change. Review the baseline diff alongside the source and graph diff.
4. Rerun the baseline-gated command and the tests.

Do not derive ground truth from graph contents or lower the baseline merely to
hide a failure. Aggregate metrics alone cannot detect all coverage loss: removing
matching edges from both inputs may preserve perfect scores. Review source scope
and evidence counts when accepting updates. This reference does not pin a source
snapshot or assert fixed evidence counts.

## Tests

With pytest available:

```sh
python -m pytest tests/test_navigation.py -q
```

Tests cover independent synthetic evidence, unique directed edges, metric
conventions, plugin loading, malformed inputs, unchanged baselines, and a failing
regression gate. No product code or external source fixture is required.
