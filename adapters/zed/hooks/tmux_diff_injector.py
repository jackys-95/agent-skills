#!/usr/bin/env python3
import difflib
import os
import subprocess
import sys
import time

from _zed_common import gen_path

file_path, tmux_pane, gen_token = sys.argv[1], sys.argv[3], sys.argv[4]

TIMEOUT = 120


def gen_stale():
    try:
        return open(gen_path(file_path)).read().strip() != gen_token
    except OSError:
        return True


deadline = time.time() + TIMEOUT

with open(file_path) as f:
    before = f.read()

try:
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            sys.exit(0)
        subprocess.run(
            ["fswatch", "-1", file_path],
            timeout=remaining,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        with open(file_path) as f:
            after = f.read()
        if after != before:
            break
        # Content unchanged (Zed's internal write) — keep waiting

    if gen_stale():
        sys.exit(0)
    diff = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{os.path.basename(file_path)}",
            tofile=f"b/{os.path.basename(file_path)}",
        )
    )
    msg = f"[Zed edit] {os.path.basename(file_path)} was saved with changes:\n{diff}"
    subprocess.run(["tmux", "send-keys", "-t", tmux_pane, "-l", msg])
    subprocess.run(["tmux", "send-keys", "-t", tmux_pane, "Enter"])
except subprocess.TimeoutExpired:
    sys.exit(0)
