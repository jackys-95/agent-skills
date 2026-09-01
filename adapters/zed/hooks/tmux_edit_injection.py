#!/usr/bin/env python3
"""Shared Zed/tmux file-watch and prompt-injection mechanics.

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

from snapshot_revert import path_hash

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


def watcher_supersession_token_path(namespace, file_path):
    """Return the marker path used to supersede older watchers for one file."""
    return f"/tmp/{namespace}_gen_{path_hash(file_path)}"


def rotate_watcher_supersession_token(namespace, file_path, token=None):
    """Persist and return a token that supersedes prior watchers for one file."""
    token = str(time.time()) if token is None else token
    with open(
        watcher_supersession_token_path(namespace, file_path),
        "w",
        encoding="utf-8",
    ) as token_file:
        token_file.write(token)
    return token


def is_current_watcher_supersession_token(namespace, file_path, expected_token):
    """Return whether the expected token still identifies the newest watcher."""
    try:
        with open(
            watcher_supersession_token_path(namespace, file_path),
            encoding="utf-8",
        ) as token_file:
            return token_file.read().strip() == expected_token
    except OSError:
        return False


def launch_watchers(edits, tmux_pane, *, namespace):
    """Launch one detached watcher process for each completed manifest entry."""
    worker_path = os.path.abspath(__file__)
    for file_path, base in edits:
        token = rotate_watcher_supersession_token(namespace, file_path)
        subprocess.Popen(
            [
                "python3",
                worker_path,
                file_path,
                base,
                tmux_pane,
                namespace,
                token,
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
    if change is None or not should_inject():
        return False

    before, after = change
    send_message(tmux_pane, build_message(file_path, before, after))
    return True


def main(argv=None):
    """Run one watcher process from serialized launch arguments."""
    argv = sys.argv[1:] if argv is None else argv
    file_path, _base, tmux_pane, namespace, expected_token = argv

    watch_and_inject(
        file_path,
        tmux_pane,
        should_inject=lambda: is_current_watcher_supersession_token(
            namespace, file_path, expected_token
        ),
    )


if __name__ == "__main__":
    main()
