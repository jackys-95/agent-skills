<!-- zed-launch-context -->
## How CC Is Launched in Zed

CC can run in Zed in two ways. The hooks (snapshot, diff, revert) work identically in both.

**Terminal Thread — recommended for Claude Pro/Max subscribers:**
Agent panel → **+** → **Terminal** → type `claude`.
Uses your Claude subscription directly. `CC_ZED_HOOK=1` is already set via `terminal.env` in `~/.config/zed/settings.json` — no extra config needed.

**ACP external agent:**
Configured via `agent_servers."claude-acp"` in `~/.config/zed/settings.json`.
Starting 2026-06-15, ACP usage draws from a separate credit pool billed at API rates — not from Claude Pro/Max subscriptions.
<!-- zed-launch-context -->

<!-- zed-adapter -->
# Zed Adapter Behavior

You are running inside Zed as an external agent. After every file edit, a diff view opens in Zed for the user to review. CC continues immediately — the diff is non-blocking.

## After a Write or Edit

The PreToolUse hook prints a `[Zed]` line containing the snapshot path before CC writes.

- **No reply** — user accepted, CC has already continued
- **Cmd+S in Zed** — user kept their edits; the file on disk has their version
- **User replies `r`** — revert: run `python3 ~/.claude/hooks/revert_zed_snapshot.py <file_path>` using the file path from the most recent `[Zed]` line, then ask what they want instead

## Guidance

- After every Write or Edit, output `reply 'r' to revert` as a **standalone line** in that same response — one line per file written, even when chaining tool calls. Hook stdout is not shown in the Zed panel; this line is the only way the user knows the option exists.
- Do not narrate or summarize the diff content — the user sees it in Zed
- Do not re-read a file after writing unless the user replies `r` and you have reverted it
- The user approves by silence — do not ask for confirmation if they haven't replied
<!-- zed-adapter -->
