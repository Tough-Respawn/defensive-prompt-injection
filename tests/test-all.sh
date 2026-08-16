#!/usr/bin/env bash

set -eu

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$repo_root"

./tests/test-hooks.sh
PYTHONPATH=src python3 -m unittest -v tests/test_core.py

if command -v node >/dev/null 2>&1; then
  node tests/test-deepseek-harness.mjs
else
  echo "# Node.js unavailable; DeepSeek Harness runtime test skipped"
fi
