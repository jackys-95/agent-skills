#!/usr/bin/env python3
"""PostToolUse hook: confirm successful apply_patch paths in the turn manifest."""

import json
import os
import sys

import manifest
from _codex_patch import paths_from_event

NAMESPACE = "codex_zed"


def main():
    if not os.environ.get("CODEX_ZED_HOOK"):
        return
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    session_id = event.get("session_id", "")
    for path in paths_from_event(event):
        manifest.mark_touched(NAMESPACE, session_id, path)


if __name__ == "__main__":
    main()
