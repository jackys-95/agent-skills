#!/usr/bin/env python3
"""Tests for the ZedCC installer."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ZED_DIR = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "zed_cc_install",
    ZED_DIR / "install_zed_cc.py",
)
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

    def test_installer_copies_combined_tmux_edit_injection_runtime(self):
        runtime_names = {source.name for source in zed_install.SCRIPTS}

        self.assertIn("tmux_edit_injection.py", runtime_names)
        self.assertIn("tmux_pane_authority.py", runtime_names)
        self.assertNotIn("tmux_injection.py", runtime_names)
        self.assertNotIn("tmux_diff_injector.py", runtime_names)

    def test_lifecycle_hooks_merge_with_foreign_matcherless_entries(self):
        legacy_start = zed_install.hook_command(
            zed_install.CLAUDE_HOOKS_DIR / "revoke_zed_pane_authority.py"
        )
        settings = {
            "hooks": {
                "SessionStart": [
                    {
                        "foreign": "preserve",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python3 foreign-start.py",
                            },
                            {"type": "command", "command": legacy_start},
                        ],
                    }
                ],
                "SessionEnd": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python3 foreign-end.py",
                            }
                        ],
                    }
                ],
            }
        }
        lifecycle = [
            hook
            for hook in zed_install.HOOKS
            if hook["event"] in {"SessionStart", "SessionEnd"}
        ]

        for hook in lifecycle:
            zed_install.install_hook(
                settings,
                hook["event"],
                hook["dest"],
                hook["matcher"],
                args=hook.get("args", ()),
                legacy_commands=hook.get("legacy_commands", ()),
            )
            zed_install.install_hook(
                settings,
                hook["event"],
                hook["dest"],
                hook["matcher"],
                args=hook.get("args", ()),
                legacy_commands=hook.get("legacy_commands", ()),
            )

        self.assertEqual(len(settings["hooks"]["SessionStart"]), 1)
        self.assertEqual(len(settings["hooks"]["SessionEnd"]), 1)
        self.assertEqual(
            settings["hooks"]["SessionStart"][0]["foreign"],
            "preserve",
        )
        for event, foreign in (
            ("SessionStart", "python3 foreign-start.py"),
            ("SessionEnd", "python3 foreign-end.py"),
        ):
            commands = [
                hook["command"]
                for hook in settings["hooks"][event][0]["hooks"]
            ]
            self.assertIn(foreign, commands)
            self.assertEqual(
                sum("zed_turn_lifecycle.py" in item for item in commands),
                1,
            )
            self.assertFalse(
                any("revoke_zed_pane_authority.py" in item for item in commands)
            )

    def test_all_cc_hook_names_are_shared_or_explicitly_cc_specific(self):
        destinations = {hook["dest"].name for hook in zed_install.HOOKS}

        self.assertIn("zed_turn_lifecycle.py", destinations)
        self.assertIn(
            "stop_flush_claude_code_zed_diffs.py",
            destinations,
        )
        self.assertNotIn("reset_zed_turn.py", destinations)
        self.assertNotIn("stop_flush_zed_diffs.py", destinations)

    def test_installer_removes_obsolete_tmux_runtime_files(self):
        hooks_dir = Path(self.tmp.name) / "hooks"
        hooks_dir.mkdir()
        combined = hooks_dir / "tmux_edit_injection.py"
        combined.write_text("current", encoding="utf-8")
        for name in zed_install.OBSOLETE_SCRIPTS:
            (hooks_dir / name).write_text("obsolete", encoding="utf-8")

        with mock.patch.object(zed_install, "CLAUDE_HOOKS_DIR", hooks_dir):
            zed_install.remove_obsolete_scripts()

        self.assertTrue(combined.exists())
        for name in zed_install.OBSOLETE_SCRIPTS:
            self.assertFalse((hooks_dir / name).exists())


if __name__ == "__main__":
    unittest.main()
