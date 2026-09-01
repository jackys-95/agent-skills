#!/usr/bin/env bash
# Unit tests for the darwin/linux platform paths outside tmux_edit_injection.py,
# which has focused Python coverage.
set -euo pipefail

ADAPTER_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
PASS=0; FAIL=0

ok()   { echo "PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }

# Runs a python snippet with sys.platform forced to $1 before importing the
# module named by $2 from $3 (one or more :-separated directories added to
# sys.path — _zed_common.py needs both hooks/ and core/ since it imports
# path_hash from snapshot_revert.py).
run_forced() {
    local plat="$1" mod="$2" dirs="$3" code="$4"
    python3 -c "
import sys
sys.platform = '$plat'
for d in '$dirs'.split(':'):
    sys.path.insert(0, d)
import importlib
mod = importlib.import_module('$mod')
$code
"
}

# _zed_common.py: BUNDLED_ZED_CLI per platform
out=$(run_forced darwin _zed_common "$ADAPTER_DIR/hooks:$ADAPTER_DIR/../core" "print(mod.BUNDLED_ZED_CLI)")
[ "$out" = "/Applications/Zed.app/Contents/MacOS/cli" ] && ok "_zed_common: darwin BUNDLED_ZED_CLI" || fail "_zed_common: darwin BUNDLED_ZED_CLI got '$out'"

out=$(run_forced linux _zed_common "$ADAPTER_DIR/hooks:$ADAPTER_DIR/../core" "print(mod.BUNDLED_ZED_CLI)")
expected="$HOME/.local/bin/zed"
[ "$out" = "$expected" ] && ok "_zed_common: linux BUNDLED_ZED_CLI" || fail "_zed_common: linux BUNDLED_ZED_CLI got '$out' want '$expected'"

# install.py: BUNDLED_ZED_CLI + WATCHER_BIN per platform
out=$(run_forced darwin install "$ADAPTER_DIR" "print(mod.BUNDLED_ZED_CLI); print(mod.WATCHER_BIN)")
if echo "$out" | grep -q "/Applications/Zed.app/Contents/MacOS/cli" && echo "$out" | grep -q "^fswatch$"; then
    ok "install.py: darwin BUNDLED_ZED_CLI + WATCHER_BIN"
else
    fail "install.py: darwin got '$out'"
fi

out=$(run_forced linux install "$ADAPTER_DIR" "print(mod.BUNDLED_ZED_CLI); print(mod.WATCHER_BIN)")
if echo "$out" | grep -q "\.local/bin/zed" && echo "$out" | grep -q "^inotifywait$"; then
    ok "install.py: linux BUNDLED_ZED_CLI + WATCHER_BIN"
else
    fail "install.py: linux got '$out'"
fi

# prune_stale_roots.py: DEFAULT_DB per platform
out=$(run_forced darwin prune_stale_roots "$ADAPTER_DIR" "print(mod.DEFAULT_DB)")
case "$out" in
    */Library/Application\ Support/Zed/db/0-stable/db.sqlite) ok "prune_stale_roots: darwin DEFAULT_DB" ;;
    *) fail "prune_stale_roots: darwin got '$out'" ;;
esac

out=$(run_forced linux prune_stale_roots "$ADAPTER_DIR" "print(mod.DEFAULT_DB)")
case "$out" in
    */.local/share/zed/db/0-stable/db.sqlite) ok "prune_stale_roots: linux DEFAULT_DB" ;;
    *) fail "prune_stale_roots: linux got '$out'" ;;
esac

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
