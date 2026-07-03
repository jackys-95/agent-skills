#!/usr/bin/env bash
# Unit tests for revert_zed_snapshot.py — restores a file to its turn-start state:
# copies back a real snapshot, or deletes a file whose base is /dev/null (created
# this turn).
set -euo pipefail

HOOK="$(dirname "$0")/../../hooks/revert_zed_snapshot.py"
PASS=0; FAIL=0

ok()   { echo "PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }

hash_of() { python3 -c "import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:16])" "$1"; }

# 6a: no pointer for the file → exit 1 (nothing to revert)
missing="/tmp/zed_revert_nopointer.txt"
rm -f "$missing" "/tmp/cc_pre_ptr_$(hash_of "$missing")"
code=0; out=$(python3 "$HOOK" "$missing" 2>&1) || code=$?
[ $code -eq 1 ] && ok "6a: no pointer → exit 1" || fail "6a: exit=$code out='$out'"

# 6b: real snapshot → file restored to snapshot content
f="/tmp/zed_revert_edit.txt"
fhash=$(hash_of "$f")
snap="/tmp/cc_pre_${fhash}_test"
ptr="/tmp/cc_pre_ptr_${fhash}"
echo "turn-start content" > "$snap"
echo "$snap" > "$ptr"
echo "CC's edited content" > "$f"
code=0; out=$(python3 "$HOOK" "$f" 2>&1) || code=$?
if [ $code -eq 0 ] && [ "$(cat "$f")" = "turn-start content" ]; then
    ok "6b: real snapshot → file restored to turn-start content"
else
    fail "6b: exit=$code content='$(cat "$f" 2>/dev/null)' out='$out'"
fi
rm -f "$f" "$snap" "$ptr"

# 6c: /dev/null pointer (new file created this turn) → file deleted
nf="/tmp/zed_revert_newfile.txt"
nfhash=$(hash_of "$nf")
nfptr="/tmp/cc_pre_ptr_${nfhash}"
echo "content CC wrote into a brand-new file" > "$nf"
printf '/dev/null' > "$nfptr"
code=0; out=$(python3 "$HOOK" "$nf" 2>&1) || code=$?
if [ $code -eq 0 ] && [ ! -e "$nf" ] && echo "$out" | grep -q 'deleted'; then
    ok "6c: /dev/null pointer → new file deleted"
else
    fail "6c: exit=$code exists=$([ -e "$nf" ] && echo yes || echo no) out='$out'"
fi
rm -f "$nf" "$nfptr"

# 6d: /dev/null pointer but file already gone (user deleted it) → still exit 0, no crash
gone="/tmp/zed_revert_alreadygone.txt"
goneptr="/tmp/cc_pre_ptr_$(hash_of "$gone")"
printf '/dev/null' > "$goneptr"
rm -f "$gone"
code=0; out=$(python3 "$HOOK" "$gone" 2>&1) || code=$?
[ $code -eq 0 ] && ok "6d: /dev/null pointer, file already gone → exit 0, no crash" || fail "6d: exit=$code out='$out'"
rm -f "$goneptr"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
