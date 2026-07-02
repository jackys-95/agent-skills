#!/usr/bin/env bash
# Unit tests for post_edit_open_in_zed.py
set -euo pipefail

HOOK="$(dirname "$0")/../../hooks/post_edit_open_in_zed.py"
PASS=0; FAIL=0

ok()   { echo "PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }

# 2a: no env var — silent, exit 0
out=$(echo '{"tool_input":{"file_path":"/tmp/zed_test_file.txt"}}' | env -u CC_ZED_HOOK python3 "$HOOK" 2>&1)
code=$?
[ $code -eq 0 ] && [ -z "$out" ] && ok "2a: no env var → silent exit 0" || fail "2a: got exit=$code output='$out'"

# Shim a fake `zed` on PATH that records its argv, so we can assert the flags the
# hook passes (real `zed` may not be installed in CI, and we must never launch it).
SHIM_DIR=$(mktemp -d)
ZED_ARGS_LOG="$SHIM_DIR/zed_args.log"
cat > "$SHIM_DIR/zed" <<SHIM
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$ZED_ARGS_LOG"
SHIM
chmod +x "$SHIM_DIR/zed"

# 2b: snapshot present — launches `zed -a --diff <snapshot> <file>`. The `-a`/--add
# flag pins the diff to the active workspace so out-of-project diffs don't swap the
# window's project (see docs/zed-diff-hook-window-swap-fix.md).
echo "original" > /tmp/zed_test_file.txt
PRE_HOOK="$(dirname "$0")/../../hooks/pre_edit_zed_snapshot.py"
CC_ZED_HOOK=1 python3 "$PRE_HOOK" <<< '{"tool_input":{"file_path":"/tmp/zed_test_file.txt"}}' > /dev/null
echo "modified" > /tmp/zed_test_file.txt
: > "$ZED_ARGS_LOG"
out=$(CC_ZED_HOOK=1 PATH="$SHIM_DIR:$PATH" python3 "$HOOK" <<< '{"tool_input":{"file_path":"/tmp/zed_test_file.txt"}}' 2>&1)
code=$?
args=$(cat "$ZED_ARGS_LOG" 2>/dev/null)
if [ $code -eq 0 ] && echo "$args" | grep -q -- '-a --diff'; then
  ok "2b: snapshot present → launches 'zed -a --diff' (args: $args)"
else
  fail "2b: exit=$code args='$args' out='$out'"
fi

# 2c: no snapshot — falls back to `zed -a <file>` (still -a so the fallback open
# doesn't swap the project either).
path_hash=$(python3 -c "import hashlib; print(hashlib.sha256(b'/tmp/zed_test_file.txt').hexdigest()[:16])")
rm -f "/tmp/cc_pre_ptr_${path_hash}"
: > "$ZED_ARGS_LOG"
out=$(CC_ZED_HOOK=1 PATH="$SHIM_DIR:$PATH" python3 "$HOOK" <<< '{"tool_input":{"file_path":"/tmp/zed_test_file.txt"}}' 2>&1)
code=$?
args=$(cat "$ZED_ARGS_LOG" 2>/dev/null)
if [ $code -eq 0 ] && echo "$args" | grep -q -- '-a ' && ! echo "$args" | grep -q -- '--diff'; then
  ok "2c: no snapshot → fallback launches 'zed -a <file>' (args: $args)"
else
  fail "2c: exit=$code args='$args' out='$out'"
fi

# Cleanup
rm -f /tmp/zed_test_file.txt
rm -rf "$SHIM_DIR"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
