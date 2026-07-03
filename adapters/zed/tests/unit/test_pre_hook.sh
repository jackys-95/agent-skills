#!/usr/bin/env bash
# Unit tests for pre_edit_zed_snapshot.py
set -euo pipefail

HOOK="$(dirname "$0")/../../hooks/pre_edit_zed_snapshot.py"
PASS=0; FAIL=0
SID="testsession1"

ok()   { echo "PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }

hash_of() { python3 -c "import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:16])" "$1"; }

# 1a: no env var — silent, exit 0
out=$(echo '{"tool_input":{"file_path":"/tmp/testfile.txt"}}' | env -u CC_ZED_HOOK python3 "$HOOK" 2>&1)
code=$?
[ $code -eq 0 ] && [ -z "$out" ] && ok "1a: no env var → silent exit 0" || fail "1a: got exit=$code output='$out'"

# 1b: new file (does not exist yet — Write creating it) → /dev/null pointer recorded
# and a new-file [Zed] line printed, so the file is revertible (delete) and diffable.
newf="/tmp/zed_newfile_test.txt"
newptr="/tmp/cc_pre_ptr_$(hash_of "$newf")"
rm -f "$newf" "$newptr"
out=$(CC_ZED_HOOK=1 python3 "$HOOK" <<< "{\"session_id\":\"newsess\",\"tool_input\":{\"file_path\":\"$newf\"}}" 2>&1)
code=$?
if [ $code -eq 0 ] && echo "$out" | grep -q 'new file' && [ "$(cat "$newptr" 2>/dev/null)" = "/dev/null" ]; then
    ok "1b: new file → /dev/null pointer recorded, revertible"
else
    fail "1b: exit=$code out='$out' ptr='$(cat "$newptr" 2>/dev/null)'"
fi
rm -f "$newptr"

# 1c: happy path — snapshot written, [Zed] line includes snapshot path
echo "original content" > /tmp/zed_test_file.txt
out=$(CC_ZED_HOOK=1 python3 "$HOOK" <<< "{\"session_id\":\"$SID\",\"tool_input\":{\"file_path\":\"/tmp/zed_test_file.txt\"}}" 2>&1)
code=$?
snapshot=$(echo "$out" | grep -o 'snapshot=[^ |]*' | cut -d= -f2)
if [ $code -eq 0 ] && echo "$out" | grep -q '\[Zed\]' && [ -f "$snapshot" ] && [ "$(cat "$snapshot")" = "original content" ]; then
    ok "1c: happy path → snapshot written, [Zed] line correct"
else
    fail "1c: exit=$code out='$out' snapshot='$snapshot'"
fi

# 1d: same file edited twice IN ONE TURN — base kept from first edit. The turn
# marker (dropped by the post-hook) makes the second pre-hook call a no-op, so the
# pointer still points at the first snapshot and its original content is preserved.
fhash=$(hash_of /tmp/zed_test_file.txt)
marker="/tmp/cc_zed_seen_${SID}_${fhash}"
echo "/tmp/zed_test_file.txt" > "$marker"       # simulate post-hook having queued it
echo "second edit content" > /tmp/zed_test_file.txt
out2=$(CC_ZED_HOOK=1 python3 "$HOOK" <<< "{\"session_id\":\"$SID\",\"tool_input\":{\"file_path\":\"/tmp/zed_test_file.txt\"}}" 2>&1)
pointer="/tmp/cc_pre_ptr_${fhash}"
kept=$(cat "$(cat "$pointer")" 2>/dev/null)
if [ -z "$out2" ] && [ "$kept" = "original content" ]; then
    ok "1d: same file twice in a turn → first snapshot kept as base, second is no-op"
else
    fail "1d: out2='$out2' kept='$kept'"
fi

# 1e: binary file — no crash (fresh session so no marker suppresses it)
printf '\x00\x01\x02\xff\xfe' > /tmp/zed_binary_test.bin
out=$(CC_ZED_HOOK=1 python3 "$HOOK" <<< '{"session_id":"binsess","tool_input":{"file_path":"/tmp/zed_binary_test.bin"}}' 2>&1)
code=$?
[ $code -eq 0 ] && ok "1e: binary file → no crash" || fail "1e: exit=$code out='$out'"

# Cleanup
rm -f /tmp/zed_test_file.txt /tmp/zed_binary_test.bin "$marker"
rm -f /tmp/cc_pre_${fhash}_* "/tmp/cc_pre_ptr_${fhash}"
binhash=$(hash_of /tmp/zed_binary_test.bin)
rm -f /tmp/cc_pre_${binhash}_* "/tmp/cc_pre_ptr_${binhash}"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
