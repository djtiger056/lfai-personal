#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

exec python backend/main.py
