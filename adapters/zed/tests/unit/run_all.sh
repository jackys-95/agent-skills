#!/usr/bin/env bash
# Run isolated function/module tests for the Zed adapters.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== prune_stale_roots.py ==="
python3 "$DIR/test_prune_stale_roots.py"

echo ""
echo "=== platform paths (darwin/linux) ==="
bash "$DIR/test_platform_paths.sh"

echo ""
echo "=== shared tmux pane authority ==="
python3 "$DIR/test_tmux_pane_authority.py"

echo ""
echo "=== shared Zed/tmux edit-injection runtime ==="
python3 "$DIR/test_tmux_edit_injection.py"

echo ""
echo "=== ZedCodex apply_patch parser ==="
python3 "$DIR/test_codex_patch.py"

echo ""
echo "=== Zed + Claude Code installer helpers ==="
python3 "$DIR/test_install_zed_cc.py"
