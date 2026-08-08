#!/usr/bin/env bash
# Unit tests for stop_flush_zed_diffs.py — flushes the turn's manifest into ONE
# `zed -a --diff ... --diff ...` multi-diff and clears the manifest.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK="$DIR/../../hooks/stop_flush_zed_diffs.py"
PRE_HOOK="$DIR/../../hooks/pre_edit_zed_snapshot.py"
POST_HOOK="$DIR/../../hooks/post_edit_open_in_zed.py"
export PYTHONPATH="$DIR/../../../core:${PYTHONPATH:-}"
PASS=0; FAIL=0
SID="stopsess"

ok()   { echo "PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }

hash_of() { python3 -c "import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:16])" "$1"; }
wait_for_log() { for _ in $(seq 1 40); do [ -s "$1" ] && return 0; sleep 0.05; done; return 1; }
manifest_of() { echo "/tmp/cc_zed_manifest_$1.json"; }

# Shim a fake `zed` on PATH that records its argv (never launch real Zed in CI).
SHIM_DIR=$(mktemp -d)
ZED_ARGS_LOG="$SHIM_DIR/zed_args.log"
cat > "$SHIM_DIR/zed" <<SHIM
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$ZED_ARGS_LOG"
SHIM
chmod +x "$SHIM_DIR/zed"

manifest=$(manifest_of "$SID")
rm -f "$manifest"

# 3a: no env var — silent, exit 0
out=$(echo '{"session_id":"'"$SID"'"}' | env -u CC_ZED_HOOK python3 "$HOOK" 2>&1)
code=$?
[ $code -eq 0 ] && [ -z "$out" ] && ok "3a: no env var → silent exit 0" || fail "3a: exit=$code out='$out'"

# 3b: empty manifest — silent, exit 0, no zed launch
: > "$ZED_ARGS_LOG"
out=$(CC_ZED_HOOK=1 PATH="$SHIM_DIR:$PATH" python3 "$HOOK" <<< "{\"session_id\":\"$SID\"}" 2>&1)
code=$?
if [ $code -eq 0 ] && [ ! -s "$ZED_ARGS_LOG" ]; then
    ok "3b: empty manifest → no zed launch"
else
    fail "3b: exit=$code args=$(cat "$ZED_ARGS_LOG")"
fi

# 3c: two edited files (one with snapshot, one new) → ONE multi-diff with two
# --diff pairs; new file diffs against /dev/null; manifest cleared afterward.
f1="/tmp/zed_stop_f1.txt"; f2="/tmp/zed_stop_f2.txt"
rm -f "$f2"
echo "orig1" > "$f1"
# f1: full pre→post→edit cycle so it has a real snapshot base
CC_ZED_HOOK=1 python3 "$PRE_HOOK"  <<< "{\"session_id\":\"$SID\",\"tool_input\":{\"file_path\":\"$f1\"}}" > /dev/null
CC_ZED_HOOK=1 python3 "$POST_HOOK" <<< "{\"session_id\":\"$SID\",\"tool_input\":{\"file_path\":\"$f1\"}}" > /dev/null
echo "changed1" > "$f1"
# f2: new file — the pre-hook runs before it exists (base="new"), then it's created
# and the post-hook confirms the queue entry.
CC_ZED_HOOK=1 python3 "$PRE_HOOK"  <<< "{\"session_id\":\"$SID\",\"tool_input\":{\"file_path\":\"$f2\"}}" > /dev/null
echo "created2" > "$f2"
CC_ZED_HOOK=1 python3 "$POST_HOOK" <<< "{\"session_id\":\"$SID\",\"tool_input\":{\"file_path\":\"$f2\"}}" > /dev/null

: > "$ZED_ARGS_LOG"
out=$(CC_ZED_HOOK=1 PATH="$SHIM_DIR:$PATH" python3 "$HOOK" <<< "{\"session_id\":\"$SID\"}" 2>&1)
code=$?
wait_for_log "$ZED_ARGS_LOG"
args=$(cat "$ZED_ARGS_LOG" 2>/dev/null)
# Expect: -a, both files present, two --diff occurrences, /dev/null for the new file.
ndiff=$(grep -o -- '--diff' <<< "$args" | wc -l | tr -d ' ')
if [ $code -eq 0 ] \
   && grep -q -- '-a' <<< "$args" \
   && [ "$ndiff" = "2" ] \
   && grep -q -- "$f1" <<< "$args" \
   && grep -q -- "/dev/null $f2" <<< "$args"; then
    ok "3c: multi-file turn → one multi-diff, two --diff pairs, new file vs /dev/null"
else
    fail "3c: exit=$code ndiff=$ndiff args='$args'"
fi

# 3d: manifest cleared after flush — a second Stop is a no-op
: > "$ZED_ARGS_LOG"
CC_ZED_HOOK=1 PATH="$SHIM_DIR:$PATH" python3 "$HOOK" <<< "{\"session_id\":\"$SID\"}" > /dev/null 2>&1
if [ ! -s "$ZED_ARGS_LOG" ] && [ ! -f "$manifest" ]; then
    ok "3d: manifest cleared → second Stop is a no-op"
else
    fail "3d: leftover manifest or zed relaunched (args=$(cat "$ZED_ARGS_LOG"))"
fi

# Cleanup
f1hash=$(hash_of "$f1"); f2hash=$(hash_of "$f2")
rm -f "$f1" "$f2" "$manifest" "/tmp/cc_gen_${f1hash}" "/tmp/cc_gen_${f2hash}"
rm -f "/tmp/cc_zed_ptr_${f1hash}" "/tmp/cc_zed_ptr_${f2hash}"
rm -rf "/tmp/cc_zed_snap_${SID}" "$SHIM_DIR"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
