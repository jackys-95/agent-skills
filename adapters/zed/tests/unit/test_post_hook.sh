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

# 2b: snapshot present — opens zed --diff (non-blocking, no crash)
echo "original" > /tmp/zed_test_file.txt
PRE_HOOK="$(dirname "$0")/../../hooks/pre_edit_zed_snapshot.py"
CC_ZED_HOOK=1 python3 "$PRE_HOOK" <<< '{"tool_input":{"file_path":"/tmp/zed_test_file.txt"}}' > /dev/null
echo "modified" > /tmp/zed_test_file.txt
out=$(CC_ZED_HOOK=1 python3 "$HOOK" <<< '{"tool_input":{"file_path":"/tmp/zed_test_file.txt"}}' 2>&1)
code=$?
[ $code -eq 0 ] && ok "2b: snapshot present → exits 0 (zed --diff launched)" || fail "2b: exit=$code out='$out'"

# 2c: no snapshot — falls back to zed <file> (no crash)
path_hash=$(python3 -c "import hashlib; print(hashlib.sha256(b'/tmp/zed_test_file.txt').hexdigest()[:16])")
rm -f "/tmp/cc_pre_ptr_${path_hash}"
out=$(CC_ZED_HOOK=1 python3 "$HOOK" <<< '{"tool_input":{"file_path":"/tmp/zed_test_file.txt"}}' 2>&1)
code=$?
[ $code -eq 0 ] && ok "2c: no snapshot → fallback exits 0 (zed file launched)" || fail "2c: exit=$code out='$out'"

# Cleanup
rm -f /tmp/zed_test_file.txt

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
