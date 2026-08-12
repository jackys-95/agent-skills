# Zed Adapter Test Plan

For zed-cc, diffs are **batched per CC turn**: individual edits are queued, and one multi-diff
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
bash adapters/zed/tests/unit/test_platform_paths.sh
python3 adapters/zed/tests/unit/test_codex_patch.py
python3 adapters/zed/tests/unit/test_codex_hooks.py
python3 adapters/zed/tests/unit/test_install_codex.py
```

### Pre-hook (`pre_edit_zed_snapshot.py`)

| ID | Scenario | Expected |
|----|----------|----------|
| 1a | `CC_ZED_HOOK` not set | Silent, exit 0 |
| 1b | File path does not exist | Record the `new` base and print new-file revert guidance |
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

### Platform paths (`_zed_common.py`, `install.py`, `prune_stale_roots.py`, `tmux_diff_injector.py`)

Forces `sys.platform` to `darwin`/`linux` before import (or, for the watcher, via a fake
`fswatch`/`inotifywait` shim on `PATH`) to verify the Linux-support branches added in
`feat(zed-adapter): add Linux support` without needing both OSes.

| ID | Scenario | Expected |
|----|----------|----------|
| 7a | `_zed_common.BUNDLED_ZED_CLI` | darwin → `.app` CLI path; linux → `~/.local/bin/zed` |
| 7b | `install.BUNDLED_ZED_CLI` / `install.WATCHER_BIN` | darwin → `.app` CLI path / `fswatch`; linux → `~/.local/bin/zed` / `inotifywait` |
| 7c | `prune_stale_roots.DEFAULT_DB` | darwin → `Library/Application Support/Zed/...`; linux → `.local/share/zed/...` |
| 7d | `tmux_diff_injector.WATCH_CMD` | darwin → `fswatch -1 <file>`; linux → `inotifywait -e modify -e close_write <file>` |

### ZedCodex

`test_codex_patch.py` covers Add, Update, Delete, Move, deduplication,
absolute/relative and parent-traversal paths, column-zero header recognition,
literal quote/tilde characters, spaces, and non-ASCII path text.

`test_codex_hooks.py` covers:

- guarded no-op behavior without `CODEX_ZED_HOOK`;
- parent versus child `UserPromptSubmit` reset behavior;
- first-base retention across repeated pre-hooks;
- multi-file Add/Update/Delete/Move rendering;
- `/dev/null` pairs for created and deleted paths;
- add-then-delete no-op filtering;
- unchanged existing-file filtering after a failed patch;
- structured Stop warnings;
- existing-file and new-file revert semantics.

`test_install_codex.py` verifies runtime copies, idempotent `hooks.json` merge,
preservation of unrelated config, selective AGENTS.md block installation, and
dry-run behavior. It also verifies migration away from the former
`additionalContextLimit = 1000` override.

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

### 5c — Edit in diff + save

1. After the turn-end multi-diff opens, change CC's edit to your own version and save (Cmd+S on macOS, Ctrl+S on Linux).
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

### ZedCodex install

```bash
python3 adapters/zed/install_codex.py
```

Check:

- Runtime files are under `~/.codex/hooks/zedcodex/`.
- `~/.codex/hooks.json` contains four hooks without changing
  `~/.codex/config.toml`.
- `/hooks` shows UserPromptSubmit, PreToolUse `^apply_patch$`, PostToolUse
  `^apply_patch$`, and Stop definitions awaiting review on first install.
- Trust persists after restart and changes to a hook definition require review.
- `~/.codex/AGENTS.md` contains one `<!-- zed-codex-adapter -->` block.

### ZedCodex manual review

With `CODEX_ZED_HOOK=1` set in a Zed terminal and the hooks trusted:

1. Ask Codex to add, update, delete, and move files in one turn.
2. Confirm no diff opens mid-turn and one multi-diff opens at Stop.
3. Confirm Codex surfaces one standalone revert line per path.
4. Reply `r <file>` for an updated file and confirm turn-start content returns.
5. Repeat for a new file and confirm revert deletes it.
6. Reply `revert all` after a move and confirm the old path returns while the
   destination is removed.
