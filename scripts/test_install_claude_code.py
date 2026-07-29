#!/usr/bin/env python3
"""Tests for the Claude Code installer orchestration."""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import install_claude_code  # noqa: E402


def quiet_call(func, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return func(*args, **kwargs)


class TestInstallClaudeCode(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_main_dry_run_writes_nothing(self) -> None:
        target = self.tmp / "skills"
        argv = [
            "install_claude_code.py",
            "--dry-run",
            "--target",
            str(target),
        ]

        with mock.patch.object(sys, "argv", argv):
            self.assertEqual(quiet_call(install_claude_code.main), 0)

        self.assertFalse(target.exists())
        self.assertFalse((self.tmp / "CLAUDE.md").exists())

    def test_install_reindex_hooks_dry_run_does_not_load_or_save_settings(self) -> None:
        with mock.patch.object(install_claude_code, "load_settings") as load_settings:
            with mock.patch.object(install_claude_code, "save_settings") as save_settings:
                quiet_call(install_claude_code.install_reindex_hooks, dry_run=True)

        load_settings.assert_not_called()
        save_settings.assert_not_called()


if __name__ == "__main__":
    unittest.main()
