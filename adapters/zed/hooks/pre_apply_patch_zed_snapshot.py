#!/usr/bin/env python3
"""PreToolUse hook: snapshot every path named by a Codex apply_patch call."""

import json
import os
import sys

import manifest
from _codex_patch import canonical_path, paths_from_event

NAMESPACE = "codex_zed"


def _context_line(path, base, cwd):
    display_path = os.path.relpath(path, cwd or os.getcwd())
    if base == manifest.NEW:
        return (
            f"[Zed] new file {display_path} queued for end-of-turn review; "
            f"reply 'r {display_path}' to revert (deletes it)."
        )
    return (
        f"[Zed] edit queued for {display_path}; "
        f"reply 'r {display_path}' to restore its turn-start content."
    )


def main():
    if not os.environ.get("CODEX_ZED_HOOK"):
        return
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    session_id = event.get("session_id", "")
    cwd = canonical_path(".", event.get("cwd") or os.getcwd())
    context = []
    for path in paths_from_event(event):
        base = manifest.seed_if_new(NAMESPACE, session_id, path)
        if base is not None:
            context.append(_context_line(path, base, cwd))

    if context:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "additionalContext": "\n".join(context),
                    }
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
