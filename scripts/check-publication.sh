#!/usr/bin/env bash
set -euo pipefail
default_denied_terms='(/Users/[A-Za-z0-9._-]+/|/home/[A-Za-z0-9._-]+/|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'
DENIED_TERMS="${DENIED_TERMS:-$default_denied_terms}"
# Only ancestors of this published snapshot retain historical identity emails.
history_identity_boundary='1217e0b8ded0c12840076713ded8bbaedaacb55e'
kit_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$kit_root"
# Exact approved identities only; other addresses, including lookalikes, fail.
email_pattern='(?<![A-Za-z0-9._%+@-])(?!(?:ci@example\.invalid|14136835\+mg-mg-mg@users\.noreply\.github\.com)(?![A-Za-z0-9._%+@-]))[A-Za-z0-9][A-Za-z0-9._%+-]*@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
credential_pattern='(gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9_-]{30,}|BEGIN[[:space:]]+([A-Z]+[[:space:]]+)?PRIVATE[[:space:]]+KEY|https?://[^/[:space:]]+:[^/@[:space:]]+@|(api[_-]?key|token|password|client_secret)[[:space:]]*=[[:space:]]*["\x27][A-Za-z0-9/+_=.-]{20,})'
secret_pattern="$credential_pattern|$email_pattern"
scan_stream() {
    local pattern="$1"
    local label="$2"
    local status=0
    rg --pcre2 --text -i -q "$pattern" || status=$?
    if [[ "$status" -eq 0 ]]; then
        printf '%s\n' "Publication scan failed: $label" >&2
        return 1
    fi
    if [[ "$status" -ne 1 ]]; then
        printf '%s\n' "Publication scan could not complete: $label" >&2
        return "$status"
    fi
}
# Keep index bytes independent of unstaged edits. NUL inventories preserve unusual names.
worktree_bytes() {
    while IFS= read -r -d '' path; do
        if [[ -f "$path" || -L "$path" ]]; then cat -- "$path"; fi
    done < <(git ls-files -z --cached --others --exclude-standard)
}
index_bytes() {
    git ls-files --stage -z | while IFS= read -r -d '' entry; do
        header="${entry%%$'\t'*}"
        read -r mode blob stage <<< "$header"
        git cat-file blob "$blob"
    done
}
history_paths() {
    git rev-list --all | while IFS= read -r commit; do
        git ls-tree -r -z --name-only "$commit"
    done
}
history_bytes() {
    git rev-list --all | while IFS= read -r commit; do
        git ls-tree -r "$commit"
    done | while IFS=$'\t' read -r header path; do
        read -r mode type blob <<< "$header"
        if [[ "$type" == blob ]]; then printf '%s\n' "$blob"; fi
    done | sort -u | while IFS= read -r blob; do
        git cat-file blob "$blob"
    done
}
tag_identities() {
    git for-each-ref refs/tags --format='%(objecttype)%09%(taggeremail:trim)' |
        while IFS=$'\t' read -r type email; do
            [[ "$type" == tag ]] || continue
            printf '%s\n' "$email"
        done
}
git ls-files -z --cached --others --exclude-standard | scan_stream "$DENIED_TERMS" 'denied terms in file paths'
worktree_bytes | scan_stream "$DENIED_TERMS" 'denied terms in files'
worktree_bytes | scan_stream "$secret_pattern" 'credential patterns in files'
index_bytes | scan_stream "$DENIED_TERMS" 'denied terms in index'
index_bytes | scan_stream "$secret_pattern" 'credential patterns in index'
if git rev-parse --verify HEAD >/dev/null 2>&1; then
    history_paths | scan_stream "$DENIED_TERMS" 'denied terms in history paths'
    history_bytes | scan_stream "$DENIED_TERMS" 'denied terms in history'
    history_bytes | scan_stream "$secret_pattern" 'credential patterns in history'
    git log --all --format=raw --no-patch | scan_stream "$DENIED_TERMS" 'denied terms in commit metadata'
    git log --all --format=raw --no-patch | scan_stream "$credential_pattern" 'credential patterns in commit metadata'
    # Message and name text is checked even in the grandfathered history.
    git log --all --format='%B%n%an%n%cn' | scan_stream "$email_pattern" 'email patterns in commit text'
    identity_range=(--all)
    if git cat-file -e "$history_identity_boundary^{commit}" 2>/dev/null; then
        identity_range+=("^$history_identity_boundary")
    fi
    git log "${identity_range[@]}" --format='%ae' |
        scan_stream '^(?!(ci@example\.invalid|14136835\+mg-mg-mg@users\.noreply\.github\.com)$).*' 'unapproved new commit identity (author)'
    git log "${identity_range[@]}" --format='%ce' |
        scan_stream '^(?!(ci@example\.invalid|14136835\+mg-mg-mg@users\.noreply\.github\.com|noreply@github\.com)$).*' 'unapproved new commit identity (committer)'
    tag_identities |
        scan_stream '^(?!(ci@example\.invalid|14136835\+mg-mg-mg@users\.noreply\.github\.com)$).*' 'unapproved new tag identity'
fi
printf '%s\n' 'Publication scans passed: no unapproved matches in files, index and history (identity boundary applied)'
