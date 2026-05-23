#!/usr/bin/env python3
import hashlib
import json
import os
import subprocess
import sys


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

    path_hash = hashlib.sha256(file_path.encode()).hexdigest()[:16]
    pointer = f"/tmp/cc_pre_ptr_{path_hash}"
    snapshot = open(pointer).read().strip() if os.path.isfile(pointer) else ""

    if snapshot and os.path.isfile(snapshot):
        subprocess.Popen(
            ["zed", "--diff", snapshot, file_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        subprocess.Popen(
            ["zed", file_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    subprocess.run(
        ["osascript", "-e", 'tell application "Zed" to activate'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Snapshot left in /tmp — PreToolUse overwrites it on the next edit to the same file


if __name__ == "__main__":
    main()
