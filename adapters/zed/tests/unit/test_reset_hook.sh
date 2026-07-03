#!/usr/bin/env bash
# Unit tests for reset_zed_turn.py — clears the session's turn markers at turn start.
set -euo pipefail

HOOK="$(dirname "$0")/../../hooks/reset_zed_turn.py"
PASS=0; FAIL=0
SID="resetsess"
OTHER="othersess"

ok()   { echo "PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }

# 4a: no env var — silent, exit 0, markers untouched
touch "/tmp/cc_zed_seen_${SID}_deadbeef00000000"
out=$(echo "{\"session_id\":\"$SID\"}" | env -u CC_ZED_HOOK python3 "$HOOK" 2>&1)
code=$?
if [ $code -eq 0 ] && [ -z "$out" ] && [ -f "/tmp/cc_zed_seen_${SID}_deadbeef00000000" ]; then
    ok "4a: no env var → silent, markers untouched"
else
    fail "4a: exit=$code out='$out'"
fi

# 4b: clears this session's markers only — another session's markers survive
touch "/tmp/cc_zed_seen_${SID}_aaaa000000000000" "/tmp/cc_zed_seen_${SID}_bbbb000000000000"
touch "/tmp/cc_zed_seen_${OTHER}_cccc000000000000"
CC_ZED_HOOK=1 python3 "$HOOK" <<< "{\"session_id\":\"$SID\"}" > /dev/null 2>&1
shopt -s nullglob
this_arr=(/tmp/cc_zed_seen_${SID}_*); this_left=${#this_arr[@]}
other_arr=(/tmp/cc_zed_seen_${OTHER}_*); other_left=${#other_arr[@]}
shopt -u nullglob
if [ "$this_left" = "0" ] && [ "$other_left" = "1" ]; then
    ok "4b: clears own session markers, leaves other session's intact"
else
    fail "4b: this_left=$this_left other_left=$other_left"
fi

# Cleanup
rm -f /tmp/cc_zed_seen_${SID}_* /tmp/cc_zed_seen_${OTHER}_*

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
