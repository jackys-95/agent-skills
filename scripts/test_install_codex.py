#!/usr/bin/env python3
"""Tests for the Codex installer."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import install_codex  # noqa: E402


def quiet_call(func, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return func(*args, **kwargs)


class TestInstallCodex(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_main_installs_skills_wrappers_and_agents_guidance(self) -> None:
        target = self.tmp / "skills"
        agents = self.tmp / "AGENTS.md"
        codex_home = self.tmp / "codex"
        argv = [
            "install_codex.py",
            "--skip-qmd",
            "--target",
            str(target),
            "--agents-target",
            str(agents),
            "--codex-home",
            str(codex_home),
        ]

        with mock.patch.object(sys, "argv", argv):
            self.assertEqual(quiet_call(install_codex.main), 0)

        expected_skills = [
            "task-memory-bank",
            "query-kb",
            "knowledge-files",
            "memory-init-project",
            "memory-new-work",
            "memory-resume",
            "memory-update",
            "memory-branch",
            "memory-handoff",
            "memory-reindex",
            "memory-doctor",
        ]
        for name in expected_skills:
            self.assertTrue((target / name / "SKILL.md").exists(), name)

        wrapper = (target / "memory-resume" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: memory-resume", wrapper)
        self.assertIn("task-memory-bank/SKILL.md", wrapper)
        self.assertIn("memory.resume", wrapper)

        helper_name = "codex_memory_permissions.py"
        init_helper = target / "memory-init-project" / "scripts" / helper_name
        doctor_helper = target / "memory-doctor" / "scripts" / helper_name
        self.assertTrue(init_helper.exists())
        self.assertTrue(doctor_helper.exists())
        self.assertFalse((target / "memory-resume" / "scripts" / helper_name).exists())

        init_wrapper = (target / "memory-init-project" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        doctor_wrapper = (target / "memory-doctor" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("codex_memory_permissions.py check", init_wrapper)
        self.assertIn("explicit `backfill`", init_wrapper)
        self.assertIn("codex_memory_permissions.py check", doctor_wrapper)

        agents_text = agents.read_text(encoding="utf-8")
        self.assertIn("<!-- codex-agent-skills -->", agents_text)
        self.assertIn("$memory-resume", agents_text)
        self.assertNotIn("<!-- zed-codex-adapter -->", agents_text)
        self.assertNotIn("<!-- phase-turns -->", agents_text)
        self.assertNotIn("codex_memory_permissions.py", agents_text)
        hooks = json.loads((codex_home / "hooks.json").read_text(encoding="utf-8"))
        self.assertEqual(
            set(hooks["hooks"]),
            {"PostToolUse", "UserPromptSubmit", "SessionStart", "SessionEnd"},
        )
        self.assertEqual(
            hooks["hooks"]["SessionStart"][0]["matcher"],
            "^(startup|resume|clear)$",
        )
        self.assertEqual(hooks["hooks"]["SessionEnd"][0]["hooks"][0]["timeout"], 3)
        runtime = codex_home / "hooks" / "agent-skills"
        self.assertTrue((runtime / "post_apply_patch_mark_dirty.py").exists())
        self.assertTrue((runtime / "reindex_dirty_collections.py").exists())
        self.assertTrue((runtime / "reindex_state.py").exists())

    def test_main_skip_agents_leaves_agents_target_untouched(self) -> None:
        target = self.tmp / "skills"
        agents = self.tmp / "AGENTS.md"
        codex_home = self.tmp / "codex"
        argv = [
            "install_codex.py",
            "--skip-qmd",
            "--skip-agents",
            "--target",
            str(target),
            "--agents-target",
            str(agents),
            "--codex-home",
            str(codex_home),
        ]

        with mock.patch.object(sys, "argv", argv):
            self.assertEqual(quiet_call(install_codex.main), 0)

        self.assertTrue((target / "task-memory-bank" / "SKILL.md").exists())
        self.assertFalse(agents.exists())

    def test_main_dry_run_writes_nothing(self) -> None:
        target = self.tmp / "skills"
        agents = self.tmp / "AGENTS.md"
        codex_home = self.tmp / "codex"
        argv = [
            "install_codex.py",
            "--dry-run",
            "--skip-qmd",
            "--target",
            str(target),
            "--agents-target",
            str(agents),
            "--codex-home",
            str(codex_home),
        ]

        with mock.patch.object(sys, "argv", argv):
            self.assertEqual(quiet_call(install_codex.main), 0)

        self.assertFalse(target.exists())
        self.assertFalse(agents.exists())
        self.assertFalse(codex_home.exists())

    def test_main_skip_qmd_does_not_call_qmd_install(self) -> None:
        target = self.tmp / "skills"
        agents = self.tmp / "AGENTS.md"
        codex_home = self.tmp / "codex"
        argv = [
            "install_codex.py",
            "--skip-qmd",
            "--target",
            str(target),
            "--agents-target",
            str(agents),
            "--codex-home",
            str(codex_home),
        ]

        with mock.patch.object(sys, "argv", argv):
            with mock.patch.object(install_codex, "install_qmd_skill") as install_qmd:
                self.assertEqual(quiet_call(install_codex.main), 0)

        install_qmd.assert_not_called()

    def test_installer_does_not_modify_codex_config(self) -> None:
        target = self.tmp / "skills"
        agents = self.tmp / "AGENTS.md"
        codex_home = self.tmp / "codex"
        config = self.tmp / "config.toml"
        config.write_text('sandbox_mode = "read-only"\n', encoding="utf-8")
        argv = [
            "install_codex.py",
            "--skip-qmd",
            "--target",
            str(target),
            "--agents-target",
            str(agents),
            "--codex-home",
            str(codex_home),
        ]

        with mock.patch.object(sys, "argv", argv):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(install_codex.main(), 0)

        self.assertEqual(
            config.read_text(encoding="utf-8"), 'sandbox_mode = "read-only"\n'
        )
        self.assertIn("run the installed helper", output.getvalue())
        self.assertIn("once during setup", output.getvalue())

    def test_reindex_hook_install_is_idempotent_and_preserves_existing_hooks(self) -> None:
        target = self.tmp / "skills"
        agents = self.tmp / "AGENTS.md"
        codex_home = self.tmp / "codex"
        codex_home.mkdir()
        config = codex_home / "hooks.json"
        config.write_text(
            json.dumps(
                {
                    "custom": {"preserve": True},
                    "hooks": {
                        "PostToolUse": [
                            {
                                "matcher": "^apply_patch$",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "python3 existing.py",
                                    }
                                ],
                            }
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )
        argv = [
            "install_codex.py",
            "--skip-qmd",
            "--target",
            str(target),
            "--agents-target",
            str(agents),
            "--codex-home",
            str(codex_home),
        ]

        with mock.patch.object(sys, "argv", argv):
            self.assertEqual(quiet_call(install_codex.main), 0)
            self.assertEqual(quiet_call(install_codex.main), 0)

        data = json.loads(config.read_text(encoding="utf-8"))
        self.assertEqual(data["custom"], {"preserve": True})
        post_handlers = data["hooks"]["PostToolUse"][0]["hooks"]
        self.assertEqual(len(post_handlers), 2)
        for event in ("UserPromptSubmit", "SessionStart", "SessionEnd"):
            self.assertEqual(len(data["hooks"][event]), 1)
            self.assertEqual(len(data["hooks"][event][0]["hooks"]), 1)

    def test_install_agents_md_is_idempotent_and_preserves_user_content(self) -> None:
        source = install_codex.ADAPTER_DIR / "AGENTS.md"
        target = self.tmp / "AGENTS.md"
        target.write_text("# User Notes\n\nKeep me.\n", encoding="utf-8")

        quiet_call(install_codex.install_agents_md, source, target, dry_run=False)
        first = target.read_text(encoding="utf-8")
        quiet_call(install_codex.install_agents_md, source, target, dry_run=False)
        second = target.read_text(encoding="utf-8")

        self.assertEqual(first, second)
        self.assertIn("# User Notes", first)
        self.assertIn("Keep me.", first)
        self.assertIn("<!-- codex-agent-skills -->", first)


if __name__ == "__main__":
    unittest.main()
