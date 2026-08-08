#!/usr/bin/env python3
"""PostToolUse hook: confirm an edited file is queued in the turn's manifest.

Diffs no longer open per edit — opening fronts Zed (the 1.9.0 CLI always activates,
with no open-without-activate flag), which steals focus on every write and can
misroute keystrokes into Zed while the user types elsewhere. Instead the pre-hook
queues each edited file in the shared manifest; the Stop hook flushes the whole turn
into one multi-diff. This hook just confirms the queue entry — kept as its own call
(rather than folded into the pre-hook) since it fires after the tool completes, not
before, which matters if a future edge case needs "touched" confirmed independently of
"base captured." See TASK-0022 designs/core-api-plan.md.
"""
import json
import os
import sys

import manifest

NAMESPACE = "cc_zed"


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
    manifest.mark_touched(NAMESPACE, session_id, file_path)


if __name__ == "__main__":
    main()
