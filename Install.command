#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo 'Python 3.11+ is required. Install it from python.org, then run again.'
  exit 1
fi
exec python3 Install.py "$@"
