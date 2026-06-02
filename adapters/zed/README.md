# Zed Adapter

The Zed-side half of a Zed + agent integration. Install this alongside an agent adapter to get a named pairing like **zed-cc** (Zed + Claude Code).

Opens a diff view in Zed whenever the agent edits or writes a file. The agent continues immediately — review is non-blocking and you can revert via the agent panel if needed.

## Requirements

- macOS
- [Zed](https://zed.dev) with the `zed` CLI in PATH (`zed --version` to verify)

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
4. The `PostToolUse` hook opens `zed --diff <snapshot> <file>` non-blocking and brings Zed to the front.
5. You review the diff in Zed at your own pace.

## UX

- **Accept** — do nothing, CC has already moved on.
- **Edit** — make changes in Zed and Cmd+S to save.
- **Revert** — reply `r` in the CC panel. CC reads the snapshot path from the `[Zed]` line and writes it back.
