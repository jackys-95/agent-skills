#!/usr/bin/env bash
# Unit tests for the task-memory-bank reindex hooks:
#   post_edit_mark_dirty.py       — PostToolUse detector (marks dirty, never reindexes)
#   reindex_dirty_collections.py  — lifecycle flush (reindex dirty collections, detached)
#   _reindex_common.py            — index.yml parsing + path→collection mapping
set -uo pipefail

HOOKS="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0; FAIL=0
ok()   { echo "PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }

WORK=$(mktemp -d)
export HOME="$WORK"                       # isolate ~/.config/qmd and markers' HOME refs
mkdir -p "$WORK/.config/qmd"

# A fake qmd registry with a tmb collection and a KB collection.
TMB_ROOT="$WORK/memory/projects/agent_skills"
KB_ROOT="$WORK/Documents/knowledge"
mkdir -p "$TMB_ROOT/work" "$KB_ROOT"
cat > "$WORK/.config/qmd/index.yml" <<YML
collections:
  mb-agent-skills:
    path: $TMB_ROOT
    pattern: "**/*.md"
  example-knowledge:
    path: $KB_ROOT
    pattern: "**/*.md"
models:
  embed: whatever
YML

marker_glob="/tmp/cc_tmb_dirty_*"
rm -f $marker_glob

run_post() { echo "$1" | python3 "$HOOKS/post_edit_mark_dirty.py" 2>&1; }

# 1: edit inside the tmb collection → marker written with the collection name
rm -f $marker_glob
run_post "{\"tool_input\":{\"file_path\":\"$TMB_ROOT/work/active.md\"}}"
if [ "$(cat /tmp/cc_tmb_dirty_mb-agent-skills 2>/dev/null)" = "mb-agent-skills" ]; then
    ok "1: edit under tmb root → dirty marker for mb-agent-skills"
else
    fail "1: no/wrong marker ($(ls $marker_glob 2>/dev/null))"
fi

# 2: edit inside the KB collection → marker for example-knowledge
rm -f $marker_glob
run_post "{\"tool_input\":{\"file_path\":\"$KB_ROOT/topic.md\"}}"
if [ "$(cat /tmp/cc_tmb_dirty_example-knowledge 2>/dev/null)" = "example-knowledge" ]; then
    ok "2: edit under KB root → dirty marker for example-knowledge"
else
    fail "2: no/wrong marker ($(ls $marker_glob 2>/dev/null))"
fi

# 3: edit OUTSIDE every collection → no marker (fast no-op)
rm -f $marker_glob
run_post "{\"tool_input\":{\"file_path\":\"$WORK/some/random/code.py\"}}"
shopt -s nullglob; leftover=($marker_glob); shopt -u nullglob
if [ ${#leftover[@]} -eq 0 ]; then
    ok "3: edit outside all collections → no marker"
else
    fail "3: unexpected marker(s): ${leftover[*]}"
fi

# 4: missing file_path → silent no-op, exit 0
rm -f $marker_glob
out=$(run_post '{"tool_input":{}}'); code=$?
shopt -s nullglob; leftover=($marker_glob); shopt -u nullglob
if [ $code -eq 0 ] && [ ${#leftover[@]} -eq 0 ]; then
    ok "4: missing file_path → no-op exit 0"
else
    fail "4: code=$code leftover=${leftover[*]}"
fi

# 5: flush hook with NO markers → does not launch the reindexer
rm -f $marker_glob
# Shim memory_bank.py location by faking the installed path under $HOME.
MB_DIR="$WORK/.claude/skills/task-memory-bank/scripts"
mkdir -p "$MB_DIR"
REINDEX_LOG="$WORK/reindex_calls.log"
cat > "$MB_DIR/memory_bank.py" <<PYSHIM
import sys
open("$REINDEX_LOG","a").write(" ".join(sys.argv[1:]) + "\n")
PYSHIM
: > "$REINDEX_LOG"
python3 "$HOOKS/reindex_dirty_collections.py" <<< '{}' 2>&1
sleep 0.3
if [ ! -s "$REINDEX_LOG" ]; then
    ok "5: no markers → reindexer not launched"
else
    fail "5: reindexer ran with no markers: $(cat "$REINDEX_LOG")"
fi

# 6: flush hook WITH two markers → reindexer called once per collection, markers cleared
printf 'mb-agent-skills' > /tmp/cc_tmb_dirty_mb-agent-skills
printf 'example-knowledge' > /tmp/cc_tmb_dirty_example-knowledge
: > "$REINDEX_LOG"
python3 "$HOOKS/reindex_dirty_collections.py" <<< '{}' 2>&1
sleep 0.5
calls=$(sort "$REINDEX_LOG" 2>/dev/null)
shopt -s nullglob; leftover=($marker_glob); shopt -u nullglob
if echo "$calls" | grep -q "reindex --collection mb-agent-skills" \
   && echo "$calls" | grep -q "reindex --collection example-knowledge" \
   && [ ${#leftover[@]} -eq 0 ]; then
    ok "6: two markers → reindex per collection, markers cleared"
else
    fail "6: calls='$calls' leftover=${leftover[*]}"
fi

rm -f $marker_glob
rm -rf "$WORK"
echo ""
echo "Results: $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
