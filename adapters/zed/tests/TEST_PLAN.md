# Zed Adapter Test Plan

Diffs are **batched per CC turn**: individual edits are queued, and one multi-diff
opens on the `Stop` hook when the turn ends. This fronts Zed once per turn instead of
once per edit — eliminating single-monitor focus-steal and the keystroke-misrouting
risk of per-edit opens. A "turn" is one user prompt; `UserPromptSubmit` resets the
per-turn state. State is keyed by `session_id` so concurrent Zed threads don't collide.

## Hook roles

| Hook | Event | Role |
|------|-------|------|
| `pre_edit_zed_snapshot.py` | PreToolUse (Edit\|Write) | Snapshot the file's **turn-start** state, once per file per turn (keep the first) |
| `post_edit_open_in_zed.py` | PostToolUse (Edit\|Write) | Queue the edited file in the turn manifest (marker); covers Write-created new files |
| `reset_zed_turn.py` | UserPromptSubmit | Clear this session's turn markers at turn start |
| `stop_flush_zed_diffs.py` | Stop | Open one `zed -a --diff …` multi-diff for the whole turn, then clear markers |

## Unit Tests (automated)

Run from the repo root:

```bash
bash adapters/zed/tests/unit/run_all.sh
# or individual suites:
bash adapters/zed/tests/unit/test_pre_hook.sh
bash adapters/zed/tests/unit/test_post_hook.sh
bash adapters/zed/tests/unit/test_reset_hook.sh
bash adapters/zed/tests/unit/test_stop_hook.sh
```

### Pre-hook (`pre_edit_zed_snapshot.py`)

| ID | Scenario | Expected |
|----|----------|----------|
| 1a | `CC_ZED_HOOK` not set | Silent, exit 0 |
| 1b | File path does not exist | Silent, exit 0 |
| 1c | Existing file | Snapshot written to `/tmp/cc_pre_<hash>`, stdout includes `[Zed] snapshot=<path> \|` |
| 1d | Same file edited twice in one turn | First snapshot kept as base (second call is a no-op — the turn marker suppresses it) |
| 1e | Binary file | No crash, snapshot written, exit 0 |

### Post-hook (`post_edit_open_in_zed.py`)

| ID | Scenario | Expected |
|----|----------|----------|
| 2a | `CC_ZED_HOOK` not set | Silent, exit 0 |
| 2b | Edit recorded | Per-`(session, file)` marker written containing the file path; no `zed` launch |
| 2c | New file (never existed at pre-time) | Still recorded in the manifest (post-hook doesn't require the file to exist) |

### Reset-hook (`reset_zed_turn.py`)

| ID | Scenario | Expected |
|----|----------|----------|
| 4a | `CC_ZED_HOOK` not set | Silent, exit 0; markers untouched |
| 4b | Markers present | Clears this session's markers only; other sessions' markers survive |

### Stop-hook (`stop_flush_zed_diffs.py`)

| ID | Scenario | Expected |
|----|----------|----------|
| 3a | `CC_ZED_HOOK` not set | Silent, exit 0 |
| 3b | Empty manifest | Silent, exit 0, no `zed` launch |
| 3c | Multi-file turn (one with snapshot, one new) | ONE `zed -a --diff …` with a `--diff` pair per file; new file diffs against `/dev/null` |
| 3d | After a flush | Markers cleared → a second `Stop` is a no-op |

---

## UX Tests (manual, requires Zed + CC running)

Prerequisites:
- `CC_ZED_HOOK=1` set in Zed `agent_servers."claude-acp".env` (or `terminal.env` for terminal-thread)
- `defaultMode: acceptEdits` in `~/.claude/settings.json`
- All four hooks installed in `~/.claude/hooks/`

### 5a — Batched open at end of turn

1. Ask CC to edit three different files in one turn.
2. **Pass**: NO diff opens mid-turn (Zed does not front on each edit). When CC finishes, ONE Zed
   multi-diff opens showing all three files. Zed fronts exactly once.

### 5b — Accept by silence

1. Ask CC to edit a file. When the turn-end diff opens, do nothing.
2. **Pass**: file on disk has CC's version.

### 5c — Edit in diff + Cmd+S

1. After the turn-end multi-diff opens, change CC's edit to your own version and Cmd+S.
2. **Pass**: file on disk has your version. (In tmux, the injector reports the saved delta back
   into the pane.)

### 5d — Revert one file via `r <file>`

1. Ask CC to edit two files. When the turn ends, reply `r <path>` for one of them.
2. **Pass**: CC runs the revert script for that path; that file returns to its **turn-start** state.
   The other file is untouched.

### 5e — `revert all`

1. After a multi-file turn, reply `revert all`.
2. **Pass**: CC reverts every file it edited this turn to its turn-start state.

### 5f — Same file edited twice in a turn

1. Ask CC to edit one file twice in a single turn.
2. **Pass**: the turn-end diff shows original→final (turn-start base to final content), and a revert
   restores the pre-turn version — not just the last edit.

### 5g — Concurrent threads don't collide

1. Run two CC terminal threads in Zed. Have each edit different files, finishing turns independently.
2. **Pass**: each thread's Stop opens only its own files (state is `session_id`-scoped).

---

## Install Verification

```bash
python3 adapters/zed/install.py
```

Check:
- All four hooks copied to `~/.claude/hooks/` and executable, plus `_zed_common.py`,
  `revert_zed_snapshot.py`, `tmux_diff_injector.py`
- `~/.claude/settings.json` registers `PreToolUse` + `PostToolUse` (matcher `Edit|Write`) and
  `UserPromptSubmit` + `Stop` (no matcher)
- `"defaultMode": "acceptEdits"` is set
- `~/.claude/CLAUDE.md` contains the `<!-- zed-adapter -->` block with current content
- Running `install.py` twice does not duplicate any hook command, the CLAUDE.md block, or corrupt settings
