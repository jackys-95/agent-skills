#!/usr/bin/env python3
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

    # --wait blocks until the buffer is closed (save-and-close or discard-and-close)
    subprocess.run(["zed", "--wait", file_path])


if __name__ == "__main__":
    main()
