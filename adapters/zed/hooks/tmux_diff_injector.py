#!/usr/bin/env python3
import difflib
import os
import subprocess
import sys

file_path, tmux_pane = sys.argv[1], sys.argv[3]


def fswatch_once():
    subprocess.run(
        ["fswatch", "-1", file_path],
        timeout=120,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


try:
    fswatch_once()  # discard — Zed writes the file when opening the diff view
    with open(file_path) as f:
        before = f.read()
    fswatch_once()  # user's save
    with open(file_path) as f:
        after = f.read()

    if after == before:
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
    pass
