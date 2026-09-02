# Zed Adapter Test Plan

For ZedCC, diffs are **batched per CC turn**: individual edits are queued, and one multi-diff
opens on the `Stop` hook when the turn ends. This fronts Zed once per turn instead of
once per edit — eliminating single-monitor focus-steal and the keystroke-misrouting
risk of per-edit opens. A "turn" is one user prompt; `UserPromptSubmit` resets the
per-turn state. State is keyed by `session_id` so concurrent Zed threads don't collide.
When a harness runs inside tmux, both CC and Codex also participate in one
cross-harness pane claim. Prompt submission restakes authority; session hooks
revoke stale or ended claims; the CC Stop hook and worker fail closed unless
the expected claim and owning process are still current.

## Hook roles

Repository sources are organized by responsibility. Installers copy the
required files by basename into flat harness runtime directories.

| Source | Event | Role |
|--------|-------|------|
| `hooks/core/zed_turn_lifecycle.py` | UserPromptSubmit | Under explicit CC or Codex policy, clear the harness turn and restake pane authority |
| `hooks/core/zed_turn_lifecycle.py` | SessionStart/SessionEnd | Under explicit CC or Codex policy, revoke mismatched or ended pane authority |
| `hooks/core/tmux_pane_authority.py` | Imported core | Persist and validate the cross-harness pane claim |
| `hooks/core/tmux_edit_injection.py` | CC worker | Watch edited files and inject only while the expected pane claim remains current |
| `hooks/claude-code/pre_edit_zed_snapshot.py` | PreToolUse (Edit\|Write) | Snapshot the file's **turn-start** state, once per file per turn |
| `hooks/claude-code/post_edit_open_in_zed.py` | PostToolUse (Edit\|Write) | Queue the edited file in the turn manifest |
| `hooks/claude-code/stop_flush_claude_code_zed_diffs.py` | Stop | Open one `zed -a --diff ...` multi-diff, then launch authorized watchers |
| `hooks/codex/pre_apply_patch_zed_snapshot.py` | PreToolUse (`apply_patch`) | Snapshot every path named by the parent Codex patch |
| `hooks/codex/post_apply_patch_zed_touch.py` | PostToolUse (`apply_patch`) | Confirm successfully patched paths |
| `hooks/codex/stop_flush_codex_zed_diffs.py` | Stop | Open one Zed multi-diff for the completed Codex turn |

## Automated Tests

Run from the repo root:

```bash
bash adapters/zed/tests/run_all.sh
```

### Unit tests

Unit tests import functions/modules directly and isolate process, filesystem, editor, and tmux boundaries with mocks, temporary state, or in-memory databases.

```bash
bash adapters/zed/tests/unit/run_all.sh
bash adapters/zed/tests/unit/test_platform_paths.sh
python3 adapters/zed/tests/unit/test_prune_stale_roots.py
python3 adapters/zed/tests/unit/test_tmux_pane_authority.py
python3 adapters/zed/tests/unit/test_tmux_edit_injection.py
python3 adapters/zed/tests/unit/test_codex_patch.py
python3 adapters/zed/tests/unit/test_install_zed_cc.py
```

### Integration tests

Integration tests execute hook lifecycles or installer subprocesses across multiple runtime modules and real temporary filesystem state. Zed and tmux commands remain mocked or isolated; these suites do not require a live editor session.

```bash
bash adapters/zed/tests/integration/run_all.sh
bash adapters/zed/tests/integration/test_pre_hook.sh
bash adapters/zed/tests/integration/test_post_hook.sh
bash adapters/zed/tests/integration/test_claude_code_turn_lifecycle.sh
bash adapters/zed/tests/integration/test_stop_hook.sh
python3 adapters/zed/tests/integration/test_claude_code_pane_authority_hooks.py
bash adapters/zed/tests/integration/test_revert_hook.sh
python3 adapters/zed/tests/integration/test_codex_hooks.py
python3 adapters/zed/tests/integration/test_install_zed_codex.py
```

### Integration: Pre-hook (`pre_edit_zed_snapshot.py`)

| ID | Scenario | Expected |
|----|----------|----------|
| 1a | `CC_ZED_HOOK` not set | Silent, exit 0 |
| 1b | File path does not exist | Record the `new` base and print new-file revert guidance |
| 1c | Existing file | Snapshot written to `/tmp/cc_pre_<hash>`, stdout includes `[Zed] snapshot=<path> \|` |
| 1d | Same file edited twice in one turn | First snapshot kept as base (second call is a no-op — the turn marker suppresses it) |
| 1e | Binary file | No crash, snapshot written, exit 0 |

### Integration: Post-hook (`post_edit_open_in_zed.py`)

| ID | Scenario | Expected |
|----|----------|----------|
| 2a | `CC_ZED_HOOK` not set | Silent, exit 0 |
| 2b | Edit recorded | Per-`(session, file)` marker written containing the file path; no `zed` launch |
| 2c | New file (never existed at pre-time) | Still recorded in the manifest (post-hook doesn't require the file to exist) |

### Integration: CC turn lifecycle (`core/zed_turn_lifecycle.py`)

| ID | Scenario | Expected |
|----|----------|----------|
| 4a | `CC_ZED_HOOK` not set | Silent, exit 0; markers untouched |
| 4b | Markers present | Clears this session's markers only; other sessions' markers survive |
| 4c | Matching tmux context | Replaces the cross-harness pane claim with a fresh CC turn-authority token |

### Integration: Claude Code Stop hook (`claude-code/stop_flush_claude_code_zed_diffs.py`)

| ID | Scenario | Expected |
|----|----------|----------|
| 3a | `CC_ZED_HOOK` not set | Silent, exit 0 |
| 3b | Empty manifest | Silent, exit 0, no `zed` launch |
| 3c | Multi-file turn (one with snapshot, one new) | ONE `zed -a --diff …` with a `--diff` pair per file; new file diffs against `/dev/null` |
| 3d | After a flush | Markers cleared → a second `Stop` is a no-op |

### Pane-authority lifecycle

`unit/test_tmux_pane_authority.py` covers canonical server/pane keys, private
claim and lock files, atomic replacement, malformed-state denial, PID plus
start-time liveness, cross-harness supersession, expected-claim serialization,
event-specific revocation, and the locked race where an old hook must not
delete a concurrent newer restake.

`integration/test_claude_code_pane_authority_hooks.py` covers Claude Code prompt restaking,
matching SessionStart preservation, owned-only SessionEnd cleanup, matching
Stop watcher launch, and denied Stop authorization that still opens the Zed
diff.

### Unit: Platform paths (`_zed_common.py`, `install_zed_cc.py`, `prune_stale_roots.py`, `tmux_edit_injection.py`)

Forces `sys.platform` to `darwin`/`linux` before import and calls the watcher command builder directly to verify both platform branches without needing both operating systems.

| ID | Scenario | Expected |
|----|----------|----------|
| 7a | `_zed_common.BUNDLED_ZED_CLI` | darwin → `.app` CLI path; linux → `~/.local/bin/zed` |
| 7b | `install.BUNDLED_ZED_CLI` / `install.WATCHER_BIN` | darwin → `.app` CLI path / `fswatch`; linux → `~/.local/bin/zed` / `inotifywait` |
| 7c | `prune_stale_roots.DEFAULT_DB` | darwin → `Library/Application Support/Zed/...`; linux → `.local/share/zed/...` |
| 7d | `tmux_edit_injection.watch_command` | darwin → `fswatch -1 <file>`; linux → `inotifywait -e modify -e close_write <file>` |

### ZedCodex automated coverage

The unit suite `unit/test_codex_patch.py` covers Add, Update, Delete, Move, deduplication,
absolute/relative and parent-traversal paths, column-zero header recognition,
literal quote/tilde characters, spaces, and non-ASCII path text.

The integration suite `integration/test_codex_hooks.py` covers:

- guarded no-op behavior without `CODEX_ZED_HOOK`;
- parent versus child `UserPromptSubmit` reset behavior;
- parent prompt pane-authority restaking without child supersession;
- SessionStart mismatch revocation and SessionEnd owned-claim cleanup;
- first-base retention across repeated pre-hooks;
- multi-file Add/Update/Delete/Move rendering;
- `/dev/null` pairs for created and deleted paths;
- add-then-delete no-op filtering;
- unchanged existing-file filtering after a failed patch;
- structured Stop warnings;
- existing-file and new-file revert semantics.

The integration suite `integration/test_install_zed_codex.py` executes the installer subprocess and verifies runtime copies, idempotent `hooks.json` merge,
preservation of unrelated config, selective AGENTS.md block installation, and
dry-run behavior. It also verifies migration away from the former
`additionalContextLimit = 1000` override.

---

## UX Tests (manual, requires Zed + CC running)

Prerequisites:
- `CC_ZED_HOOK=1` set in Zed `agent_servers."claude-acp".env` (or `terminal.env` for terminal-thread)
- `defaultMode: acceptEdits` in `~/.claude/settings.json`
- All six lifecycle registrations installed in `~/.claude/settings.json`

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
python3 adapters/zed/install_zed_cc.py
```

Check:
- All registered hooks copied to `~/.claude/hooks/` and executable, plus
  `_zed_common.py`, `revert_zed_snapshot.py`, `tmux_edit_injection.py`, and
  `tmux_pane_authority.py`
- `~/.claude/settings.json` registers `PreToolUse` + `PostToolUse` (matcher `Edit|Write`) and
  `UserPromptSubmit` + `Stop` + `SessionStart` + `SessionEnd` (no matcher)
- `"defaultMode": "acceptEdits"` is set
- `~/.claude/CLAUDE.md` contains current `<!-- zed-launch-context -->`,
  `<!-- zed-adapter -->`, and `<!-- phase-turns -->` blocks.
- Running `install_zed_cc.py` twice does not duplicate any hook command or CLAUDE.md
  block, or corrupt settings.
- Running only `scripts/claude-code/install_claude_code.py` does not install any of these
  Zed-specific blocks.

### ZedCodex install

```bash
python3 adapters/zed/install_zed_codex.py
```

Check:

- Runtime files are under `~/.codex/hooks/zedcodex/`.
- `~/.codex/hooks.json` contains six hooks without changing
  `~/.codex/config.toml`.
- `/hooks` shows UserPromptSubmit, PreToolUse `^apply_patch$`, PostToolUse
  `^apply_patch$`, Stop, SessionStart, and SessionEnd definitions awaiting review
  on first install.
- Trust persists after restart and changes to a hook definition require review.
- `~/.codex/AGENTS.md` contains one `<!-- zed-codex-adapter -->` block and one
  `<!-- phase-turns -->` block.
- Running only `scripts/codex/install_codex.py` installs neither Zed-specific block.

### ZedCodex manual review

With `CODEX_ZED_HOOK=1` set in a Zed terminal and the hooks trusted:

1. Ask Codex to add, update, delete, and move files in one turn.
2. Confirm no diff opens mid-turn and one multi-diff opens at Stop.
3. Confirm Codex surfaces one standalone revert line per path.
4. Reply `r <file>` for an updated file and confirm turn-start content returns.
5. Repeat for a new file and confirm revert deletes it.
6. Reply `revert all` after a move and confirm the old path returns while the
   destination is removed.
