#!/usr/bin/env bash
# Run all automated tests for the Zed adapters and their shared core.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== adapters/core (manifest.py, snapshot_revert.py) ==="
python3 "$DIR/../../core/tests/test_snapshot_revert.py"
python3 "$DIR/../../core/tests/test_manifest.py"

echo ""
echo "=== Zed adapter unit suites ==="
bash "$DIR/unit/run_all.sh"

echo ""
echo "=== Zed adapter integration suites ==="
bash "$DIR/integration/run_all.sh"
