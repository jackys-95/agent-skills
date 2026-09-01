#!/usr/bin/env bash
# Run script-level lifecycle and installer integration tests for the Zed adapters.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== pre_edit_zed_snapshot.py ==="
bash "$DIR/test_pre_hook.sh"

echo ""
echo "=== post_edit_open_in_zed.py ==="
bash "$DIR/test_post_hook.sh"

echo ""
echo "=== reset_zed_turn.py ==="
bash "$DIR/test_reset_hook.sh"

echo ""
echo "=== stop_flush_zed_diffs.py ==="
bash "$DIR/test_stop_hook.sh"

echo ""
echo "=== revert_zed_snapshot.py ==="
bash "$DIR/test_revert_hook.sh"

echo ""
echo "=== ZedCodex hook lifecycle ==="
python3 "$DIR/test_codex_hooks.py"

echo ""
echo "=== ZedCodex installer subprocess ==="
python3 "$DIR/test_install_codex.py"
