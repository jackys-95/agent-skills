#!/usr/bin/env python3
"""Tests for Codex qmd dirty detection and the shared marker runtime."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
HOOKS_DIR = REPO_ROOT / "adapters" / "codex" / "hooks"
RUNTIME_DIR = REPO_ROOT / "adapters" / "core"
DETECTOR = HOOKS_DIR / "post_apply_patch_mark_dirty.py"

sys.path.insert(0, str(RUNTIME_DIR))
from reindex_state import collection_for_path, load_collections  # noqa: E402


class ReindexStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.config = self.root / "config"
        self.markers = self.root / "markers"
        self.collection = self.root / "knowledge"
        self.nested = self.collection / "nested"
        self.nested.mkdir(parents=True)
        index = self.config / "qmd" / "index.yml"
        index.parent.mkdir(parents=True)
        index.write_text(
            "collections:\n"
            "  knowledge:\n"
            f"    path: {self.collection}\n"
            '    pattern: "**/*.md"\n'
            "  nested:\n"
            f"    path: {self.nested}\n"
            '    pattern: "**/*.md"\n',
            encoding="utf-8",
        )
        self.env = {
            **os.environ,
            "XDG_CONFIG_HOME": str(self.config),
            "TMB_REINDEX_MARKER_DIR": str(self.markers),
            "PYTHONPATH": os.pathsep.join([str(HOOKS_DIR), str(RUNTIME_DIR)]),
        }

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_longest_registered_root_wins(self) -> None:
        with mock.patch.dict(os.environ, self.env, clear=True):
            collections = load_collections()
            self.assertEqual(
                collection_for_path(self.nested / "topic.md", collections),
                "nested",
            )

    def test_apply_patch_marks_each_changed_collection(self) -> None:
        event = {
            "cwd": str(self.root),
            "tool_name": "apply_patch",
            "tool_input": {
                "command": (
                    "*** Begin Patch\n"
                    "*** Update File: knowledge/topic.md\n"
                    "@@\n"
                    "+changed\n"
                    "*** Update File: knowledge/nested/other.md\n"
                    "@@\n"
                    "+changed\n"
                    "*** End Patch\n"
                )
            },
        }

        subprocess.run(
            [sys.executable, str(DETECTOR)],
            input=json.dumps(event),
            text=True,
            env=self.env,
            check=True,
        )

        self.assertEqual(
            (self.markers / "tmb_qmd_dirty_knowledge").read_text(encoding="utf-8"),
            "knowledge",
        )
        self.assertEqual(
            (self.markers / "tmb_qmd_dirty_nested").read_text(encoding="utf-8"),
            "nested",
        )

    def test_outside_path_is_ignored(self) -> None:
        event = {
            "cwd": str(self.root),
            "tool_input": {
                "command": (
                    "*** Begin Patch\n"
                    "*** Update File: outside.md\n"
                    "*** End Patch\n"
                )
            },
        }
        subprocess.run(
            [sys.executable, str(DETECTOR)],
            input=json.dumps(event),
            text=True,
            env=self.env,
            check=True,
        )
        self.assertFalse(self.markers.exists())


if __name__ == "__main__":
    unittest.main()
