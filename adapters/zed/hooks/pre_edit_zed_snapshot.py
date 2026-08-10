#!/usr/bin/env python3
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

    # Snapshot ONCE per file per turn so the diff base is the file's turn-start
    # state: N edits to the same file in one turn still show original→final and
    # revert restores the pre-turn version. seed_if_new keeps the first entry of the
    # turn — a later edit this turn returns None (no-op) below.
    base = manifest.seed_if_new(NAMESPACE, session_id, file_path)
    if base is None:
        sys.exit(0)

    rel = os.path.relpath(file_path)
    if base == manifest.NEW:
        # New file (Write creating it): no turn-start content exists. Revert of a
        # "new" base means delete, restoring the pre-turn state ("did not exist").
        print(f"[Zed] new file {rel} — created this turn; diff opens at end of turn; reply 'r {rel}' to revert (deletes it).")
    else:
        print(f"[Zed] snapshot={base} | edit queued for {rel} — diff opens at end of turn; reply 'r {rel}' to revert.")


if __name__ == "__main__":
    main()
