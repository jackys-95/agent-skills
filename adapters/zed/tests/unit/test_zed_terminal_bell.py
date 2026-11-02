#!/usr/bin/env python3
"""Tests for the opt-in Zed terminal bell hook."""

from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path
from unittest import mock

ZED_DIR = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "zed_terminal_bell",
    ZED_DIR / "hooks" / "claude-code" / "zed_terminal_bell.py",
)
bell = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bell)


def ps_result(stdout):
    return mock.Mock(stdout=stdout)


class TestParentTty(unittest.TestCase):
    def tty_for(self, stdout):
        with mock.patch.object(bell.subprocess, "run", return_value=ps_result(stdout)):
            return bell.parent_tty()

    def test_plain_tty_name(self):
        self.assertEqual(self.tty_for("ttys003\n"), "ttys003")

    def test_padded_and_dev_prefixed_names(self):
        self.assertEqual(self.tty_for("  ttys003 \n"), "ttys003")
        self.assertEqual(self.tty_for("/dev/ttys003\n"), "ttys003")

    def test_no_controlling_terminal_is_skipped(self):
        self.assertIsNone(self.tty_for("??\n"))
        self.assertIsNone(self.tty_for("?\n"))
        self.assertIsNone(self.tty_for(""))

    def test_odd_names_are_rejected(self):
        self.assertIsNone(self.tty_for("../etc/passwd\n"))
        self.assertIsNone(self.tty_for("ttys003 ttys004\n"))

    def test_queries_the_parent_pid(self):
        with mock.patch.object(
            bell.subprocess, "run", return_value=ps_result("ttys001")
        ) as run:
            bell.parent_tty()
        self.assertEqual(run.call_args.args[0][-1], str(os.getppid()))


class TestMain(unittest.TestCase):
    def test_gated_on_cc_zed_hook(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
            bell, "parent_tty"
        ) as parent_tty:
            self.assertEqual(bell.main(), 0)
        parent_tty.assert_not_called()

    def test_writes_bell_to_parent_tty(self):
        with mock.patch.dict(os.environ, {"CC_ZED_HOOK": "1"}), mock.patch.object(
            bell, "parent_tty", return_value="ttys009"
        ), mock.patch("builtins.open", mock.mock_open()) as opened:
            self.assertEqual(bell.main(), 0)
        opened.assert_called_once_with("/dev/ttys009", "w")
        opened().write.assert_called_once_with("\a")

    def test_no_tty_writes_nothing(self):
        with mock.patch.dict(os.environ, {"CC_ZED_HOOK": "1"}), mock.patch.object(
            bell, "parent_tty", return_value=None
        ), mock.patch("builtins.open", mock.mock_open()) as opened:
            self.assertEqual(bell.main(), 0)
        opened.assert_not_called()

    def test_failures_never_block(self):
        with mock.patch.dict(os.environ, {"CC_ZED_HOOK": "1"}), mock.patch.object(
            bell, "parent_tty", side_effect=OSError("boom")
        ):
            self.assertEqual(bell.main(), 0)
        with mock.patch.dict(os.environ, {"CC_ZED_HOOK": "1"}), mock.patch.object(
            bell, "parent_tty", return_value="ttys009"
        ), mock.patch("builtins.open", side_effect=PermissionError):
            self.assertEqual(bell.main(), 0)


if __name__ == "__main__":
    unittest.main()
