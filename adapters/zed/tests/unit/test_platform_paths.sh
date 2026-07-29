#!/usr/bin/env bash
# Unit tests for the darwin/linux platform branches added for Linux support
# (_zed_common.py, install.py, prune_stale_roots.py, tmux_diff_injector.py).
set -euo pipefail

ADAPTER_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
PASS=0; FAIL=0

ok()   { echo "PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }

# Runs a python snippet with sys.platform forced to $1 before importing the
# module named by $2 from $3 (a directory added to sys.path).
run_forced() {
    local plat="$1" mod="$2" dir="$3" code="$4"
    python3 -c "
import sys
sys.platform = '$plat'
sys.path.insert(0, '$dir')
import importlib
mod = importlib.import_module('$mod')
$code
"
}

# _zed_common.py: BUNDLED_ZED_CLI per platform
out=$(run_forced darwin _zed_common "$ADAPTER_DIR/hooks" "print(mod.BUNDLED_ZED_CLI)")
[ "$out" = "/Applications/Zed.app/Contents/MacOS/cli" ] && ok "_zed_common: darwin BUNDLED_ZED_CLI" || fail "_zed_common: darwin BUNDLED_ZED_CLI got '$out'"

out=$(run_forced linux _zed_common "$ADAPTER_DIR/hooks" "print(mod.BUNDLED_ZED_CLI)")
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

# tmux_diff_injector.py: WATCH_CMD per platform. The module runs top-level watch
# logic on import (it expects argv[1]/argv[3]/argv[4] and blocks on the watcher
# binary), so exercise it as a subprocess against a fake, instant-exit watcher
# binary placed first on PATH rather than importing it in-process.
tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

# The fake watcher logs its argv, then mutates the watched file (its last arg)
# so tmux_diff_injector.py's before/after check sees a change and exits its
# watch loop on the first pass instead of spinning for the full 120s timeout.
cat > "$tmpdir/fswatch" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" > "$FAKE_WATCH_LOG"
echo "changed" >> "${@: -1}"
exit 0
EOF
cat > "$tmpdir/inotifywait" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" > "$FAKE_WATCH_LOG"
echo "changed" >> "${@: -1}"
exit 0
EOF
chmod +x "$tmpdir/fswatch" "$tmpdir/inotifywait"

target="/tmp/zed_platform_test_target.txt"
: > "$target"
log="$tmpdir/watch_log"

FAKE_WATCH_LOG="$log" PATH="$tmpdir:$PATH" python3 -c "
import sys
sys.platform = 'darwin'
sys.argv = ['tmux_diff_injector.py', '$target', 'ignored', 'testpane', 'gen1']
sys.path.insert(0, '$ADAPTER_DIR/hooks')
exec(open('$ADAPTER_DIR/hooks/tmux_diff_injector.py').read())
" >/dev/null 2>&1 || true
out=$(cat "$log" 2>/dev/null || echo "")
if echo "$out" | grep -q -- "-1 $target"; then
    ok "tmux_diff_injector: darwin uses fswatch -1 <file>"
else
    fail "tmux_diff_injector: darwin got '$out'"
fi
rm -f "$log"
: > "$target"

FAKE_WATCH_LOG="$log" PATH="$tmpdir:$PATH" python3 -c "
import sys
sys.platform = 'linux'
sys.argv = ['tmux_diff_injector.py', '$target', 'ignored', 'testpane', 'gen1']
sys.path.insert(0, '$ADAPTER_DIR/hooks')
exec(open('$ADAPTER_DIR/hooks/tmux_diff_injector.py').read())
" >/dev/null 2>&1 || true
out=$(cat "$log" 2>/dev/null || echo "")
if echo "$out" | grep -q -- "-e modify -e close_write $target"; then
    ok "tmux_diff_injector: linux uses inotifywait -e modify -e close_write <file>"
else
    fail "tmux_diff_injector: linux got '$out'"
fi

rm -f "$target"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
