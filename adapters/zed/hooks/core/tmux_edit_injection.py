#!/usr/bin/env python3
"""Core Zed/tmux file-watch and prompt-injection mechanics.

Harness hooks supply completed edits and lifecycle-specific injection guards. This
module owns the editor-specific watcher, message, and tmux transport behavior.
It is deployed as a flat file beside its callers, so keep it stdlib-only beyond
snapshot_revert.
"""

from __future__ import annotations

import difflib
import os
import subprocess
import sys
import time

import tmux_pane_authority as authority

WATCH_TIMEOUT = 120


def watch_command(file_path, platform=None):
    """Return the one-shot file-watcher command for the current platform."""
    platform = sys.platform if platform is None else platform
    commands = {
        "darwin": ["fswatch", "-1", file_path],
        "linux": [
            "inotifywait",
            "-e",
            "modify",
            "-e",
            "close_write",
            file_path,
        ],
    }
    return commands.get(platform)


def launch_watchers(edits, tmux_pane, *, expected_claim):
    """Launch one detached watcher process for each completed manifest entry."""
    worker_path = os.path.abspath(__file__)
    serialized_claim = authority.serialize_expected_claim(expected_claim)
    for file_path, base in edits:
        subprocess.Popen(
            [
                "python3",
                worker_path,
                file_path,
                base,
                tmux_pane,
                serialized_claim,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def wait_for_change(file_path, timeout=WATCH_TIMEOUT, platform=None):
    """Wait for content to differ from its value at watcher start."""
    command = watch_command(file_path, platform=platform)
    if command is None:
        return None

    deadline = time.time() + timeout
    with open(file_path, encoding="utf-8") as watched_file:
        before = watched_file.read()

    try:
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                return None
            subprocess.run(
                command,
                timeout=remaining,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            with open(file_path, encoding="utf-8") as watched_file:
                after = watched_file.read()
            if after != before:
                return before, after
            # Zed may write without changing content; keep waiting.
    except subprocess.TimeoutExpired:
        return None


def build_message(file_path, before, after):
    """Build the existing user-visible Zed edit notification."""
    filename = os.path.basename(file_path)
    diff = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
        )
    )
    return f"[Zed edit] {filename} was saved with changes:\n{diff}"


def send_message(tmux_pane, message):
    """Type a message into a tmux pane and submit it."""
    subprocess.run(["tmux", "send-keys", "-t", tmux_pane, "-l", message])
    subprocess.run(["tmux", "send-keys", "-t", tmux_pane, "Enter"])


def watch_and_inject(
    file_path,
    tmux_pane,
    *,
    should_inject,
    timeout=WATCH_TIMEOUT,
    platform=None,
):
    """Watch one file and inject its saved delta when the caller's guard allows."""
    change = wait_for_change(file_path, timeout=timeout, platform=platform)
    if change is None:
        return False

    before, after = change
    message = build_message(file_path, before, after)
    if not should_inject():
        return False
    send_message(tmux_pane, message)
    return True


def main(argv=None):
    """Run one watcher process from serialized launch arguments."""
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 4:
        return
    file_path, _base, tmux_pane, serialized_claim = argv
    expected_claim = authority.deserialize_expected_claim(serialized_claim)
    if expected_claim is None or expected_claim.tmux_pane != tmux_pane:
        return

    watch_and_inject(
        file_path,
        tmux_pane,
        should_inject=lambda: authority.is_current_pane_claim(expected_claim),
    )


if __name__ == "__main__":
    main()
