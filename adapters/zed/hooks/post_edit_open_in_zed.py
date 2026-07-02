#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import time

from _zed_common import gen_path, pointer_path, resolve_zed


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

    pointer = pointer_path(file_path)
    snapshot = open(pointer).read().strip() if os.path.isfile(pointer) else ""

    zed = resolve_zed()
    if not zed:
        print(
            "[Zed] `zed` CLI not found on PATH or in /Applications/Zed.app — "
            "diff pane skipped. Fix: in Zed run command palette → `cli: install`, "
            "or `brew install --cask zed`. Verify with `zed --version`.",
            file=sys.stderr,
        )
        # Exit 1 so the first stderr line surfaces to the user as a hook-error
        # notice. Exit 0 would bury it in transcript-only output; exit 2 routes
        # it to Claude rather than the user. The tool already ran — nothing blocks.
        sys.exit(1)

    # `-a`/`--add` opens the diff in the currently focused workspace instead of
    # letting Zed pick a window by its own heuristic. Without it, a diff on a file
    # OUTSIDE the focused project (e.g. a task-memory-bank file, or a cross-package
    # edit in a multi-repo workspace) makes Zed reuse some other workspace and swap
    # the active window's project. `-a` pins the diff to the focused window and
    # preserves its root; in-project diffs were never affected. Verified against
    # Zed 1.9.0, including concurrent multi-file bursts.
    #
    # Both branches use `--diff` so the path opens as a diff buffer, never a
    # project worktree. A bare `zed -a <path>` (new file, no snapshot) attaches
    # the out-of-project path to the focused workspace as a loose worktree and
    # bloats its recent-projects entry; `--diff` operands do not. New files have
    # no prior snapshot, so we diff them against an empty base (`/dev/null`) —
    # the whole file renders as additions. Verified clean against Zed 1.9.0.
    base = snapshot if snapshot and os.path.isfile(snapshot) else os.devnull
    subprocess.Popen(
        [zed, "-a", "--diff", base, file_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # No explicit `osascript ... activate` here: the `zed -a --diff` call above
    # already raises Zed on its own (the CLI activates the app when it opens a
    # buffer, and there's no flag to suppress that). An earlier version opened a
    # plain buffer (`zed --wait <file>`) that didn't reliably front the app, so it
    # needed the activate; the diff CLI made that redundant. There is no clean way
    # to open the diff while keeping Zed backgrounded — restoring the prior
    # frontmost app afterward flickers — so we accept that a diff fronts Zed.
    tmux_pane = os.environ.get("TMUX_PANE")
    if tmux_pane and snapshot and os.path.isfile(snapshot):
        gen_token = str(time.time())
        gen_file = gen_path(file_path)
        with open(gen_file, "w") as f:
            f.write(gen_token)
        subprocess.Popen(
            [
                "python3",
                os.path.join(os.path.dirname(__file__), "tmux_diff_injector.py"),
                file_path,
                snapshot,
                tmux_pane,
                gen_token,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    # Snapshot left in /tmp — PreToolUse overwrites it on the next edit to the same file


if __name__ == "__main__":
    main()
