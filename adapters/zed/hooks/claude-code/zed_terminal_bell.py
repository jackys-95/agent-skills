#!/usr/bin/env python3
"""Claude Code bell hook: ring the terminal bell so Zed marks the thread.

Zed shows a terminal thread's blue dot as soon as the terminal receives a bell.
Claude Code captures hook stdout and a /dev/tty write fails silently from a hook,
so this resolves the parent process's controlling tty and writes the bell there.
Registered for Stop and PermissionRequest.
Never blocks Claude Code: every failure is swallowed and the exit code is 0.
"""
import os
import re
import subprocess
import sys

TTY_NAME = re.compile(r"^[A-Za-z0-9]+$")


def parent_tty():
    """Return the parent's tty device name (e.g. ttys003), or None."""
    result = subprocess.run(
        ["ps", "-o", "tty=", "-p", str(os.getppid())],
        capture_output=True,
        text=True,
        timeout=5,
    )
    name = result.stdout.strip()
    if name.startswith("/dev/"):
        name = name[len("/dev/"):]
    # "??" / "?" mean no controlling terminal; anything else odd is rejected
    # so the write can never be steered at an unexpected path.
    return name if TTY_NAME.match(name) else None


def main():
    if not os.environ.get("CC_ZED_HOOK"):
        return 0
    try:
        tty = parent_tty()
        if tty:
            with open(f"/dev/{tty}", "w") as device:
                device.write("\a")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
