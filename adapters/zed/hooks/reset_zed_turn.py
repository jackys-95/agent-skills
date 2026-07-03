#!/usr/bin/env python3
"""UserPromptSubmit hook: mark the start of a new CC turn for the Zed adapter.

Clears this session's per-turn snapshot markers so the next PreToolUse edit
captures a fresh turn-start base. Snapshots batch per turn and flush on Stop; a
turn is one user prompt, so the boundary is reset here. Session-scoped, so
concurrent Zed threads never clear each other's markers.
"""
import glob
import json
import os
import sys

from _zed_common import seen_glob


def main():
    if not os.environ.get("CC_ZED_HOOK"):
        sys.exit(0)
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    session_id = event.get("session_id", "")
    for marker in glob.glob(seen_glob(session_id)):
        try:
            os.remove(marker)
        except OSError:
            pass


if __name__ == "__main__":
    main()
