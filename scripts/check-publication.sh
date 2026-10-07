#!/usr/bin/env bash
set -euo pipefail
: "${DENIED_TERMS:?Provide the owner-reviewed denied-term regular expression outside the repository}"
kit_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$kit_root"
secret_pattern='(gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9_-]{30,}|BEGIN[[:space:]]+([A-Z]+[[:space:]]+)?PRIVATE[[:space:]]+KEY|https?://[^/[:space:]]+:[^/@[:space:]]+@|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|(api[_-]?key|token|password|client_secret)[[:space:]]*=[[:space:]]*["\x27][A-Za-z0-9/+_=.-]{20,})'
scan_stream() {
    local pattern="$1"
    local label="$2"
    local status=0
    rg -i -q "$pattern" || status=$?
    if [[ "$status" -eq 0 ]]; then
        printf '%s\n' "Publication scan failed: $label" >&2
        return 1
    fi
    if [[ "$status" -ne 1 ]]; then
        printf '%s\n' "Publication scan could not complete: $label" >&2
        return "$status"
    fi
}
# Read only intended Git paths, including hidden files, never local runtime derivatives.
git ls-files -z --cached --others --exclude-standard | xargs -0 cat | scan_stream "$DENIED_TERMS" 'denied terms in files'
git ls-files -z --cached --others --exclude-standard | xargs -0 cat | scan_stream "$secret_pattern" 'credential patterns in files'
if git rev-parse --verify HEAD >/dev/null 2>&1; then
    git log -p --all | scan_stream "$DENIED_TERMS" 'denied terms in history'
    git log -p --all | scan_stream "$secret_pattern" 'credential patterns in history'
fi
printf '%s\n' 'Publication scans passed: zero matches in files and history'
