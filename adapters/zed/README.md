# Zed Adapter

Opens files in Zed whenever Claude Code edits or writes them, then blocks CC until you close the buffer — so CC continues with your changes (or without, if you close without saving).

## Requirements

- macOS
- [Zed](https://zed.dev) with the `zed` CLI in PATH (`zed --version` to verify)
- [fswatch](https://github.com/emcrisostomo/fswatch) (`brew install fswatch`)

## Install

```bash
python3 adapters/zed/install.py
```

This copies the hook script into `~/.claude/hooks/` and wires it into `~/.claude/settings.json` as a global `PostToolUse` hook.

## Enable inside Zed

The hook is guarded by `CC_ZED_HOOK=1` so it only fires when CC runs inside Zed. CC runs via Zed's **agent panel** (not the terminal), so the env var must be set under `agent_servers`:

`~/.config/zed/settings.json`:
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

Without this, the hook is a no-op — CC running in any other context is unaffected.

## How it works

1. CC edits or writes a file.
2. The `PostToolUse` hook fires with the file path.
3. The hook opens the file in Zed and races `fswatch` (save event) against `zed --wait` (close event).
4. CC blocks until whichever fires first.
5. **Cmd+S** → CC continues immediately with your saved version.
6. **Close tab without saving** → CC continues with its original write.

## UX note

This gives you an edit-in-place flow: review what CC wrote, tweak directly in Zed, close the tab, and CC resumes with your changes — no back-and-forth conversation round trip required.
