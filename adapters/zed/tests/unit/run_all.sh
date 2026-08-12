#!/usr/bin/env bash
# Run all unit tests for the Zed adapter hooks
set -euo pipefail
DIR="$(dirname "$0")"

echo "=== adapters/core (manifest.py, snapshot_revert.py) ==="
python3 "$DIR/../../../core/tests/test_snapshot_revert.py"
python3 "$DIR/../../../core/tests/test_manifest.py"

echo ""
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
echo "=== prune_stale_roots.py ==="
python3 "$DIR/test_prune_stale_roots.py"

echo ""
echo "=== platform paths (darwin/linux) ==="
bash "$DIR/test_platform_paths.sh"

echo ""
echo "=== ZedCodex apply_patch parser ==="
python3 "$DIR/test_codex_patch.py"

echo ""
echo "=== ZedCodex hook lifecycle ==="
python3 "$DIR/test_codex_hooks.py"

echo ""
echo "=== ZedCodex installer ==="
python3 "$DIR/test_install_codex.py"
