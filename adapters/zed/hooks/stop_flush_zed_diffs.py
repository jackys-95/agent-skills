#!/usr/bin/env python3
"""Stop hook: flush the turn's edits into ONE Zed multi-diff.

The pre-hook accumulates a per-(session, file) marker for every file edited during
the turn instead of opening a diff per edit. Opening a diff fronts Zed (the 1.9.0
CLI always activates on open, with no open-without-activate flag), so per-edit
opens steal focus on every write — jarring on a single monitor and, worse, able to
misroute keystrokes into Zed while the user types elsewhere. Batching to the Stop
boundary fronts Zed once per turn, when CC has just finished and the user is not
mid-typing-elsewhere.
"""
import glob
import json
import os
import subprocess
import sys
import time

from _zed_common import gen_path, pointer_path, resolve_zed, seen_glob


def main():
    if not os.environ.get("CC_ZED_HOOK"):
        sys.exit(0)
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    session_id = event.get("session_id", "")
    markers = glob.glob(seen_glob(session_id))
    if not markers:
        sys.exit(0)

    # Build the manifest: one (base, file) pair per file edited this turn. Read the
    # file path from the marker's contents; the base is the turn-start snapshot the
    # pre-hook pointed at (kept from the FIRST edit this turn), or /dev/null for a
    # file with no snapshot (a new file — renders as all-additions). Sort for a
    # stable pane order. Clear markers as we go so the next turn starts clean even
    # if the diff open below fails.
    edits = []  # list of (file_path, base)
    for marker in sorted(markers):
        try:
            file_path = open(marker).read().strip()
        except OSError:
            file_path = ""
        try:
            os.remove(marker)
        except OSError:
            pass
        if not file_path:
            continue
        pointer = pointer_path(file_path)
        snapshot = open(pointer).read().strip() if os.path.isfile(pointer) else ""
        base = snapshot if snapshot and os.path.isfile(snapshot) else os.devnull
        edits.append((file_path, base))

    if not edits:
        sys.exit(0)

    zed = resolve_zed()
    if not zed:
        print(
            "[Zed] `zed` CLI not found on PATH or in /Applications/Zed.app — "
            "diff pane skipped. Fix: in Zed run command palette → `cli: install`, "
            "or `brew install --cask zed`. Verify with `zed --version`.",
            file=sys.stderr,
        )
        # Exit 1 so the first stderr line surfaces to the user as a hook-error
        # notice. The tools already ran — nothing blocks.
        sys.exit(1)

    # `-a`/`--add` opens the diff in the currently focused workspace instead of
    # letting Zed pick a window by its own heuristic — without it, a diff on a file
    # OUTSIDE the focused project swaps the active window's project (see TASK-0012).
    # `--diff` is repeatable and, given many pairs, renders them in a SINGLE
    # multi-diff pane — so a large turn opens one pane, not one window per file, and
    # Zed fronts exactly once. Every operand is a `--diff` pair (never a bare path),
    # so no path attaches to the workspace as a loose worktree. New files diff
    # against /dev/null. Verified against Zed 1.9.0.
    cmd = [zed, "-a"]
    for file_path, base in edits:
        cmd += ["--diff", base, file_path]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # tmux edit-injector: when CC runs in a tmux pane, watch each file for a manual
    # Cmd+S in the diff and inject the saved delta back into the pane. One watcher
    # per file that has a real snapshot base (new files against /dev/null have none).
    tmux_pane = os.environ.get("TMUX_PANE")
    if tmux_pane:
        injector = os.path.join(os.path.dirname(__file__), "tmux_diff_injector.py")
        for file_path, base in edits:
            if base == os.devnull:
                continue
            gen_token = str(time.time())
            with open(gen_path(file_path), "w") as f:
                f.write(gen_token)
            subprocess.Popen(
                ["python3", injector, file_path, base, tmux_pane, gen_token],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


if __name__ == "__main__":
    main()
