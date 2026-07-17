#!/usr/bin/env python3
"""Prune stale worktree roots from Zed's workspace DB.

Zed persists every folder it has ever opened as a root in `trusted_worktrees`
and in `workspaces.paths`, and REPLAYS them on session-restore. An out-of-project
directory that some earlier out-of-project `zed -a` write opened as a root keeps
reappearing in the project panel after restart. Worse, while it persists on a
real project's workspace it acts as an ancestor "home" for out-of-project files,
so `zed -a --diff` routes those diffs into that window (issue #58). This script
removes that residue.

It targets two classes of stale root:
  1. Out-of-project residue — paths inside a task-memory-bank OR knowledge-base
     tree, or a container that directly holds a task-memory-bank tree (these
     should never be Zed roots; the diff hook opens them as diff buffers).
  2. Dead paths — roots whose directory no longer exists on disk (e.g. deleted
     /tmp test fixtures) that only produce "could not be canonicalized" errors.

Two DB locations are cleaned:
  - `trusted_worktrees` rows — deleted directly (independent rows).
  - `workspaces.paths` multi-root entries — the stale root is dropped in place
    and `paths_order` blanked so Zed rebuilds order on load (see
    `rewrite_workspace_roots`); an all-stale or now-duplicate workspace row is
    deleted.

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

# A root whose path contains any of these segments is out-of-project residue,
# not a project a Zed window should mount. task-memory-bank AND knowledge-base
# trees both live outside app repos and get written by out-of-project CC edits,
# so a persisted root INSIDE either is residue (issue #58 — the knowledge-base
# case was a prior classification blind spot). These are substring markers, so a
# root is only residue when it sits *within* the tree, never a sibling repo that
# merely has a similarly named subdirectory.
RESIDUE_MARKERS = (
    "/memory/task-memory-bank/",
    "/task-memory-bank/",
    "/knowledge/",
)
# Only `task-memory-bank` is safe as a *container* marker (a root that directly
# holds it, e.g. `~/memory`): the name is specific enough to never collide with
# a real repo's subdirectory. `knowledge` is NOT — many legitimate project repos
# contain a `knowledge/` folder, so treating "holds a knowledge/ dir" as residue
# would wrongly flag (and delete) a real project root. So `knowledge` gets the
# inside-marker above only, never a container check.
RESIDUE_CONTAINER_DIRS = ("task-memory-bank",)

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


def is_residue_path(path: str) -> bool:
    # Residue if the path lives inside a task-memory-bank OR knowledge-base tree,
    # OR if it is (or directly holds) a container of a task-memory-bank tree.
    # The container check is restricted to `task-memory-bank` (see
    # RESIDUE_CONTAINER_DIRS) so it never flags a real repo that merely has a
    # `knowledge/` subdirectory.
    if any(marker in path for marker in RESIDUE_MARKERS):
        return True
    stripped = path.rstrip("/")
    for child in RESIDUE_CONTAINER_DIRS:
        if stripped.endswith("/" + child):
            return True
        if os.path.isdir(os.path.join(path, child)):
            return True
    return False


def is_dead_path(path: str) -> bool:
    # Roots are directories; a root that is not an existing dir is dead residue.
    return not os.path.isdir(path)


def classify(path: str) -> str | None:
    """Return a reason string if the path is stale residue, else None."""
    if is_residue_path(path):
        return "out-of-project residue (memory-bank / knowledge-base)"
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
    """Workspaces whose `paths` include a stale residue root among other roots.

    Returns (workspace_id, stale_roots, kept_roots). This is the case that
    magnetizes an out-of-project write into an unrelated window: a dangling
    residue root persisted on a real project's workspace acts as an ancestor
    home for the file, so `zed -a --diff` routes the diff there (issue #58).
    `rewrite_workspace_roots` applies the fix.
    """
    rows = conn.execute(
        "SELECT workspace_id, paths FROM workspaces WHERE paths IS NOT NULL AND paths != ''"
    ).fetchall()
    out = []
    for ws_id, paths in rows:
        roots = paths.split("\n")
        # Residue only — NOT dead-path detection. Dropping a root from a live
        # workspace is destructive, and a "dead" root is often just a real
        # project on a temporarily-unmounted volume (e.g. /Volumes/...). Dead
        # paths are only safe to prune from trusted_worktrees (Zed re-trusts on
        # next open), never from workspaces.paths.
        stale = [r for r in roots if is_residue_path(r)]
        if stale:
            kept = [r for r in roots if r not in stale]
            out.append((ws_id, stale, kept))
    return out


def rewrite_workspace_roots(
    conn: sqlite3.Connection, stale_ws: list[tuple[int, list[str], list[str]]]
) -> list[str]:
    """Drop stale residue roots from each workspace's `paths`, in place.

    Relies on Zed's own self-healing deserialize (`crates/util/src/path_list.rs`):
    `paths` is stored newline-joined and lexicographically SORTED, with a
    separate `paths_order` permutation. On load, if `order` length != `paths`
    length, Zed discards the stored order and rebuilds identity order from the
    sorted paths. So we need only (1) drop the stale lines — the survivors of an
    already-sorted list stay sorted — and (2) blank `paths_order` to force the
    rebuild. `identity_paths`/`identity_paths_order` (a git-resolved dedup copy)
    are nullable and fall back to `paths` when absent, so we null them rather
    than filter the resolved form.

    - all roots stale -> delete the workspace row (an empty workspace is inert).
    - `UNIQUE(remote_connection_id, paths)` collision (a single-root workspace
      for the survivor already exists) -> delete this now-redundant row instead
      of rewriting into a duplicate.

    Returns human-readable log lines describing what was done.
    """
    log: list[str] = []
    for ws_id, stale, kept in stale_ws:
        if not kept:
            conn.execute("DELETE FROM workspaces WHERE workspace_id = ?", (ws_id,))
            log.append(f"workspace {ws_id}: all roots stale -> row deleted")
            continue
        new_paths = "\n".join(kept)  # kept preserves the stored (sorted) order
        try:
            conn.execute(
                "UPDATE workspaces SET paths = ?, paths_order = '', "
                "identity_paths = NULL, identity_paths_order = NULL "
                "WHERE workspace_id = ?",
                (new_paths, ws_id),
            )
            log.append(
                f"workspace {ws_id}: dropped {len(stale)} stale root(s), "
                f"kept {len(kept)} (order rebuilt on next open)"
            )
        except sqlite3.IntegrityError:
            # A workspace for the surviving root set already exists (UNIQUE on
            # (remote_connection_id, paths)); this row is redundant residue.
            conn.execute("DELETE FROM workspaces WHERE workspace_id = ?", (ws_id,))
            log.append(
                f"workspace {ws_id}: survivor workspace already exists "
                f"-> redundant row deleted"
            )
    return log


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
            print("\nWorkspaces carrying a stale residue root (will be rewritten):")
            for ws_id, stale, kept in stale_ws:
                print(f"  workspace {ws_id}:")
                for r in stale:
                    print(f"    - REMOVE: {r}")
                for r in kept:
                    print(f"    - keep:   {r}")
                if not kept:
                    print("    (no roots survive -> the workspace row will be deleted)")

        if not args.apply:
            print("\nDry run. Re-run with --apply to prune the trusted_worktrees rows "
                  "and rewrite the workspaces above.")
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
            print(f"Deleted {len(ids)} stale trusted_worktrees row(s): {ids}")
        else:
            print("No trusted_worktrees rows to delete.")

        if stale_ws:
            for line in rewrite_workspace_roots(conn, stale_ws):
                print(line)

        conn.commit()
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
