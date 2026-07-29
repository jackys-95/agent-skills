# Zed Adapter Behavior

You are running inside Zed as an external agent. Diffs for the files you edit are
**batched per turn**: nothing opens on each individual edit — instead one multi-diff
view opens in Zed when your turn ends, showing every file you changed. This keeps Zed
from stealing focus mid-turn. CC never blocks on the diff.

## After a Write or Edit

The PreToolUse hook prints a `[Zed]` line containing the snapshot path before CC writes.
The diff itself does not open until the turn ends (the `Stop` hook flushes it).

- **No reply** — user accepted; the files on disk have CC's versions
- **Saved in Zed (Cmd+S on macOS, Ctrl+S on Linux)** — user kept their edits in the diff view; that file on disk has their version
- **User replies `r <file>`** — revert one file: run
  `python3 ~/.claude/hooks/revert_zed_snapshot.py <file_path>` for that file (match it to the
  most recent `[Zed]` line for that path), then ask what they want instead
- **User replies `revert all`** — revert every file you edited this turn: run the revert script
  once per file from this turn's `[Zed]` lines, then ask what they want instead

The diff base is each file's **turn-start** state, so reverting restores the file to how it was
before this turn — even if CC edited it several times. For a **new file created this turn**, the
turn-start state is "did not exist", so reverting it **deletes** the file.

## Guidance

- After every Write or Edit, output `reply 'r <file>' to revert` as a **standalone line** in that
  same response — one line per file written, even when chaining tool calls. Include the file path
  so a multi-file turn is unambiguous. Hook stdout is not shown in the Zed panel; this line is the
  only way the user knows the option exists.
- Do not narrate or summarize the diff content — the user sees it in Zed
- Do not re-read a file after writing unless the user reverts it
- The user approves by silence — do not ask for confirmation if they haven't replied
