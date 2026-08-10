#!/usr/bin/env python3
"""Unit tests for the turn-scoped manifest built on top of snapshot_revert.

Run: python3 test_manifest.py
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
import manifest
import snapshot_revert as sr

NS = "test_ns_manifest"


def tearDownModule():
    for path in glob.glob(f"/tmp/{NS}_*"):
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            os.remove(path)


class SeedIfNewTests(unittest.TestCase):
    def test_first_seed_returns_base_and_records_entry(self):
        session = "seed1"
        d = Path(tempfile.mkdtemp())
        f = d / "a.txt"
        f.write_text("original")

        base = manifest.seed_if_new(NS, session, str(f))
        self.assertNotEqual(base, None)
        self.assertNotEqual(base, manifest.NEW)
        self.assertEqual(Path(base).read_text(), "original")

    def test_second_seed_same_turn_is_noop_and_keeps_first_base(self):
        session = "seed2"
        d = Path(tempfile.mkdtemp())
        f = d / "a.txt"
        f.write_text("first content")

        first_base = manifest.seed_if_new(NS, session, str(f))
        f.write_text("second content")
        second_result = manifest.seed_if_new(NS, session, str(f))

        self.assertIsNone(second_result)
        self.assertEqual(Path(first_base).read_text(), "first content")

    def test_new_file_seeds_new_sentinel(self):
        session = "seed3"
        path = str(Path(tempfile.mkdtemp()) / "does_not_exist_yet.txt")

        base = manifest.seed_if_new(NS, session, path)
        self.assertEqual(base, manifest.NEW)

    def test_mark_touched_is_safe_superset_of_seed_if_new(self):
        session = "seed4"
        d = Path(tempfile.mkdtemp())
        f = d / "a.txt"
        f.write_text("x")

        manifest.seed_if_new(NS, session, str(f))
        manifest.mark_touched(NS, session, str(f))  # must not raise or duplicate
        edits = manifest.close_turn(NS, session)
        self.assertEqual(len(edits), 1)


class CloseTurnTests(unittest.TestCase):
    def test_close_turn_returns_all_entries_and_deletes_manifest(self):
        session = "close1"
        d = Path(tempfile.mkdtemp())
        f1, f2 = d / "a.txt", d / "b.txt"
        f1.write_text("1")
        f2.write_text("2")
        manifest.seed_if_new(NS, session, str(f1))
        manifest.seed_if_new(NS, session, str(f2))

        edits = manifest.close_turn(NS, session)
        self.assertEqual({e[0] for e in edits}, {str(f1), str(f2)})
        self.assertFalse(os.path.isfile(sr.manifest_path(NS, session)))

    def test_close_turn_on_missing_manifest_returns_empty(self):
        self.assertEqual(manifest.close_turn(NS, "never-opened-session"), [])

    def test_close_turn_reports_new_file_base_as_sentinel(self):
        session = "close2"
        path = str(Path(tempfile.mkdtemp()) / "brand_new.txt")
        manifest.seed_if_new(NS, session, path)
        edits = manifest.close_turn(NS, session)
        self.assertEqual(edits, [(path, manifest.NEW)])


class ClearTurnTests(unittest.TestCase):
    def test_clear_turn_removes_manifest_for_session_only(self):
        session, other = "clear1", "clear1-other"
        d = Path(tempfile.mkdtemp())
        f = d / "a.txt"
        f.write_text("x")
        manifest.seed_if_new(NS, session, str(f))
        manifest.seed_if_new(NS, other, str(f))

        manifest.clear_turn(NS, session)

        self.assertFalse(os.path.isfile(sr.manifest_path(NS, session)))
        self.assertTrue(os.path.isfile(sr.manifest_path(NS, other)))

    def test_clear_turn_on_missing_manifest_does_not_raise(self):
        manifest.clear_turn(NS, "never-opened-session-2")


class BulkSeedTests(unittest.TestCase):
    def test_bulk_seed_seeds_every_file_under_roots(self):
        session = "bulk1"
        d = Path(tempfile.mkdtemp())
        (d / "a.txt").write_text("1")
        (d / "sub").mkdir()
        (d / "sub" / "b.txt").write_text("2")

        manifest.bulk_seed(NS, session, [str(d)], cwd=str(d))
        edits = manifest.close_turn(NS, session)
        self.assertEqual(len(edits), 2)

    def test_bulk_seed_skips_dot_git(self):
        session = "bulk2"
        d = Path(tempfile.mkdtemp())
        (d / ".git").mkdir()
        (d / ".git" / "HEAD").write_text("ref: refs/heads/main")
        (d / "a.txt").write_text("1")

        manifest.bulk_seed(NS, session, [str(d)])
        edits = manifest.close_turn(NS, session)
        self.assertEqual([e[0] for e in edits], [str(d / "a.txt")])


if __name__ == "__main__":
    unittest.main(verbosity=2)
