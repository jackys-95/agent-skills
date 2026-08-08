#!/usr/bin/env python3
"""Unit tests for snapshot_revert: pure file-copy semantics, no manifest bookkeeping.

Run: python3 test_snapshot_revert.py
"""
from __future__ import annotations

import glob
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import snapshot_revert as sr

NS = "test_ns"


def tearDownModule():
    for path in glob.glob(f"/tmp/{NS}_*"):
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            os.remove(path)


class SnapshotTests(unittest.TestCase):
    def test_existing_file_is_copied_and_returns_snapshot_path(self):
        d = Path(tempfile.mkdtemp())
        f = d / "a.txt"
        f.write_text("original")
        base = sr.snapshot(NS, "snap1", str(f))
        self.assertNotEqual(base, sr.NEW)
        self.assertEqual(Path(base).read_text(), "original")

    def test_missing_file_returns_new_sentinel(self):
        base = sr.snapshot(NS, "snap2", "/tmp/does-not-exist-snapshot-revert-test.txt")
        self.assertEqual(base, sr.NEW)

    def test_snapshot_writes_a_pointer(self):
        d = Path(tempfile.mkdtemp())
        f = d / "a.txt"
        f.write_text("original")
        base = sr.snapshot(NS, "snap3", str(f))
        self.assertEqual(Path(sr.pointer_path(NS, str(f))).read_text(), base)

    def test_snapshot_dir_scoped_by_namespace_and_session(self):
        d1 = sr.snapshot_dir("ns_a", "s1")
        d2 = sr.snapshot_dir("ns_b", "s1")
        d3 = sr.snapshot_dir("ns_a", "s2")
        self.assertNotEqual(d1, d2)
        self.assertNotEqual(d1, d3)

    def test_pointer_path_scoped_by_namespace_only_not_session(self):
        """Pointers are process-wide by path — no session component — because revert
        must find them regardless of which session (or turn) captured them."""
        self.assertNotEqual(sr.pointer_path("ns_a", "/tmp/x"), sr.pointer_path("ns_b", "/tmp/x"))
        self.assertEqual(sr.pointer_path("ns_a", "/tmp/x"), sr.pointer_path("ns_a", "/tmp/x"))

    def test_sanitize_session_falls_back_for_empty(self):
        self.assertEqual(sr.sanitize_session(""), "nosession")
        self.assertEqual(sr.sanitize_session(None), "nosession")

    def test_sanitize_session_strips_unsafe_chars(self):
        self.assertEqual(sr.sanitize_session("a/b c!d"), "abcd")


class RevertTests(unittest.TestCase):
    def test_revert_restores_real_snapshot(self):
        d = Path(tempfile.mkdtemp())
        f = d / "a.txt"
        f.write_text("turn-start content")
        sr.snapshot(NS, "rev1", str(f))
        f.write_text("edited")

        ok = sr.revert(NS, str(f))
        self.assertTrue(ok)
        self.assertEqual(f.read_text(), "turn-start content")

    def test_revert_new_base_deletes_file(self):
        f = Path(tempfile.mkdtemp()) / "created_this_turn.txt"
        sr.snapshot(NS, "rev2", str(f))  # f doesn't exist yet -> pointer records "new"
        f.write_text("agent wrote this")

        ok = sr.revert(NS, str(f))
        self.assertTrue(ok)
        self.assertFalse(f.exists())

    def test_revert_new_base_already_gone_is_still_success(self):
        f = Path(tempfile.mkdtemp()) / "already_gone.txt"
        sr.snapshot(NS, "rev3", str(f))  # never actually created afterward

        ok = sr.revert(NS, str(f))
        self.assertTrue(ok)

    def test_revert_untracked_path_fails(self):
        ok = sr.revert(NS, "/tmp/never-tracked-by-any-pointer.txt")
        self.assertFalse(ok)

    def test_revert_survives_after_the_turn_manifest_is_gone(self):
        """revert() reads only the pointer file, never the turn manifest — the
        load-bearing property that keeps revert working after Stop has already
        deleted the manifest. The diff a user reverts from opens only after Stop
        runs, and the revert reply is itself a new turn's UserPromptSubmit — see
        TASK-0022 designs/core-api-plan.md."""
        d = Path(tempfile.mkdtemp())
        f = d / "b.txt"
        f.write_text("turn-start content")
        sr.snapshot(NS, "rev4", str(f))
        f.write_text("edited")
        manifest_file = sr.manifest_path(NS, "rev4")
        if os.path.isfile(manifest_file):
            os.remove(manifest_file)

        ok = sr.revert(NS, str(f))
        self.assertTrue(ok)
        self.assertEqual(f.read_text(), "turn-start content")


if __name__ == "__main__":
    unittest.main(verbosity=2)
