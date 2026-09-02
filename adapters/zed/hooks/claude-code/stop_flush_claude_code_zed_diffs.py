#!/usr/bin/env python3
"""Claude Code Stop hook: flush the turn into one Zed multi-diff.

The pre-hook accumulates a turn manifest instead of opening a diff per edit. Opening a
diff fronts Zed (the 1.9.0 CLI always activates on open, with no open-without-activate
flag), so per-edit opens steal focus on every write — jarring on a single monitor and,
worse, able to misroute keystrokes into Zed while the user types elsewhere. Batching to
the Stop boundary fronts Zed once per turn, when CC has just finished and the user is
not mid-typing-elsewhere.
"""
import json
import os
import subprocess
import sys

import manifest
import tmux_pane_authority as authority
from _zed_common import resolve_zed
from tmux_edit_injection import launch_watchers

NAMESPACE = "cc_zed"


def main():
    if not os.environ.get("CC_ZED_HOOK"):
        sys.exit(0)
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    session_id = event.get("session_id", "")
    edits = manifest.close_turn(NAMESPACE, session_id)
    if not edits:
        sys.exit(0)

    zed = resolve_zed()
    if not zed:
        if sys.platform == "darwin":
            hint = (
                "not found on PATH or in /Applications/Zed.app — diff pane "
                "skipped. Fix: in Zed run command palette → `cli: install`, "
                "or `brew install --cask zed`."
            )
        else:
            hint = (
                "not found on PATH or in ~/.local/bin — diff pane skipped. "
                "Fix: install Zed via https://zed.dev/download and ensure "
                "~/.local/bin is on PATH."
            )
        print(
            f"[Zed] `zed` CLI {hint} Verify with `zed --version`.",
            file=sys.stderr,
        )
        # Exit 1 so the first stderr line surfaces to the user as a hook-error
        # notice. The tools already ran — nothing blocks.
        sys.exit(1)

    # `-a`/`--add` opens the diff in the currently focused workspace instead of
    # letting Zed pick a window by its own heuristic — without it, a diff on a file
    # OUTSIDE the focused project swaps the active window's project.
    # `--diff` is repeatable and, given many pairs, renders them in a SINGLE
    # multi-diff pane — so a large turn opens one pane, not one window per file, and
    # Zed fronts exactly once. Every operand is a `--diff` pair (never a bare path),
    # so no path attaches to the workspace as a loose worktree. New files diff
    # against /dev/null — the manifest's "new" sentinel translates to the real
    # /dev/null path only here, at the Zed-CLI boundary. Verified against Zed 1.9.0.
    cmd = [zed, "-a"]
    for file_path, base in edits:
        zed_base = os.devnull if base == manifest.NEW else base
        cmd += ["--diff", zed_base, file_path]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # tmux edit-injector: when CC runs in a tmux pane, watch each file for a manual
    # Cmd+S in the diff and inject the saved delta back into the pane. One watcher
    # per edited file — including new files: the injector diffs the file's current
    # (CC-written) content against whatever the user saves, so it needs no base.
    tmux_server = os.environ.get("TMUX")
    tmux_pane = os.environ.get("TMUX_PANE")
    if tmux_server and tmux_pane and session_id:
        owner = authority.current_owner_identity()
        if owner is None:
            return
        expected_claim = authority.read_pane_claim(tmux_server, tmux_pane)
        identity = authority.PaneIdentity.from_owner("cc", session_id, owner)
        if not authority.claim_matches_identity(
            expected_claim,
            identity,
        ) or not authority.is_current_pane_claim(expected_claim):
            return
        launch_watchers(
            edits,
            tmux_pane,
            expected_claim=expected_claim,
        )


if __name__ == "__main__":
    main()
