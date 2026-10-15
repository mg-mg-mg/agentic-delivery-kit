# Delivery boundaries and recovery

This document describes the kit's earlier dispatcher-based reference model, not current production practice. Its strict evidence invalidation, restricted queue and manual reconciliation are deliberate reference constraints. For current practice, see the companion [Agentic Engineering case study](https://github.com/mg-mg-mg/agentic-engineering). The executable supports Codex CLI role launching, not OMP.

## Three independent responsibilities

The author owns one dedicated task worktree and its implementation. The dispatcher, not the author, stages reviewed paths, commits, pushes and creates a PR. The reviewer is a separate read-only invocation at fixed head/base commits. The verifier is another credentialless invocation that executes the exact reviewer-selected argv checks. The integration role belongs to the trusted dispatcher.

Only explicit owner authorization covers publication and code merge. It never includes deployment, purchases, account changes, production writes, or human messages. Issue prose is task data, not permission to widen filesystem or network access. The configured opt-in label represents task authorization, not a generic grant to any issue content.

## Queue and ownership

Selection requires exactly one allowed type, priority and track, at least one configured surface label, an explicit opt-in and no hold. Only closed, completed native prerequisites unblock work. Priority ordering is deterministic. A nonzero Project number additionally requires the configured ready status and no deferred dispatch value. No Project identifiers are shipped.

Snapshots paginate and reject a limit-sized or malformed result. Existing matching local/remote branches and declared open PR references prevent a duplicate author. Pool claims are serialized by a nonblocking filesystem lock. Each worker preserves its own active state. A malformed peer claim stops the queue instead of allowing a duplicate.

The primary checkout stays clean on its configured integration branch. Worktrees live below one configured parent. Saved lanes must still point to the same worktree and branch, and share the configured primary repository's Git common directory. No dotenv files are linked or copied to a lane. Git hooks are disabled for dispatcher writes. Treat the target repository's existing Git configuration as trusted, and validate toolchain read roots carefully.

## Review and merge

Before every model role, the dispatcher permits only standard credential-free local/worktree Git metadata and the exact HTTPS origin. Credential helpers, HTTP headers, include files, aliases, filters and extra remotes in local configuration stop activation. Move approved authentication into the trusted dispatcher's external credential store, never repository metadata. Repository history must also be credential-free. This precheck is not an atomic defense against a hostile process changing metadata afterward, so only trusted checkouts are supported.

Before every push, including a clean resumed lane, validate base ancestry, every commit's touched paths, cumulative file and commit limits, whitespace and automatic closing text. A forbidden path added then removed still blocks publication. Staging checks alone are not publication evidence.

Every ready change needs separate read-only review and independent observed checks at exact head/base commits. Findings, remaining criteria or unavailable checks block merge. A changed head/base invalidates prior evidence. The dispatcher uses `--squash --match-head-commit` and never uses an administrator bypass or unchecked auto-merge.

PR text and commits cannot use automatic closing keywords, since issue completion must not occur before reconciliation. The reference does not automatically close an Issue or mutate Project status. Immediately after merging it reads back the integration ref and requires the squash commit, then verifies the owned head branch, configured base branch, a single squash parent equal to the reviewed base, a tree equal to the reviewed head and ancestry in the fetched integration branch. Issue content/labels must still match the saved fingerprint. Evidence stays in private runtime state, not in this reference repository. Each worker's `completed.json` retains an ordered list of completed task records rather than replacing earlier evidence.

## Interruption and leases

`active.json` is replaced atomically with private permissions before external transitions. A pending merge is reconciled by reading remote merge state, never retried blindly. An open or ambiguously merged PR remains owned. Qualification runs before acquiring the integration lease. Base drift is expected with concurrent workers: a moved base, changed PR head or other read-only refusal stops the lane in `needs_rebase` without retaining the lease. The lease rechecks the exact frozen head/base snapshot; a proven pre-mutation refusal returns normally and releases it. Failed or signaled mutation-path integration retains the lease in the shared Git common directory. Never expire that marker by age alone.

Inspect private owner metadata, processes, branch/worktree state and remote merge evidence before manually clearing a retained lease. All cooperating integration entrypoints must use the same lease; qualification fetches run outside it. Raw Git commands and other machines can ignore it. The lease has no nested acquisition or inherited-token protocol in this reference.

Before spawning, a durable conservative launching marker is saved. A pipe-gated exec wrapper cannot start role work until its PID has been registered durably. Unresolved launching or child ownership always blocks automatic replacement, even if the original process group is absent; recovery requires manual inspection.

Role execution and timer installation require the owner assertion `process_containment_validated = true`, in addition to the permission gate. Set it only after validating that the installed CLI/OS profile contains all descendants for the role's lifetime, including detached sessions. The kit does not implement or independently audit that OS containment; a hard descendant-lifetime guarantee comes only from the validated containment mechanism.

Process-group termination remains best-effort cleanup, not descendant containment. Even a single child that starts a new session and whose parent exits immediately can survive outside the original group. No process-table polling or detached-PID discovery is performed. Any abnormal exit, timeout, signal, invalid result or failed registration keeps the writer marker sticky; a successful structured result clears it only after the original group is absent, relying on the owner's containment assertion for descendants. Unresolved markers require manual inspection regardless of apparent PID absence.

The current worker lock is held throughout a pass. Installer rendering/installation acquires every worker lock first and refuses to overwrite existing timers. Failed installation is not automatically rolled back.

## Deliberately manual recovery

Partial worktree creation, changed acceptance criteria, exhausted repair budgets, ambiguous publication and unmatched squash results require manual inspection. Base/head drift requires fresh author work and fixed-SHA review, not automatic retries. Blocked authors, rejected review evidence and failed verification persist `phase = "blocked"` and a short reason; repair counts are saved before testing the budget. Later ticks skip `blocked` and `needs_rebase` lanes. A private `failure.json` also stops ticks before external operations; command failures retain at most the last 300 stderr characters there, never on stdout. After inspection, an operator must explicitly clear the failure file and repair/reset the active phase and evidence before resuming. Never clear unresolved process ownership or a retained lease without investigating it.

No automatic rebase, destructive cleanup, notification transport, secret linking, status reconciliation or release operation is included. A completed branch and worktree are preserved so a maintainer can inspect exact evidence before cleanup.

Before installing timers, prewarm required dependencies and configure `launch.path` with the absolute directories holding Git, GitHub CLI and Codex. Confirm those executables are available in that timer environment. Use small bounded queues first. Private timer stdout/stderr and completed diagnostic artifacts can contain task content and must never be committed or published.
