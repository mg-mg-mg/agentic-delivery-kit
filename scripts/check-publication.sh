#!/usr/bin/env bash
set -euo pipefail
: "${DENIED_TERMS:?Provide the owner-reviewed denied-term regular expression outside the repository}"
kit_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$kit_root"
secret_pattern='(gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9_-]{30,}|BEGIN[[:space:]]+([A-Z]+[[:space:]]+)?PRIVATE[[:space:]]+KEY|https?://[^/[:space:]]+:[^/@[:space:]]+@|[A-Za-z0-9][A-Za-z0-9._%+-]*@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|(api[_-]?key|token|password|client_secret)[[:space:]]*=[[:space:]]*["\x27][A-Za-z0-9/+_=.-]{20,})'
scan_stream() {
    local pattern="$1"
    local label="$2"
    local status=0
    rg --text -i -q "$pattern" || status=$?
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
    git log --all --format=raw --no-patch | scan_stream "$secret_pattern" 'credential patterns in commit metadata'
fi
printf '%s\n' 'Publication scans passed: zero matches in files and history'
