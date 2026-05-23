# Zed Adapter

Opens a diff view in Zed whenever Claude Code edits or writes a file. CC continues immediately — review is non-blocking and you can revert via the CC panel if needed.

## Requirements

- macOS
- [Zed](https://zed.dev) with the `zed` CLI in PATH (`zed --version` to verify)

## Install

```bash
python3 adapters/zed/install.py
```

This copies both hook scripts into `~/.claude/hooks/`, registers them as PreToolUse/PostToolUse hooks in `~/.claude/settings.json`, sets `defaultMode: acceptEdits`, and appends the adapter instructions to `~/.claude/CLAUDE.md`.

## Enable inside Zed

The hooks are guarded by `CC_ZED_HOOK=1` so they only fire when CC runs inside Zed. Set it under `agent_servers` in `~/.config/zed/settings.json`:

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

Without this, the hooks are no-ops — CC running in any other context is unaffected.

## How it works

1. CC edits or writes a file (`acceptEdits` auto-approves the write).
2. The `PreToolUse` hook snapshots the original file to `/tmp/cc_pre_<hash>` and prints a `[Zed]` line with the snapshot path.
3. CC writes the file.
4. The `PostToolUse` hook opens `zed --diff <snapshot> <file>` non-blocking and brings Zed to the front.
5. You review the diff in Zed at your own pace.

## UX

- **Accept** — do nothing, CC has already moved on.
- **Edit** — make changes in Zed and Cmd+S to save.
- **Revert** — reply `r` in the CC panel. CC reads the snapshot path from the `[Zed]` line and writes it back.
