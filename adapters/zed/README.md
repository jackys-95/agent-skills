# Zed Adapter

The Zed-side half of a Zed + agent integration. It supports **zed-cc**
(Zed + Claude Code) and **ZedCodex** (Zed + Codex CLI).

Opens a diff view in Zed for the files the agent changed. Diffs are **batched per turn**: instead of one diff popping up on every edit, all the files touched during a turn open together in a single multi-diff when the turn ends. This keeps Zed from stealing focus mid-turn (the Zed CLI always fronts the app when it opens content). The agent continues immediately — review is non-blocking and you can revert via the agent panel if needed.

## Requirements

- macOS or Linux
- [Zed](https://zed.dev) with the `zed` CLI in PATH (`zed --version` to verify)
- For tmux edit injection (zed-cc only — see [Edit injection (tmux)](#edit-injection-tmux)), a file watcher:
  - macOS: [fswatch](https://github.com/emcrisostomo/fswatch) (`brew install fswatch`)
  - Linux: inotify-tools (`sudo apt install inotify-tools` or your distro's equivalent)

## Install zed-cc

Install the agent adapter first (e.g., the CC adapter for zed-cc):

```bash
python3 scripts/install_claude_code.py
```

Then install the Zed adapter:

```bash
python3 adapters/zed/install.py
```

This copies hook scripts into `~/.claude/hooks/`, registers them in `~/.claude/settings.json` (PreToolUse/PostToolUse on `Edit|Write`, plus turn-boundary UserPromptSubmit/Stop hooks), sets `defaultMode: acceptEdits`, and appends the adapter instructions to `~/.claude/CLAUDE.md`.

## Install ZedCodex

Install the Codex skill adapter, then the ZedCodex hooks:

```bash
python3 scripts/install_codex.py
python3 adapters/zed/install_codex.py
```

The second command copies runtime files to `~/.codex/hooks/zedcodex/`, merges
four command hooks into `~/.codex/hooks.json`, and installs tagged review
guidance in `~/.codex/AGENTS.md`. It does not modify
`~/.codex/config.toml`.

Set `CODEX_ZED_HOOK=1` in Zed's terminal environment. Start a new Codex CLI
session, run `/hooks`, and review and trust the four definitions. Hooks are
hash-trusted, so changed definitions require another review.

ZedCodex currently detects `apply_patch` changes. Prefer `apply_patch` while
the pairing is active; shell-mediated writes do not receive a diff or revert
snapshot in this MVP.

## Enable zed-cc inside Zed

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

Diffs are batched per CC turn (one turn = one user prompt) and flushed on the `Stop` hook, so Zed fronts once per turn instead of once per edit. State is keyed by `session_id`, so concurrent Zed threads never share a batch.

1. **Turn start** — `UserPromptSubmit` clears this session's per-turn markers.
2. CC edits or writes a file (`acceptEdits` auto-approves the write).
3. The `PreToolUse` hook snapshots the file's **turn-start** state to `/tmp/cc_pre_<hash>` (once per file per turn — the first edit wins, so repeated edits keep the pre-turn base) and prints a `[Zed]` line with the snapshot path.
4. The `PostToolUse` hook queues the file in the turn manifest (a per-`(session, file)` marker). No diff opens yet.
5. **Turn end** — the `Stop` hook opens ONE `zed -a --diff <base> <file> --diff <base> <file> …` covering every file changed this turn, non-blocking, bringing Zed to the front once. `--diff` given many pairs renders them in a single multi-diff pane. The `-a`/`--add` flag pins the diff to the active workspace, so a diff on a file outside the current project (e.g. a task-memory-bank file, or a cross-package edit in a multi-repo workspace) doesn't swap the window's project. New files (no snapshot) diff against an empty base (`/dev/null`); using `--diff` for every operand keeps each path a diff buffer rather than attaching it to the workspace as a loose worktree.
6. You review the multi-diff in Zed at your own pace.

**zed-cc only:** if CC is running inside `tmux` (terminal thread → `tmux` → `claude`), the Stop hook also starts a background watcher for each changed file that has a snapshot. When you save your edits in Zed (Cmd+S on macOS, Ctrl+S on Linux), the watcher injects a `[Zed edit]` message with the diff into CC's input — no manual copy-paste needed. ZedCodex does not do this yet; see [Edit injection (tmux)](#edit-injection-tmux).

## Maintenance: stray memory-bank root in the project panel

Zed persists every folder it has opened as a root (in its workspace DB and `trusted_worktrees`) and **replays them on session-restore**. If an out-of-project directory — e.g. a task-memory-bank folder — was ever opened as a root by older tooling, it can keep reappearing as an extra root in the project panel after a restart, even though the current diff hook never adds it (the hook opens paths as diff buffers, not folders).

This is persisted residue, not a live recurrence. To clear it:

```bash
# Quit Zed first (Cmd+Q on macOS, Ctrl+Q on Linux) — the DB is locked while Zed runs.
python3 adapters/zed/prune_stale_roots.py           # dry run: show what would be pruned
python3 adapters/zed/prune_stale_roots.py --apply    # back up the DB, then prune
```

The script only removes roots that are memory-bank residue or dead paths (directories no longer on disk); real project roots are left untouched. It refuses to run while Zed is open and backs up the DB before any change.

## UX

- **Accept** — do nothing, CC has already moved on.
- **Edit** — make changes in Zed and save (Cmd+S on macOS, Ctrl+S on Linux). Your version is what stays on disk. Under zed-cc in tmux, CC is automatically notified with a diff of your changes; under ZedCodex the save is **not** echoed back, so tell Codex you edited the file (it is instructed to re-read a file you saved).
- **Revert one file** — reply `r <file>` in the CC panel. CC reads the snapshot path from that file's `[Zed]` line and writes it back (restoring its turn-start state).
- **Revert all** — reply `revert all` to roll back every file CC changed this turn.

## Edit injection (tmux)

**zed-cc only.** ZedCodex does not spawn the watcher: a Cmd+S in a ZedCodex diff keeps your version on disk, but nothing tells Codex about it. Say so in the session and it will re-read the file. Parity is deferred until the injector's false-"user saved" bug is fixed ([#65](https://github.com/jackys-95/agent-skills/issues/65)) — porting it first would duplicate that defect into a second adapter.

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
