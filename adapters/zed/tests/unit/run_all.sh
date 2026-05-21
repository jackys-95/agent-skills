#!/usr/bin/env bash
# Run all unit tests for the Zed adapter hooks
set -euo pipefail
DIR="$(dirname "$0")"

echo "=== pre_edit_zed_snapshot.py ==="
bash "$DIR/test_pre_hook.sh"

echo ""
echo "=== post_edit_open_in_zed.py ==="
bash "$DIR/test_post_hook.sh"
