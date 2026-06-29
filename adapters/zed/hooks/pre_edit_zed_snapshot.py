#!/usr/bin/env python3
import json
import os
import shutil
import sys
import time

from _zed_common import pointer_path, snapshot_path

ONE_MS_AS_NS = 1_000_000


def main():
    if not os.environ.get("CC_ZED_HOOK"):
        sys.exit(0)
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    file_path = event.get("tool_input", {}).get("file_path", "")
    if not file_path or not os.path.isfile(file_path):
        sys.exit(0)

    ts_in_ms = int(time.time_ns() // ONE_MS_AS_NS)
    snapshot = snapshot_path(file_path, ts_in_ms)

    shutil.copyfile(file_path, snapshot)

    # Pointer lets post-hook find this snapshot without recomputing the timestamp.
    with open(pointer_path(file_path), "w") as f:
        f.write(snapshot)

    rel = os.path.relpath(file_path)
    print(f"[Zed] snapshot={snapshot} | Diff opening for {rel} — reply 'r' to revert.")


if __name__ == "__main__":
    main()
