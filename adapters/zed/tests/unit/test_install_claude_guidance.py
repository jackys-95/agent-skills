#!/usr/bin/env python3
"""Tests for the Zed + Claude Code guidance installer."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ZED_DIR = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("zed_install", ZED_DIR / "install.py")
zed_install = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(zed_install)


class TestInstallClaudeGuidance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.target = Path(self.tmp.name) / "CLAUDE.md"
        self.target.write_text(
            "# User notes\n\n"
            "<!-- zed-launch-context -->\nOld launch\n<!-- zed-launch-context -->\n\n"
            "<!-- zed-adapter -->\nOld review\n<!-- zed-adapter -->\n\n"
            "<!-- phase-turns -->\nOld phases\n<!-- phase-turns -->\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_install_is_idempotent_and_replaces_all_zed_blocks(self):
        with mock.patch.object(zed_install, "CLAUDE_MD", self.target):
            zed_install.install_claude_md()
            first = self.target.read_text(encoding="utf-8")
            zed_install.install_claude_md()
            second = self.target.read_text(encoding="utf-8")

        self.assertEqual(first, second)
        self.assertIn("# User notes", first)
        self.assertNotIn("Old launch", first)
        self.assertNotIn("Old review", first)
        self.assertNotIn("Old phases", first)
        self.assertEqual(first.count("<!-- zed-launch-context -->"), 2)
        self.assertEqual(first.count("<!-- zed-adapter -->"), 2)
        self.assertEqual(first.count("<!-- phase-turns -->"), 2)
        self.assertIn("How CC Is Launched in Zed", first)
        self.assertIn("Zed Adapter Behavior", first)
        self.assertIn("Phase-Scoped Turns", first)


if __name__ == "__main__":
    unittest.main()
