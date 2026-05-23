#!/usr/bin/env bash
# Unit tests for pre_edit_zed_snapshot.py
set -euo pipefail

HOOK="$(dirname "$0")/../../hooks/pre_edit_zed_snapshot.py"
PASS=0; FAIL=0

ok()   { echo "PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }

# 1a: no env var — silent, exit 0
out=$(echo '{"tool_input":{"file_path":"/tmp/testfile.txt"}}' | env -u CC_ZED_HOOK python3 "$HOOK" 2>&1)
code=$?
[ $code -eq 0 ] && [ -z "$out" ] && ok "1a: no env var → silent exit 0" || fail "1a: got exit=$code output='$out'"

# 1b: nonexistent file — silent, exit 0
out=$(CC_ZED_HOOK=1 python3 "$HOOK" <<< '{"tool_input":{"file_path":"/tmp/nonexistent_xyz_abc.txt"}}' 2>&1)
code=$?
[ $code -eq 0 ] && [ -z "$out" ] && ok "1b: nonexistent file → silent exit 0" || fail "1b: got exit=$code output='$out'"

# 1c: happy path — snapshot written, [Zed] line includes snapshot path
echo "original content" > /tmp/zed_test_file.txt
out=$(CC_ZED_HOOK=1 python3 "$HOOK" <<< '{"tool_input":{"file_path":"/tmp/zed_test_file.txt"}}' 2>&1)
code=$?
snapshot=$(echo "$out" | grep -o 'snapshot=[^ |]*' | cut -d= -f2)
if [ $code -eq 0 ] && echo "$out" | grep -q '\[Zed\]' && [ -f "$snapshot" ] && [ "$(cat "$snapshot")" = "original content" ]; then
    ok "1c: happy path → snapshot written, [Zed] line correct"
else
    fail "1c: exit=$code out='$out' snapshot='$snapshot'"
fi

# 1d: same file edited twice — unique snapshot paths, pointer updated to latest
out2=$(CC_ZED_HOOK=1 python3 "$HOOK" <<< '{"tool_input":{"file_path":"/tmp/zed_test_file.txt"}}' 2>&1)
snap2=$(echo "$out2" | grep -o 'snapshot=[^ |]*' | cut -d= -f2)
path_hash=$(python3 -c "import hashlib; print(hashlib.sha256(b'/tmp/zed_test_file.txt').hexdigest()[:16])")
pointer="/tmp/cc_pre_ptr_${path_hash}"
if [ "$snapshot" != "$snap2" ] && [ -f "$pointer" ] && [ "$(cat "$pointer")" = "$snap2" ]; then
    ok "1d: same file twice → unique snapshots, pointer updated to latest"
else
    fail "1d: snap1=$snapshot snap2=$snap2 pointer=$(cat "$pointer" 2>/dev/null)"
fi

# 1e: binary file — no crash
printf '\x00\x01\x02\xff\xfe' > /tmp/zed_binary_test.bin
out=$(CC_ZED_HOOK=1 python3 "$HOOK" <<< '{"tool_input":{"file_path":"/tmp/zed_binary_test.bin"}}' 2>&1)
code=$?
[ $code -eq 0 ] && ok "1e: binary file → no crash" || fail "1e: exit=$code out='$out'"

# Cleanup
rm -f /tmp/zed_test_file.txt /tmp/zed_binary_test.bin
rm -f /tmp/cc_pre_$(python3 -c "import hashlib; print(hashlib.sha256(b'/tmp/zed_test_file.txt').hexdigest()[:16])")_*
rm -f /tmp/cc_pre_ptr_$(python3 -c "import hashlib; print(hashlib.sha256(b'/tmp/zed_test_file.txt').hexdigest()[:16])")
rm -f /tmp/cc_pre_$(python3 -c "import hashlib; print(hashlib.sha256(b'/tmp/zed_binary_test.bin').hexdigest()[:16])")_*
rm -f /tmp/cc_pre_ptr_$(python3 -c "import hashlib; print(hashlib.sha256(b'/tmp/zed_binary_test.bin').hexdigest()[:16])")

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
