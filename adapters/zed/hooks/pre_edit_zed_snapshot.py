#!/usr/bin/env python3
import hashlib
import json
import os
import shutil
import sys


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

    path_hash = hashlib.sha256(file_path.encode()).hexdigest()[:16]
    ts = int(__import__("time").time_ns() // 1_000_000)
    snapshot = f"/tmp/cc_pre_{path_hash}_{ts}"

    shutil.copyfile(file_path, snapshot)

    # Pointer lets post-hook find this snapshot without recomputing the timestamp.
    with open(f"/tmp/cc_pre_ptr_{path_hash}", "w") as f:
        f.write(snapshot)

    rel = os.path.relpath(file_path)
    print(f"[Zed] snapshot={snapshot} | Diff opening for {rel} — reply 'r' to revert.")


if __name__ == "__main__":
    main()
