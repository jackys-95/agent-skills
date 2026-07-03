#!/usr/bin/env python3
"""PostToolUse hook: record an edited file in the turn's Zed diff manifest.

Diffs no longer open per edit — opening fronts Zed (the 1.9.0 CLI always activates,
with no open-without-activate flag), which steals focus on every write and can
misroute keystrokes into Zed while the user types elsewhere. Instead each edited
file is queued in a per-(session, file) marker; the Stop hook flushes the whole
turn into one multi-diff. This hook just drops the marker (created here so that
Write-created new files, which don't exist at PreToolUse time, still get queued).
"""
import json
import os
import sys

from _zed_common import seen_marker


def main():
    if not os.environ.get("CC_ZED_HOOK"):
        sys.exit(0)
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    file_path = event.get("tool_input", {}).get("file_path", "")
    if not file_path:
        sys.exit(0)

    session_id = event.get("session_id", "")
    # Marker contents = the file path, so the Stop hook enumerates the turn's edited
    # files from the session's markers alone. Its existence also tells the pre-hook
    # the turn-start base is already captured (keep the first snapshot). Rewritten
    # every edit (cheap, idempotent).
    with open(seen_marker(session_id, file_path), "w") as f:
        f.write(file_path)


if __name__ == "__main__":
    main()
