#!/usr/bin/env python3
"""Stop hook: open one Zed multi-diff for the completed Codex turn."""

import filecmp
import json
import os
import subprocess
import sys

import manifest
from _zed_common import resolve_zed

NAMESPACE = "codex_zed"


def _warn(message):
    # Stop requires structured stdout. systemMessage is user-visible but does not
    # ask Codex to continue the completed turn.
    print(json.dumps({"systemMessage": message}))


def _unchanged(base, path):
    try:
        return filecmp.cmp(base, path, shallow=False)
    except OSError:
        return False


def main():
    if not os.environ.get("CODEX_ZED_HOOK"):
        return
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    edits = manifest.close_turn(NAMESPACE, event.get("session_id", ""))
    if not edits:
        return

    pairs = []
    for path, base in edits:
        if base == manifest.NEW:
            # A file added and then removed in the same turn has no final change.
            if not os.path.exists(path):
                continue
            pair = (os.devnull, path)
        elif not os.path.exists(path):
            pair = (base, os.devnull)
        else:
            # PreToolUse runs even when apply_patch later fails. Suppress paths
            # whose final contents still match their turn-start snapshots.
            if _unchanged(base, path):
                continue
            pair = (base, path)
        pairs.append(pair)

    if not pairs:
        return

    zed = resolve_zed()
    if not zed:
        _warn(
            "[Zed] `zed` CLI not found; end-of-turn review was skipped. "
            "Install the Zed CLI and verify with `zed --version`."
        )
        return

    cmd = [zed, "-a"]
    for left, right in pairs:
        cmd += ["--diff", left, right]

    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        _warn(f"[Zed] failed to open end-of-turn review: {exc}")


if __name__ == "__main__":
    main()
