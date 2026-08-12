#!/usr/bin/env python3
"""UserPromptSubmit hook: clear the parent Codex turn's Zed manifest."""

import json
import os
import sys

import manifest

NAMESPACE = "codex_zed"


def main():
    if not os.environ.get("CODEX_ZED_HOOK"):
        return
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    # Subagents share the parent session id but have independent prompt events.
    # The parent Stop is the review boundary, so a child prompt must not erase it.
    if "agent_id" in event:
        return
    manifest.clear_turn(NAMESPACE, event.get("session_id", ""))


if __name__ == "__main__":
    main()
