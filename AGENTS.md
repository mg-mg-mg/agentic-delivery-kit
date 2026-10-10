# Agent instructions

This repository is a reference harness, not authorization to operate a target service. Runtime execution is disabled until an owner configures a target, approves publication/merge scope, and validates the installed CLI's OS-level isolation.

## Boundaries

- Read source before editing. Use the smallest change that fixes the root cause.
- Target-specific values belong in `kit.toml`, not new constants spread across modules.
- Never commit credentials, private runtime state, personal paths, internal hosts, customer data or operational records. Use fictional examples and synthetic fixtures only.
- Never copy another repository's Git metadata, history or application fixtures.
- Do not enable execution, install timers, publish task content, merge, deploy, spend money, modify accounts or send human messages without authorization for that exact target and action.
- Keep model roles credentialless. Preserve read-only review, denied tool networking, isolated writes, disabled personal hooks/apps and non-writable Git metadata. Never add a compatibility fallback that weakens permissions.
- Local leases are cooperative, fail-closed and sticky on failure. Never auto-expire or remove a retained lease.
- Independent review and verification bind to exact head/base commits. Changed SHAs invalidate prior evidence. Never infer test success from author claims.
- Serialize integration, pin the merge head and verify the squash parent/tree. Do not auto-rollback unexpected remote integration.

## Verification

Before committing, review staged paths and run the changed regression tests. The final candidate must pass `make verify` with an environment containing pytest/Ruff. Run the synthetic navigation baseline too. Supply an owner-reviewed exclusion expression outside this repository to `scripts/check-publication.sh`, and scan working-tree/index content, paths, all reachable historical blobs and commit metadata before pushing.

Keep development caches and state ignored. Document unavailable checks truthfully in `SECURITY_REVIEW.md`. Unit tests and command-construction assertions do not prove OS sandbox enforcement or live delivery. Keep repository visibility private until the owner explicitly approves a change.
