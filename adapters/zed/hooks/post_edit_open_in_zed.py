#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import threading


def _race(path):
    """Block until file is saved (fswatch) or buffer is closed (zed --wait)."""
    done = threading.Event()
    procs = []

    def run(cmd):
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append(p)
        p.wait()
        done.set()

    threads = [
        threading.Thread(target=run, args=(["fswatch", "-1", path],), daemon=True),
        threading.Thread(target=run, args=(["zed", "--wait", path],), daemon=True),
    ]
    for t in threads:
        t.start()
    done.wait()
    for p in procs:
        try:
            p.kill()
        except Exception:
            pass


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
    _race(file_path)


if __name__ == "__main__":
    main()
