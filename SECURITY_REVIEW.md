# Security review

Review date: 2026-10-07 (UTC).

## Extraction boundary

This is a newly initialized repository with no imported history. Runtime modules and documentation were rewritten around generic delivery invariants. The only source fixtures are a tiny fictional Python workflow, normalized graph edges and an independent baseline. No application implementation, private operational data, internal configuration, credential files or source issue identifiers are included.

All target-specific settings live in `kit.toml`. Its repository is a fictional example, execution is disabled, CLI permission validation is false, the Project number is zero, and the LaunchAgent namespace is `com.example.agentic-delivery`. Runtime state, local settings, environment files, caches and generated navigation indexes are excluded from publication.

## Verification evidence

The checks below were observed on the extraction candidate. Checks cover the entire publication tree, including hidden tracked files, plus every commit message and patch in this fresh history. They do not scan unrelated repositories or export private runtime state.

- `uv run pytest -q`: 92 tests passed.
- `uv run ruff check .`: passed with no findings.
- Shell syntax gate over every `scripts/*.sh`: passed.
- `python -m delivery_kit.governance`: configuration and maintained policy paths passed.
- Synthetic navigation CLI with the shipped baseline: precision and recall both 1.0, zero missing/unexpected edges and zero regressions. The tests independently prove a degraded graph exits nonzero and does not rewrite the baseline.
- ShellCheck: unavailable on the local tool path, shell syntax checking used instead.
- Dedicated secret scanner: neither Gitleaks nor TruffleHog is installed. The specified ripgrep fallback is used.
- `DENIED_TERMS=<owner-provided expression> bash scripts/check-publication.sh`: zero matches in publication files and all commit patches/messages. The expression covers excluded product/domain/provider names, personal path patterns, internal-host prefixes and private identifier prefixes. The denied literals are intentionally not embedded in this repository.
- The same script scans recognizable GitHub/provider credentials, private key headers, embedded URL credentials, email addresses and long credential assignments. Publication paths and `git log -p --all` are both checked. No discovered value is printed.
- Manual manifest review: all publication files are limited to kit code, tests, synthetic fixtures, generic docs, license, configuration and public package metadata. The dependency lockfile uses the public package index and archive hashes only.
- Git identities have empty email fields. History was initialized independently, with no alternate object store or imported refs.
- Scanner regression tests catch denied untracked content, removed historical content, credential-shaped values and recognizable email addresses without echoing discovered values. A diff-prefixed Python decorator is explicitly tested as a non-email.

## Runtime boundaries not proven by these checks

Credentialless unit tests validate command construction, environment allowlists, ownership and metadata gates, fixed-SHA evidence and sticky leases. Real Git fixtures reject unrelated replacement repositories and accept legitimate linked worktrees by comparing shared Git metadata identity. They do not prove the installed Codex CLI's OS sandbox behavior. Live Codex author/reviewer/verifier execution, GitHub task delivery/merge and actual LaunchAgent installation were not exercised for this extraction. Those remain explicit activation prerequisites.

The inference broker requires its own authentication and model transport. Role tools must not receive general host credentials or network access. A boolean assertion is not a sandbox audit. The target repository's local Git/toolchain configuration and explicitly imported navigation plugins are trusted. The lease protects only cooperating local processes, and GitHub cannot atomically pin both merge head and base through this CLI command.

Keep this repository private until an independent publication review has approved it. The kit includes no code that changes repository visibility, performs a release, or deploys a service.
