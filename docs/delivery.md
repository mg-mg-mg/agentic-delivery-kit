# Delivery boundaries and recovery

## Three independent responsibilities

The author owns one dedicated task worktree and its implementation. The dispatcher, not the author, stages reviewed paths, commits, pushes and creates a PR. The reviewer is a separate read-only invocation at fixed head/base commits. The verifier is another credentialless invocation that executes the exact reviewer-selected argv checks. The integration role belongs to the trusted dispatcher.

Only explicit owner authorization covers publication and code merge. It never includes deployment, purchases, account changes, production writes, or human messages. Issue prose is task data, not permission to widen filesystem or network access. The configured opt-in label represents task authorization, not a generic grant to any issue content.

## Queue and ownership

Selection requires exactly one allowed type, priority and track, at least one configured surface label, an explicit opt-in and no hold. Only closed, completed native prerequisites unblock work. Priority ordering is deterministic. A nonzero Project number additionally requires the configured ready status and no deferred dispatch value. No Project identifiers are shipped.

Snapshots paginate and reject a limit-sized or malformed result. Existing matching local/remote branches and declared open PR references prevent a duplicate author. Pool claims are serialized by a nonblocking filesystem lock. Each worker preserves its own active state. A malformed peer claim stops the queue instead of allowing a duplicate.

The primary checkout stays clean on its configured integration branch. Worktrees live below one configured parent. Saved lanes must still point to the same worktree and branch, and share the configured primary repository's Git common directory. No dotenv files are linked or copied to a lane. Git hooks are disabled for dispatcher writes. Treat the target repository's existing Git configuration as trusted, and validate toolchain read roots carefully.

## Review and merge

Every ready change needs separate read-only review and independent observed checks at exact head/base commits. Findings, remaining criteria or unavailable checks block merge. A changed head/base invalidates prior evidence. The dispatcher uses `--squash --match-head-commit` and never uses an administrator bypass or unchecked auto-merge.

PR text and commits cannot use automatic closing keywords, since issue completion must not occur before reconciliation. The reference does not automatically close an Issue or mutate Project status. After merging it verifies a single squash parent equal to the reviewed base and a tree equal to the reviewed head. Issue content/labels must still match the saved fingerprint. Evidence stays in private runtime state, not in this reference repository.

## Interruption and leases

`active.json` is replaced atomically with private permissions before external transitions. A pending merge is reconciled by reading remote merge state, never retried blindly. An open or ambiguously merged PR remains owned. Failed or signaled integration retains the lease in the shared Git common directory. Never expire that marker by age alone.

Inspect private owner metadata, processes, branch/worktree state and remote merge evidence before manually clearing a retained lease. All cooperating fetch/merge entrypoints must use the same lease. Raw Git commands and other machines can ignore it. The lease has no nested acquisition or inherited-token protocol in this reference.

A process-group marker is saved before model work. Timeouts terminate the whole group and retain the lane if termination cannot be confirmed. The current worker lock is held throughout a pass. Installer rendering/installation acquires every worker lock first and refuses to overwrite existing timers. Failed installation is not automatically rolled back.

## Deliberately manual recovery

Partial worktree creation, unexpected base drift, changed acceptance criteria, exhausted repair budgets, ambiguous publication and unmatched squash results require manual inspection. No automatic rebase, destructive cleanup, notification transport, secret linking, status reconciliation or release operation is included. A completed branch and worktree are preserved so a maintainer can inspect exact evidence before cleanup.

Before installing timers, prewarm required dependencies and confirm the installed Python and Codex executables are available in the timer environment. Use small bounded queues first. Private timer stdout/stderr and completed diagnostic artifacts can contain task content and must never be committed or published.
