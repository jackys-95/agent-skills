#!/usr/bin/env bash
# Unit tests for reset_zed_turn.py — clears the session's manifest at turn start.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK="$DIR/../../hooks/reset_zed_turn.py"
export PYTHONPATH="$DIR/../../../core:${PYTHONPATH:-}"
PASS=0; FAIL=0
SID="resetsess"
OTHER="othersess"

ok()   { echo "PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }

manifest_of() { echo "/tmp/cc_zed_manifest_$1.json"; }

# 4a: no env var — silent, exit 0, manifest untouched
manifest=$(manifest_of "$SID")
echo '{"entries":{}}' > "$manifest"
out=$(echo "{\"session_id\":\"$SID\"}" | env -u CC_ZED_HOOK python3 "$HOOK" 2>&1)
code=$?
if [ $code -eq 0 ] && [ -z "$out" ] && [ -f "$manifest" ]; then
    ok "4a: no env var → silent, manifest untouched"
else
    fail "4a: exit=$code out='$out'"
fi

# 4b: clears this session's manifest only — another session's manifest survives
other_manifest=$(manifest_of "$OTHER")
echo '{"entries":{}}' > "$manifest"
echo '{"entries":{}}' > "$other_manifest"
CC_ZED_HOOK=1 python3 "$HOOK" <<< "{\"session_id\":\"$SID\"}" > /dev/null 2>&1
if [ ! -f "$manifest" ] && [ -f "$other_manifest" ]; then
    ok "4b: clears own session's manifest, leaves other session's intact"
else
    fail "4b: this_exists=$([ -f "$manifest" ] && echo yes || echo no) other_exists=$([ -f "$other_manifest" ] && echo yes || echo no)"
fi

# Cleanup
rm -f "$manifest" "$other_manifest"
rm -rf "/tmp/cc_zed_snap_${SID}" "/tmp/cc_zed_snap_${OTHER}"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
