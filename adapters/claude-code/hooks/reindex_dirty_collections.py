#!/usr/bin/env python3
"""Lifecycle hook: reindex every dirty memory-bank / knowledge-base collection.

Registered on THREE events, all of which fire AFTER a turn's Zed diff review window
has closed — so reindex never captures an about-to-be-reverted edit:

  UserPromptSubmit — start of the next turn; covers every turn but the last.
  SessionEnd       — covers the final turn of a clean session (no next turn).
  SessionStart     — crash-recovery net: only does work if a prior session was
                     hard-killed after a write, leaving a marker behind. In a clean
                     session the markers were already cleared, so this no-ops.

For each dirty collection: run `qmd update` once (global change-scan — qmd has no
per-collection update), then `qmd embed -c <collection>` (the expensive pass, scoped
to just that collection) via `memory_bank.py reindex --collection <name>`. Runs
DETACHED with output suppressed so it never churns the pane. Markers are cleared up
front so a second lifecycle event doesn't double-reindex.

See docs/task-memory-bank-reindex-hooks.md.
"""
import os
import subprocess
import sys

from _reindex_common import clear_marker, dirty_collections


def find_memory_bank():
    """Locate the deployed memory_bank.py.

    The installer deploys this hook to <claude-dir>/hooks/ and the skill to
    <claude-dir>/skills/, so the script is a sibling-tree lookup from this file's
    own location. TMB_MEMORY_BANK overrides for non-default --target installs.
    """
    override = os.environ.get("TMB_MEMORY_BANK")
    if override:
        override = os.path.expanduser(override)
        return override if os.path.isfile(override) else None

    hooks_dir = os.path.dirname(os.path.abspath(__file__))
    claude_dir = os.path.dirname(hooks_dir)
    path = os.path.join(
        claude_dir, "skills", "task-memory-bank", "scripts", "memory_bank.py"
    )
    return path if os.path.isfile(path) else None


def main():
    collections = dirty_collections()
    if not collections:
        sys.exit(0)

    script = find_memory_bank()
    if not script:
        # No reindexer available — clear markers so we don't spin every event, and
        # exit quietly. (The skill still works; the index is just stale until a
        # manual reindex.)
        for name in collections:
            clear_marker(name)
        sys.exit(0)

    # Clear markers BEFORE launching so a near-simultaneous second lifecycle event
    # (e.g. SessionEnd right after a final UserPromptSubmit) sees a clean slate and
    # doesn't queue a duplicate reindex.
    names = sorted(set(collections))
    for name in names:
        clear_marker(name)

    # Run the reindexes SEQUENTIALLY in ONE detached process, not parallel Popens:
    # each `reindex` runs `qmd update` (a global change-scan — no per-collection flag)
    # then `qmd embed -c <name>`, and concurrent `qmd update`s would race on the same
    # sqlite index. Chaining with `&&` in one background `sh -c` serializes them and
    # keeps the whole job off the hook's critical path (detached, output suppressed).
    # Common case is a single dirty collection, so this is usually one call; the rare
    # multi-collection boundary pays a redundant (cheap) `qmd update` per collection.
    chain = " && ".join(
        f"python3 {script} reindex --collection {name}" for name in names
    )
    subprocess.Popen(
        ["sh", "-c", chain],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


if __name__ == "__main__":
    main()
