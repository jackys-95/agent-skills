#!/usr/bin/env bash
# Unit tests for post_edit_open_in_zed.py — confirms the edit is queued in the shared
# manifest (the diff open moved to the Stop hook). No `zed` launch happens here.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK="$DIR/../../hooks/post_edit_open_in_zed.py"
export PYTHONPATH="$DIR/../../../core:${PYTHONPATH:-}"
PASS=0; FAIL=0
SID="postsess"

ok()   { echo "PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }

manifest_of() { echo "/tmp/cc_zed_manifest_$1.json"; }
has_entry() {
    python3 -c "
import hashlib, json, sys
try:
    data = json.load(open(sys.argv[1]))
except (OSError, ValueError):
    print('no')
    raise SystemExit
h = hashlib.sha256(sys.argv[2].encode()).hexdigest()[:16]
print('yes' if h in data.get('entries', {}) else 'no')
" "$1" "$2"
}

# 2a: no env var — silent, exit 0
out=$(echo '{"tool_input":{"file_path":"/tmp/zed_test_file.txt"}}' | env -u CC_ZED_HOOK python3 "$HOOK" 2>&1)
code=$?
[ $code -eq 0 ] && [ -z "$out" ] && ok "2a: no env var → silent exit 0" || fail "2a: got exit=$code output='$out'"

# 2b: edit recorded — queues an entry for the file in the session's manifest
fpath="/tmp/zed_test_file.txt"
echo "content" > "$fpath"
manifest=$(manifest_of "$SID")
rm -f "$manifest"
out=$(CC_ZED_HOOK=1 python3 "$HOOK" <<< "{\"session_id\":\"$SID\",\"tool_input\":{\"file_path\":\"$fpath\"}}" 2>&1)
code=$?
if [ $code -eq 0 ] && [ "$(has_entry "$manifest" "$fpath")" = "yes" ]; then
    ok "2b: edit recorded → manifest entry written"
else
    fail "2b: exit=$code entry=$(has_entry "$manifest" "$fpath")"
fi

# 2c: new file (never existed at pre-time) — still recorded. The post-hook does not
# require the file to exist, so a Write-created file joins the turn manifest.
newpath="/tmp/zed_new_file_xyz.txt"
rm -f "$newpath"
out=$(CC_ZED_HOOK=1 python3 "$HOOK" <<< "{\"session_id\":\"$SID\",\"tool_input\":{\"file_path\":\"$newpath\"}}" 2>&1)
code=$?
if [ $code -eq 0 ] && [ "$(has_entry "$manifest" "$newpath")" = "yes" ]; then
    ok "2c: new file → still recorded in manifest"
else
    fail "2c: exit=$code entry=$(has_entry "$manifest" "$newpath")"
fi

# Cleanup
hash_of() { python3 -c "import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:16])" "$1"; }
rm -f "$fpath" "$manifest"
rm -rf "/tmp/cc_zed_snap_${SID}"
rm -f "/tmp/cc_zed_ptr_$(hash_of "$fpath")" "/tmp/cc_zed_ptr_$(hash_of "$newpath")"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
