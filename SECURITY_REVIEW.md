# Security review

Review date: 2026-10-07 (UTC).

## Extraction boundary

This is a newly initialized repository with no imported history. Runtime modules and documentation were rewritten around generic delivery invariants. The only source fixtures are a tiny fictional Python workflow, normalized graph edges and an independent baseline. No application implementation, private operational data, internal configuration, credential files or source issue identifiers are included.

All target-specific settings live in `kit.toml`. Its repository is a fictional example, execution is disabled, CLI permission validation is false, the Project number is zero, and the LaunchAgent namespace is `com.example.agentic-delivery`. Runtime state, local settings, environment files, caches and generated navigation indexes are excluded from publication.

## Verification evidence

The extraction checks below were observed on the original candidate, not proof of the later repairs. The publication scanner now inspects tracked/untracked working-tree bytes and index blobs independently, all reachable commit trees' unique blobs (binary included), historical/current paths and separate commit metadata. It does not scan unrelated repositories or export private runtime state.

- `uv run pytest -q`: 108 tests passed.
- `uv run ruff check .`: passed with no findings.
- Shell syntax gate over every `scripts/*.sh`: passed.
- `python -m delivery_kit.governance`: configuration and maintained policy paths passed.
- Synthetic navigation CLI with the shipped baseline: precision and recall both 1.0, zero missing/unexpected edges and zero regressions. The tests independently prove a degraded graph exits nonzero and does not rewrite the baseline.
- ShellCheck: unavailable on the local tool path, shell syntax checking used instead.
- Dedicated secret scanner: neither Gitleaks nor TruffleHog is installed. The specified ripgrep fallback is used.
- `DENIED_TERMS=<externally supplied expression> bash scripts/check-publication.sh` applies a case-insensitive regular expression without printing discovered values. Denied literals are intentionally not embedded in this repository.
- The same script scans recognizable GitHub/provider credentials, private key headers, embedded URL credentials, email addresses and long credential assignments. Raw blob scanning is not decoding: compressed archives, encoded payloads and unsupported credential formats still need independent review.
- Manual manifest review: all publication files are limited to kit code, tests, synthetic fixtures, generic docs, license, configuration and public package metadata. The dependency lockfile uses the public package index and archive hashes only.
- Git identities have empty email fields. History was initialized independently, with no alternate object store or imported refs.
- Real Git regressions verify complete committed publication history, including forbidden paths removed before the final tree, and reject unrelated bases. Merge reconciliation rejects a different target branch or missing integration-branch ancestry. Known credential-capable configuration keys, mismatched origins, linked-worktree configuration and other worktrees' shared configuration are rejected before role launch.
- Real Git scanner regressions cover staged content masked by safe unstaged edits, denied current/historical filenames, removed binary blobs and merge-only trees, alongside removed text, credential shapes and recognizable email addresses. Publication guards also reject added-then-removed historical symbolic links.

Repair verification (2026-10-10): `uv run make verify` passed 129 tests, Ruff, governance and shell syntax; ShellCheck remained unavailable. `uv lock --check` passed. The shipped navigation baseline reported precision/recall 1.0 with no regressions. Earlier regressions against the original commit produced 14 failures and two passing controls; the initial polling-based supervision repair was subsequently rejected and replaced by the enforced containment activation gate and an honest detached-escape control.

The repaired publication scanner passed with a generic denied expression supplied only through the environment. This targeted zero-match result is not proof of anonymity, absence of every secret format, or owner approval of publication.

## Runtime boundaries not proven by these checks

Credentialless unit tests validate command construction, environment allowlists, ownership and metadata gates, fixed-SHA evidence and sticky leases. Real Git fixtures reject unrelated replacement repositories and accept legitimate linked worktrees by comparing shared Git metadata identity. They do not prove the installed Codex CLI's OS sandbox behavior. Live Codex author/reviewer/verifier execution, GitHub task delivery/merge and actual LaunchAgent installation were not exercised for this extraction. Those remain explicit activation prerequisites.

The inference broker requires its own authentication and model transport. Role tools must not receive general host credentials or network access. A boolean assertion is not a sandbox audit. The target repository's local Git/toolchain configuration and explicitly imported navigation plugins are trusted. The lease protects only cooperating local processes, and GitHub cannot atomically pin both merge head and base through this CLI command.

Role launch uses a durable launching marker and an exec handshake before work begins. `run`, `--execute` and timer installation refuse activation unless the owner sets `process_containment_validated = true` after validating descendant lifetime containment in the installed CLI/OS profile. Process-group cleanup alone cannot contain detached descendants: an honest immediate-parent-exit subprocess control demonstrates a detached child surviving without OS containment. No process-table polling or detached-PID discovery is performed. Abnormal execution retains ownership; unresolved markers never automatically clear on restart. Successful completion relies on the separately validated OS containment for a hard descendant-lifetime guarantee. This boolean gate does not itself prove containment.

Keep this repository private until an independent publication review has approved it. The kit includes no code that changes repository visibility, performs a release, or deploys a service.
