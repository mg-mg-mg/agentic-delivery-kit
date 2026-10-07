#!/usr/bin/env bash
set -euo pipefail
kit_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$kit_root"
exec "${PYTHON:-python3}" -m delivery_kit.launch "$@"
