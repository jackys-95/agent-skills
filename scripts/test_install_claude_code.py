#!/usr/bin/env python3
"""Tests for the Claude Code installer orchestration."""

from __future__ import annotations

import contextlib
import copy
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
                quiet_call(
                    install_claude_code.install_reindex_hooks,
                    self.tmp / "skills",
                    dry_run=True,
                )

        load_settings.assert_not_called()
        save_settings.assert_not_called()

    def test_install_reindex_hooks_migrates_legacy_flush_commands(self) -> None:
        target = self.tmp / "skills"
        hooks_dir = self.tmp / "hooks"
        legacy_command = f"python3 {hooks_dir / 'reindex_dirty_collections.py'}"
        current_command = (
            f"{legacy_command} --memory-bank "
            f"{target / 'task-memory-bank' / 'scripts' / 'memory_bank.py'}"
        )
        unrelated = {
            "type": "command",
            "command": "python3 /custom/prompt_hook.py",
            "timeout": 7,
        }
        settings = {
            "custom": {"preserve": True},
            "hooks": {
                event: [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": legacy_command,
                                "timeout": 3,
                            },
                            copy.deepcopy(unrelated),
                        ]
                    }
                ]
                for event in ("UserPromptSubmit", "SessionEnd", "SessionStart")
            },
        }
        settings["hooks"]["SessionEnd"][0]["hooks"].insert(
            1,
            {
                "type": "command",
                "command": current_command,
                "timeout": 5,
            },
        )
        saved = []

        with mock.patch.object(
            install_claude_code,
            "CLAUDE_HOOKS_DIR",
            hooks_dir,
        ):
            with mock.patch.object(
                install_claude_code,
                "load_settings",
                return_value=settings,
            ):
                with mock.patch.object(
                    install_claude_code,
                    "save_settings",
                    side_effect=lambda data: saved.append(copy.deepcopy(data)),
                ):
                    quiet_call(
                        install_claude_code.install_reindex_hooks,
                        target,
                        dry_run=False,
                    )
                    quiet_call(
                        install_claude_code.install_reindex_hooks,
                        target,
                        dry_run=False,
                    )

        data = saved[-1]
        self.assertEqual(saved[-2], saved[-1])
        self.assertEqual(data["custom"], {"preserve": True})
        for event in ("UserPromptSubmit", "SessionEnd", "SessionStart"):
            commands = data["hooks"][event][0]["hooks"]
            self.assertEqual(
                sum(hook.get("command") == current_command for hook in commands),
                1,
            )
            self.assertFalse(
                any(hook.get("command") == legacy_command for hook in commands)
            )
            self.assertIn(unrelated, commands)
            migrated = next(
                hook for hook in commands if hook.get("command") == current_command
            )
            expected_timeout = 5 if event == "SessionEnd" else 3
            self.assertEqual(migrated["timeout"], expected_timeout)

    def test_main_has_no_zed_guidance_wiring(self) -> None:
        target = self.tmp / "skills"
        argv = ["install_claude_code.py", "--target", str(target)]

        with mock.patch.object(sys, "argv", argv):
            with mock.patch.object(install_claude_code, "install_canonical_skills"):
                with mock.patch.object(
                    install_claude_code,
                    "install_memory_bank_adapter",
                ) as install_adapter:
                    with mock.patch.object(install_claude_code, "install_plain_skills"):
                        with mock.patch.object(install_claude_code, "install_qmd_skill"):
                            with mock.patch.object(
                                install_claude_code, "install_reindex_hooks"
                            ):
                                self.assertEqual(
                                    quiet_call(install_claude_code.main),
                                    0,
                                )

        self.assertFalse((self.tmp / "CLAUDE.md").exists())
        install_adapter.assert_called_once_with(
            install_claude_code.REPO_ROOT,
            target.resolve(),
            False,
        )


if __name__ == "__main__":
    unittest.main()
