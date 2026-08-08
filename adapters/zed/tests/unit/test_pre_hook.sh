#!/usr/bin/env bash
# Unit tests for pre_edit_zed_snapshot.py
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK="$DIR/../../hooks/pre_edit_zed_snapshot.py"
export PYTHONPATH="$DIR/../../../core:${PYTHONPATH:-}"
PASS=0; FAIL=0
SID="testsession1"

ok()   { echo "PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }

manifest_of() { echo "/tmp/cc_zed_manifest_$1.json"; }
base_of() {
    python3 -c "
import hashlib, json, sys
try:
    data = json.load(open(sys.argv[1]))
except (OSError, ValueError):
    print('')
    raise SystemExit
h = hashlib.sha256(sys.argv[2].encode()).hexdigest()[:16]
print(data.get('entries', {}).get(h, {}).get('base', ''))
" "$1" "$2"
}

# 1a: no env var — silent, exit 0
out=$(echo '{"tool_input":{"file_path":"/tmp/testfile.txt"}}' | env -u CC_ZED_HOOK python3 "$HOOK" 2>&1)
code=$?
[ $code -eq 0 ] && [ -z "$out" ] && ok "1a: no env var → silent exit 0" || fail "1a: got exit=$code output='$out'"

# 1b: new file (does not exist yet — Write creating it) → "new" base recorded and a
# new-file [Zed] line printed, so the file is revertible (delete) and diffable.
newf="/tmp/zed_newfile_test.txt"
manifest=$(manifest_of "newsess")
rm -f "$newf" "$manifest"
out=$(CC_ZED_HOOK=1 python3 "$HOOK" <<< "{\"session_id\":\"newsess\",\"tool_input\":{\"file_path\":\"$newf\"}}" 2>&1)
code=$?
base=$(base_of "$manifest" "$newf")
if [ $code -eq 0 ] && echo "$out" | grep -q 'new file' && [ "$base" = "new" ]; then
    ok "1b: new file → 'new' base recorded, revertible"
else
    fail "1b: exit=$code out='$out' base='$base'"
fi
rm -f "$manifest"

# 1c: happy path — snapshot written, [Zed] line includes snapshot path
manifest=$(manifest_of "$SID")
rm -f "$manifest"
echo "original content" > /tmp/zed_test_file.txt
out=$(CC_ZED_HOOK=1 python3 "$HOOK" <<< "{\"session_id\":\"$SID\",\"tool_input\":{\"file_path\":\"/tmp/zed_test_file.txt\"}}" 2>&1)
code=$?
snapshot=$(echo "$out" | grep -o 'snapshot=[^ |]*' | cut -d= -f2)
if [ $code -eq 0 ] && echo "$out" | grep -q '\[Zed\]' && [ -f "$snapshot" ] && [ "$(cat "$snapshot")" = "original content" ]; then
    ok "1c: happy path → snapshot written, [Zed] line correct"
else
    fail "1c: exit=$code out='$out' snapshot='$snapshot'"
fi

# 1d: same file edited twice IN ONE TURN — base kept from first edit. Self-contained
# session so it doesn't depend on 1c's leftover state.
SID_D="testsession1d"
manifest_d=$(manifest_of "$SID_D")
rm -f "$manifest_d"
echo "first edit content" > /tmp/zed_test_file_1d.txt
CC_ZED_HOOK=1 python3 "$HOOK" <<< "{\"session_id\":\"$SID_D\",\"tool_input\":{\"file_path\":\"/tmp/zed_test_file_1d.txt\"}}" > /dev/null
echo "second edit content" > /tmp/zed_test_file_1d.txt
out2=$(CC_ZED_HOOK=1 python3 "$HOOK" <<< "{\"session_id\":\"$SID_D\",\"tool_input\":{\"file_path\":\"/tmp/zed_test_file_1d.txt\"}}" 2>&1)
base_d=$(base_of "$manifest_d" "/tmp/zed_test_file_1d.txt")
kept=$(cat "$base_d" 2>/dev/null)
if [ -z "$out2" ] && [ "$kept" = "first edit content" ]; then
    ok "1d: same file twice in a turn → first snapshot kept as base, second is no-op"
else
    fail "1d: out2='$out2' kept='$kept'"
fi

# 1e: binary file — no crash (fresh session so no existing entry suppresses it)
printf '\x00\x01\x02\xff\xfe' > /tmp/zed_binary_test.bin
out=$(CC_ZED_HOOK=1 python3 "$HOOK" <<< '{"session_id":"binsess","tool_input":{"file_path":"/tmp/zed_binary_test.bin"}}' 2>&1)
code=$?
[ $code -eq 0 ] && ok "1e: binary file → no crash" || fail "1e: exit=$code out='$out'"

# Cleanup
hash_of() { python3 -c "import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:16])" "$1"; }
rm -f /tmp/zed_test_file.txt /tmp/zed_test_file_1d.txt /tmp/zed_binary_test.bin
rm -f "$manifest" "$manifest_d" "$(manifest_of binsess)"
rm -rf "/tmp/cc_zed_snap_${SID}" "/tmp/cc_zed_snap_${SID_D}" /tmp/cc_zed_snap_binsess
rm -f "/tmp/cc_zed_ptr_$(hash_of "$newf")" "/tmp/cc_zed_ptr_$(hash_of /tmp/zed_test_file.txt)" \
      "/tmp/cc_zed_ptr_$(hash_of /tmp/zed_test_file_1d.txt)" "/tmp/cc_zed_ptr_$(hash_of /tmp/zed_binary_test.bin)"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
