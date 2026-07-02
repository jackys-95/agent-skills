#!/usr/bin/env python3
"""Prune stale worktree roots from Zed's workspace DB.

Zed persists every folder it has ever opened as a root in `trusted_worktrees`
and in `workspaces.paths`, and REPLAYS them on session-restore. A memory-bank
directory that some earlier (pre-fix) tooling opened as a root therefore keeps
reappearing in the project panel after restart — it looks like a live bug but is
just persisted residue. This script removes that residue.

It targets two classes of stale root:
  1. Out-of-project residue — paths under a task-memory-bank tree (these should
     never be Zed roots; the diff hook opens them as diff buffers, not folders).
  2. Dead paths — roots whose directory no longer exists on disk (e.g. deleted
     /tmp test fixtures) that only produce "could not be canonicalized" errors.

Safe by default:
  - Refuses to run while Zed is running (SQLite is locked / would be clobbered).
  - Dry-run unless --apply is passed.
  - Backs up the DB before any write.

Usage:
    python3 prune_stale_roots.py            # dry run: show what would be pruned
    python3 prune_stale_roots.py --apply    # back up, then prune

Quit Zed (Cmd+Q) before running with --apply.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

# A root under any of these path segments is memory-bank residue, not a project.
MEMORY_BANK_MARKERS = ("/memory/task-memory-bank/", "/task-memory-bank/")

DEFAULT_DB = (
    Path.home()
    / "Library"
    / "Application Support"
    / "Zed"
    / "db"
    / "0-stable"
    / "db.sqlite"
)


def zed_is_running() -> bool:
    try:
        return (
            subprocess.run(
                ["pgrep", "-x", "zed"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            == 0
        )
    except FileNotFoundError:
        return False


def is_memory_bank_path(path: str) -> bool:
    # Residue if the path lives inside a task-memory-bank tree, OR if it is the
    # container that directly holds one (e.g. `~/memory` holding `task-memory-bank/`).
    # The second check is precise — it matches only real memory-bank parents, not
    # arbitrary `~/memory`-style directories on other machines.
    if any(marker in path for marker in MEMORY_BANK_MARKERS):
        return True
    if path.rstrip("/").endswith("/task-memory-bank"):
        return True
    return os.path.isdir(os.path.join(path, "task-memory-bank"))


def is_dead_path(path: str) -> bool:
    # Roots are directories; a root that is not an existing dir is dead residue.
    return not os.path.isdir(path)


def classify(path: str) -> str | None:
    """Return a reason string if the path is stale residue, else None."""
    if is_memory_bank_path(path):
        return "memory-bank residue"
    if is_dead_path(path):
        return "dead path (not on disk)"
    return None


def find_stale_trusted(conn: sqlite3.Connection) -> list[tuple[int, str, str]]:
    rows = conn.execute(
        "SELECT trust_id, absolute_path FROM trusted_worktrees ORDER BY trust_id"
    ).fetchall()
    out = []
    for trust_id, path in rows:
        reason = classify(path)
        if reason:
            out.append((trust_id, path, reason))
    return out


def find_stale_workspace_roots(
    conn: sqlite3.Connection,
) -> list[tuple[int, list[str], list[str]]]:
    """Workspaces whose `paths` include a memory-bank root among other roots.

    Returns (workspace_id, stale_roots, kept_roots). Only reported (not
    auto-rewritten) — editing multi-root `paths`/`paths_order` in place is
    fiddly and rare; surface it for manual review instead.
    """
    rows = conn.execute(
        "SELECT workspace_id, paths FROM workspaces WHERE paths IS NOT NULL AND paths != ''"
    ).fetchall()
    out = []
    for ws_id, paths in rows:
        roots = paths.split("\n")
        stale = [r for r in roots if is_memory_bank_path(r)]
        if stale:
            kept = [r for r in roots if r not in stale]
            out.append((ws_id, stale, kept))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db", default=str(DEFAULT_DB), help="Path to Zed's workspace db.sqlite."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete (default is a dry run). Backs up the DB first.",
    )
    args = parser.parse_args()

    db_path = Path(args.db).expanduser()
    if not db_path.is_file():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 1

    if zed_is_running():
        print(
            "Zed is running — quit it (Cmd+Q) before pruning. SQLite is locked "
            "while Zed is open, and Zed may overwrite the DB on exit, clobbering "
            "any changes.",
            file=sys.stderr,
        )
        return 1

    conn = sqlite3.connect(str(db_path))
    try:
        stale_trusted = find_stale_trusted(conn)
        stale_ws = find_stale_workspace_roots(conn)

        if not stale_trusted and not stale_ws:
            print("No stale roots found — nothing to prune.")
            return 0

        if stale_trusted:
            print("Stale trusted_worktrees rows:")
            for trust_id, path, reason in stale_trusted:
                print(f"  [{trust_id}] {path}  ({reason})")

        if stale_ws:
            print("\nWorkspaces with a memory-bank root (review manually):")
            for ws_id, stale, kept in stale_ws:
                print(f"  workspace {ws_id}:")
                for r in stale:
                    print(f"    - REMOVE: {r}")
                for r in kept:
                    print(f"    - keep:   {r}")
            print(
                "  (not auto-edited — if a workspace should lose its memory-bank\n"
                "   root, remove that folder from the project panel in Zed instead,\n"
                "   or delete the whole workspace row if it is disposable.)"
            )

        if not args.apply:
            print("\nDry run. Re-run with --apply to delete the trusted_worktrees rows above.")
            return 0

        backup = db_path.with_suffix(db_path.suffix + f".bak-{int(time.time())}")
        shutil.copy2(db_path, backup)
        print(f"\nBacked up DB -> {backup}")

        ids = [trust_id for trust_id, _, _ in stale_trusted]
        if ids:
            conn.executemany(
                "DELETE FROM trusted_worktrees WHERE trust_id = ?",
                [(i,) for i in ids],
            )
            conn.commit()
            print(f"Deleted {len(ids)} stale trusted_worktrees row(s): {ids}")
        else:
            print("No trusted_worktrees rows to delete.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
