# Zed Adapter

The Zed-side half of a Zed + agent integration. Install this alongside an agent adapter to get a named pairing like **zed-cc** (Zed + Claude Code).

Opens a diff view in Zed whenever the agent edits or writes a file. The agent continues immediately — review is non-blocking and you can revert via the agent panel if needed.

## Requirements

- macOS
- [Zed](https://zed.dev) with the `zed` CLI in PATH (`zed --version` to verify)
- [fswatch](https://github.com/emcrisostomo/fswatch) for edit injection (`brew install fswatch`)

## Install

Install the agent adapter first (e.g., the CC adapter for zed-cc):

```bash
python3 scripts/install_claude_code.py
```

Then install the Zed adapter:

```bash
python3 adapters/zed/install.py
```

This copies hook scripts into `~/.claude/hooks/`, registers them as PreToolUse/PostToolUse hooks in `~/.claude/settings.json`, sets `defaultMode: acceptEdits`, and appends the adapter instructions to `~/.claude/CLAUDE.md`.

## Enable inside Zed

The hooks are guarded by `CC_ZED_HOOK=1` so they only fire when CC runs inside Zed.

**Terminal Thread (recommended for Claude Pro/Max subscribers):**
`CC_ZED_HOOK=1` is already set via `terminal.env` — no extra config needed. Open the agent panel → **+** → **Terminal** → type `claude`.

**ACP external agent:**
Set the env var under `agent_servers` in `~/.config/zed/settings.json`:

```json
{
  "agent_servers": {
    "claude-acp": {
      "type": "registry",
      "env": {
        "CC_ZED_HOOK": "1"
      }
    }
  }
}
```

Without `CC_ZED_HOOK=1`, the hooks are no-ops — CC running in any other context is unaffected.

## How it works

1. CC edits or writes a file (`acceptEdits` auto-approves the write).
2. The `PreToolUse` hook snapshots the original file to `/tmp/cc_pre_<hash>` and prints a `[Zed]` line with the snapshot path.
3. CC writes the file.
4. The `PostToolUse` hook opens `zed -a --diff <snapshot> <file>` non-blocking and brings Zed to the front. The `-a`/`--add` flag pins the diff to the active workspace, so a diff on a file outside the current project (e.g. a task-memory-bank file, or a cross-package edit in a multi-repo workspace) doesn't swap the window's project. New files (no snapshot) diff against an empty base (`zed -a --diff /dev/null <file>`); using `--diff` in both cases keeps the path a diff buffer rather than attaching it to the workspace as a loose worktree.
5. You review the diff in Zed at your own pace.

If CC is running inside `tmux` (terminal thread → `tmux` → `claude`), a background watcher also starts for each written file. When you save your edits in Zed (Cmd+S), the watcher injects a `[Zed edit]` message with the diff into CC's input — no manual copy-paste needed.

## UX

- **Accept** — do nothing, CC has already moved on.
- **Edit** — make changes in Zed and Cmd+S to save. If running inside tmux, CC is automatically notified with a diff of your changes.
- **Revert** — reply `r` in the CC panel. CC reads the snapshot path from the `[Zed]` line and writes it back.

## Edit injection (tmux)

Run CC inside tmux for automatic edit notification:

```bash
tmux
claude  # inside the tmux pane
```

`$TMUX_PANE` is set automatically — no extra config needed. When you save a diff view, CC receives:

```
[Zed edit] filename.py was saved with changes:
--- a/filename.py
+++ b/filename.py
@@ ...
```

If you close the diff without saving, or save without making changes, nothing is sent. The watcher expires silently after 120 seconds.
