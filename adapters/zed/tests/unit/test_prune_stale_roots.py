#!/usr/bin/env python3
"""Unit tests for prune_stale_roots: residue classification + workspace rewrite.

Run: python3 test_prune_stale_roots.py

Stdlib only (unittest + tempfile + sqlite3). Builds a throwaway sqlite mirroring
the columns the tool touches — no real Zed DB, no Zed running. The load-bearing
tests are (a) the knowledge/ false-positive guard (a real repo with a knowledge/
subdir must NOT be flagged) and (b) the workspace rewrite's three cases:
multi-root drop, all-stale delete, and UNIQUE-collision delete.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import prune_stale_roots as p


def _db() -> sqlite3.Connection:
    """A sqlite mirroring the workspace-path columns + the UNIQUE(paths) index."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """CREATE TABLE workspaces (
            workspace_id INTEGER PRIMARY KEY,
            paths TEXT,
            paths_order TEXT,
            identity_paths TEXT,
            identity_paths_order TEXT
        )"""
    )
    conn.execute("CREATE UNIQUE INDEX ix_paths ON workspaces (paths)")
    return conn


def _insert(conn, ws_id, paths, order="", ident=None, ident_order=None):
    conn.execute(
        "INSERT INTO workspaces (workspace_id, paths, paths_order, identity_paths, identity_paths_order) "
        "VALUES (?,?,?,?,?)",
        (ws_id, "\n".join(paths), order, ident, ident_order),
    )


class ClassifyTests(unittest.TestCase):
    def test_task_memory_bank_inside_is_residue(self):
        self.assertTrue(p.is_residue_path("/Users/x/memory/task-memory-bank/projects/foo"))

    def test_knowledge_inside_is_residue(self):
        self.assertTrue(p.is_residue_path("/Users/x/Documents/example-program/knowledge/technical"))

    def test_repo_with_knowledge_subdir_is_NOT_residue(self):
        # A real project repo that merely contains a knowledge/ folder must not
        # be flagged — knowledge gets the inside-marker only, no container check.
        d = Path(tempfile.mkdtemp())
        (d / "knowledge").mkdir()
        self.assertFalse(p.is_residue_path(str(d)))

    def test_container_holding_task_memory_bank_is_residue(self):
        d = Path(tempfile.mkdtemp())
        (d / "task-memory-bank").mkdir()
        self.assertTrue(p.is_residue_path(str(d)))

    def test_plain_project_root_is_not_residue(self):
        self.assertFalse(p.is_residue_path("/Users/x/github/agent-skills"))

    def test_dead_path_classifies(self):
        self.assertEqual(p.classify("/no/such/dir/anywhere"), "dead path (not on disk)")


class RewriteTests(unittest.TestCase):
    def test_multi_root_drops_stale_keeps_real(self):
        conn = _db()
        _insert(
            conn, 28,
            ["/Users/x/Documents/example-program/task-memory-bank/projects/foo", "/Users/x/github/agent-skills"],
            order="1,0",
            ident="/Users/x/Documents/example-program/task-memory-bank/projects/foo\n/Users/x/github/agent-skills",
            ident_order="1,0",
        )
        stale = p.find_stale_workspace_roots(conn)
        log = p.rewrite_workspace_roots(conn, stale)
        row = conn.execute(
            "SELECT paths, paths_order, identity_paths, identity_paths_order FROM workspaces WHERE workspace_id=28"
        ).fetchone()
        self.assertEqual(row[0], "/Users/x/github/agent-skills")  # only the real root survives
        self.assertEqual(row[1], "")                               # order blanked -> Zed rebuilds
        self.assertIsNone(row[2])                                  # identity_paths nulled
        self.assertIsNone(row[3])
        self.assertIn("dropped 1 stale root", log[0])

    def test_all_stale_deletes_row(self):
        conn = _db()
        _insert(conn, 5, ["/Users/x/memory/task-memory-bank/projects/only"])
        stale = p.find_stale_workspace_roots(conn)
        log = p.rewrite_workspace_roots(conn, stale)
        self.assertIsNone(
            conn.execute("SELECT 1 FROM workspaces WHERE workspace_id=5").fetchone()
        )
        self.assertIn("row deleted", log[0])

    def test_unique_collision_deletes_redundant_row(self):
        conn = _db()
        # A single-root agent-skills workspace already exists...
        _insert(conn, 10, ["/Users/x/github/agent-skills"])
        # ...and a second, polluted one whose survivor would collide with it.
        _insert(
            conn, 11,
            ["/Users/x/memory/task-memory-bank/projects/foo", "/Users/x/github/agent-skills"],
        )
        stale = p.find_stale_workspace_roots(conn)
        log = p.rewrite_workspace_roots(conn, stale)
        # The pre-existing row stays; the redundant polluted one is deleted.
        self.assertIsNotNone(conn.execute("SELECT 1 FROM workspaces WHERE workspace_id=10").fetchone())
        self.assertIsNone(conn.execute("SELECT 1 FROM workspaces WHERE workspace_id=11").fetchone())
        self.assertTrue(any("redundant row deleted" in line for line in log))

    def test_clean_workspace_untouched(self):
        conn = _db()
        _insert(conn, 1, ["/Users/x/github/agent-skills"])
        self.assertEqual(p.find_stale_workspace_roots(conn), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
