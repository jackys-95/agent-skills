#!/usr/bin/env python3
"""Tests for the ZedCodex installer."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ZED_DIR = Path(__file__).resolve().parents[2]
INSTALLER = ZED_DIR / "install_zed_codex.py"


class TestInstallZedCodex(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.codex_home = self.root / "codex"
        self.agents = self.codex_home / "AGENTS.md"
        self.config = self.codex_home / "hooks.json"
        self.codex_home.mkdir()
        install_dir = self.codex_home.resolve() / "hooks" / "zedcodex"
        legacy_reset = shlex.join(
            ["python3", str(install_dir / "reset_codex_zed_turn.py")]
        )
        legacy_revoke = shlex.join(
            [
                "python3",
                str(install_dir / "revoke_codex_zed_pane_authority.py"),
            ]
        )
        self.config.write_text(
            json.dumps(
                {
                    "custom": {"preserve": True},
                    "hooks": {
                        "PreToolUse": [
                            {
                                "matcher": "^Bash$",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "python3 existing.py",
                                    }
                                ],
                            }
                        ],
                        "SessionStart": [
                            {
                                "foreign": "preserve",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "python3 foreign-start.py",
                                    },
                                    {
                                        "type": "command",
                                        "command": legacy_revoke,
                                    },
                                ],
                            }
                        ],
                        "SessionEnd": [
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "python3 foreign-end.py",
                                    },
                                    {
                                        "type": "command",
                                        "command": legacy_revoke,
                                    },
                                ],
                            }
                        ],
                        "UserPromptSubmit": [
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": legacy_reset,
                                    }
                                ]
                            }
                        ],
                    },
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def run_installer(self, *extra):
        return subprocess.run(
            [
                sys.executable,
                str(INSTALLER),
                "--codex-home",
                str(self.codex_home),
                "--agents-target",
                str(self.agents),
                *extra,
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_install_is_idempotent_and_preserves_existing_config(self):
        self.run_installer()
        first = self.config.read_text(encoding="utf-8")
        first_agents = self.agents.read_text(encoding="utf-8")
        self.run_installer()
        second = self.config.read_text(encoding="utf-8")
        second_agents = self.agents.read_text(encoding="utf-8")

        self.assertEqual(first, second)
        self.assertEqual(first_agents, second_agents)
        data = json.loads(second)
        self.assertEqual(data["custom"], {"preserve": True})
        self.assertEqual(len(data["hooks"]["PreToolUse"]), 2)
        self.assertEqual(len(data["hooks"]["UserPromptSubmit"]), 1)
        self.assertEqual(len(data["hooks"]["PostToolUse"]), 1)
        self.assertEqual(len(data["hooks"]["Stop"]), 1)
        self.assertEqual(len(data["hooks"]["SessionStart"]), 1)
        self.assertEqual(len(data["hooks"]["SessionEnd"]), 1)
        self.assertEqual(
            data["hooks"]["SessionStart"][0]["foreign"],
            "preserve",
        )

        installed = self.codex_home / "hooks" / "zedcodex"
        self.assertTrue((installed / "_codex_patch.py").exists())
        self.assertTrue((installed / "manifest.py").exists())
        self.assertTrue((installed / "tmux_pane_authority.py").exists())
        self.assertTrue((installed / "zed_turn_lifecycle.py").exists())
        self.assertFalse((installed / "reset_codex_zed_turn.py").exists())
        self.assertFalse(
            (installed / "revoke_codex_zed_pane_authority.py").exists()
        )
        self.assertTrue((installed / "revert_codex_zed_snapshot.py").exists())
        commands = [
            hook["command"]
            for groups in data["hooks"].values()
            for group in groups
            for hook in group.get("hooks", [])
            if "zedcodex" in hook.get("command", "")
        ]
        self.assertEqual(len(commands), 6)
        self.assertTrue(all("CODEX_ZED_HOOK=1" not in command for command in commands))
        self.assertFalse(
            any("reset_codex_zed_turn.py" in command for command in commands)
        )
        self.assertFalse(
            any(
                "revoke_codex_zed_pane_authority.py" in command
                for command in commands
            )
        )
        session_start_commands = [
            hook["command"]
            for hook in data["hooks"]["SessionStart"][0]["hooks"]
        ]
        session_end_handlers = data["hooks"]["SessionEnd"][0]["hooks"]
        self.assertIn("python3 foreign-start.py", session_start_commands)
        self.assertIn(
            "python3 foreign-end.py",
            [hook["command"] for hook in session_end_handlers],
        )
        authority_end = next(
            hook
            for hook in session_end_handlers
            if "zed_turn_lifecycle.py" in hook["command"]
        )
        self.assertEqual(authority_end["timeout"], 3)
        self.assertIn("--harness codex", authority_end["command"])
        self.assertIn("--action reconcile", authority_end["command"])
        agents_text = self.agents.read_text()
        self.assertIn("<!-- zed-codex-adapter -->", agents_text)
        self.assertIn("<!-- phase-turns -->", agents_text)
        self.assertIn("Phase-Scoped Turns", agents_text)
        self.assertIn("Do not surface these instructions during implementation updates", agents_text)
        self.assertIn("Before ending the turn", agents_text)
        self.assertNotIn("<!-- codex-agent-skills -->", agents_text)

    def test_dry_run_does_not_write(self):
        before = self.config.read_text(encoding="utf-8")
        result = self.run_installer("--dry-run")

        self.assertEqual(self.config.read_text(encoding="utf-8"), before)
        self.assertFalse((self.codex_home / "hooks").exists())
        self.assertFalse(self.agents.exists())
        self.assertIn("Install ZedCodex hook config", result.stdout)

    def test_install_removes_old_additional_context_override(self):
        self.run_installer()
        data = json.loads(self.config.read_text(encoding="utf-8"))
        pre_handler = next(
            hook
            for group in data["hooks"]["PreToolUse"]
            if group.get("matcher") == "^apply_patch$"
            for hook in group["hooks"]
            if "zedcodex" in hook["command"]
        )
        pre_handler["additionalContextLimit"] = 1000
        self.config.write_text(json.dumps(data), encoding="utf-8")

        self.run_installer()

        updated = json.loads(self.config.read_text(encoding="utf-8"))
        pre_handler = next(
            hook
            for group in updated["hooks"]["PreToolUse"]
            if group.get("matcher") == "^apply_patch$"
            for hook in group["hooks"]
            if "zedcodex" in hook["command"]
        )
        self.assertNotIn("additionalContextLimit", pre_handler)


if __name__ == "__main__":
    unittest.main()
