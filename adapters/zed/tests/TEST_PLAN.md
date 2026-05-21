# Zed Adapter Test Plan

## Unit Tests (automated)

Run from the repo root:

```bash
bash adapters/zed/tests/unit/run_all.sh
# or individual suites:
bash adapters/zed/tests/unit/test_pre_hook.sh
bash adapters/zed/tests/unit/test_post_hook.sh
```

### Pre-hook (`pre_edit_zed_snapshot.py`)

| ID | Scenario | Expected |
|----|----------|----------|
| 1a | `CC_ZED_HOOK` not set | Silent, exit 0 |
| 1b | File path does not exist | Silent, exit 0 |
| 1c | Existing file | Snapshot written to `/tmp/cc_pre_<hash>`, stdout includes `[Zed] snapshot=<path> \|` |
| 1d | Same file edited twice | Same snapshot path both times (deterministic hash) |
| 1e | Binary file | No crash, snapshot written, exit 0 |

### Post-hook (`post_edit_open_in_zed.py`)

| ID | Scenario | Expected |
|----|----------|----------|
| 2a | `CC_ZED_HOOK` not set | Silent, exit 0 |
| 2b | Snapshot present | `zed --diff <snapshot> <file>` launched non-blocking, exit 0 |
| 2c | Snapshot absent (new file) | `zed <file>` launched as fallback, exit 0 |

---

## UX Tests (manual, requires Zed + CC running)

Prerequisites:
- `CC_ZED_HOOK=1` set in Zed `agent_servers."claude-acp".env`
- `defaultMode: acceptEdits` in `~/.claude/settings.json`
- Both hooks installed in `~/.claude/hooks/`

### 3a — Accept by silence

1. Ask CC to edit a file.
2. Diff opens in Zed. Do nothing.
3. **Pass**: CC continued without waiting; file on disk has CC's version.

### 3b — Edit in diff + Cmd+S

1. Ask CC to edit a file.
2. In the Zed diff view, change CC's edit to your own version.
3. Cmd+S.
4. **Pass**: file on disk has your version (not CC's). CC has already continued.

### 3c — Revert via `r`

1. Ask CC to edit a file.
2. Reply `r` in the CC agent panel.
3. **Pass**: CC reads snapshot path from the `[Zed]` line, writes snapshot back, asks what to do instead. File on disk returns to pre-edit state.

### 3d — Same file edited twice

1. Ask CC to edit a file twice in succession.
2. **Pass**: each edit opens a fresh diff showing only that edit's delta (snapshot is overwritten by PreToolUse on the second edit).

---

## Install Verification

```bash
python3 adapters/zed/install.py
```

Check:
- Both hooks copied to `~/.claude/hooks/` and executable
- `~/.claude/settings.json` has `"defaultMode": "acceptEdits"`
- `~/.claude/CLAUDE.md` contains the `<!-- zed-adapter -->` block with current content
- Running `install.py` twice does not duplicate the CLAUDE.md block or corrupt settings
