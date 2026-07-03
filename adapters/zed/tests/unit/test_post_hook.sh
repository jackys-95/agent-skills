#!/usr/bin/env bash
# Unit tests for post_edit_open_in_zed.py — now records the turn manifest marker
# (the diff open moved to the Stop hook). No `zed` launch happens here.
set -euo pipefail

HOOK="$(dirname "$0")/../../hooks/post_edit_open_in_zed.py"
PASS=0; FAIL=0
SID="postsess"

ok()   { echo "PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }

hash_of() { python3 -c "import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:16])" "$1"; }

# 2a: no env var — silent, exit 0
out=$(echo '{"tool_input":{"file_path":"/tmp/zed_test_file.txt"}}' | env -u CC_ZED_HOOK python3 "$HOOK" 2>&1)
code=$?
[ $code -eq 0 ] && [ -z "$out" ] && ok "2a: no env var → silent exit 0" || fail "2a: got exit=$code output='$out'"

# 2b: edit recorded — drops a per-(session,file) marker containing the file path
fpath="/tmp/zed_test_file.txt"
fhash=$(hash_of "$fpath")
marker="/tmp/cc_zed_seen_${SID}_${fhash}"
rm -f "$marker"
out=$(CC_ZED_HOOK=1 python3 "$HOOK" <<< "{\"session_id\":\"$SID\",\"tool_input\":{\"file_path\":\"$fpath\"}}" 2>&1)
code=$?
if [ $code -eq 0 ] && [ -f "$marker" ] && [ "$(cat "$marker")" = "$fpath" ]; then
    ok "2b: edit recorded → marker written with file path"
else
    fail "2b: exit=$code marker=$(cat "$marker" 2>/dev/null)"
fi

# 2c: new file (never existed at pre-time) — still recorded. The post-hook does not
# require the file to exist, so a Write-created file joins the turn manifest.
newpath="/tmp/zed_new_file_xyz.txt"
newhash=$(hash_of "$newpath")
newmarker="/tmp/cc_zed_seen_${SID}_${newhash}"
rm -f "$newmarker"
out=$(CC_ZED_HOOK=1 python3 "$HOOK" <<< "{\"session_id\":\"$SID\",\"tool_input\":{\"file_path\":\"$newpath\"}}" 2>&1)
code=$?
if [ $code -eq 0 ] && [ -f "$newmarker" ] && [ "$(cat "$newmarker")" = "$newpath" ]; then
    ok "2c: new file → still recorded in manifest"
else
    fail "2c: exit=$code marker=$(cat "$newmarker" 2>/dev/null)"
fi

# Cleanup
rm -f "$marker" "$newmarker"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
