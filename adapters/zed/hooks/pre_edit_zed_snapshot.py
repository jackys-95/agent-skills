#!/usr/bin/env python3
import json
import os
import shutil
import sys
import time

from _zed_common import pointer_path, seen_marker, snapshot_path

ONE_MS_AS_NS = 1_000_000


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
    # revert restores the pre-turn version. The marker (written by the post-hook,
    # cleared on UserPromptSubmit) signals "base already captured this turn" — on
    # later edits we keep the first snapshot/pointer untouched.
    if os.path.isfile(seen_marker(session_id, file_path)):
        sys.exit(0)

    # New file (Write creating it): no turn-start content exists. Record a
    # /dev/null pointer instead of a snapshot so revert deletes the file, restoring
    # the pre-turn state ("did not exist"). The post-hook still records the marker,
    # so the first Write pins /dev/null as the base and a later same-turn edit keeps
    # it. The Stop hook already diffs a /dev/null base as all-additions.
    if not os.path.isfile(file_path):
        with open(pointer_path(file_path), "w") as f:
            f.write(os.devnull)
        rel = os.path.relpath(file_path)
        print(f"[Zed] new file {rel} — created this turn; diff opens at end of turn; reply 'r {rel}' to revert (deletes it).")
        sys.exit(0)

    ts_in_ms = int(time.time_ns() // ONE_MS_AS_NS)
    snapshot = snapshot_path(file_path, ts_in_ms)
    shutil.copyfile(file_path, snapshot)

    # Pointer lets the Stop hook and revert find this snapshot by file path.
    with open(pointer_path(file_path), "w") as f:
        f.write(snapshot)

    rel = os.path.relpath(file_path)
    print(f"[Zed] snapshot={snapshot} | edit queued for {rel} — diff opens at end of turn; reply 'r {rel}' to revert.")


if __name__ == "__main__":
    main()
