#!/usr/bin/env python3
"""Tests for the Codex installer."""

from __future__ import annotations

import contextlib
import io
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
        argv = [
            "install_codex.py",
            "--skip-qmd",
            "--target",
            str(target),
            "--agents-target",
            str(agents),
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

        agents_text = agents.read_text(encoding="utf-8")
        self.assertIn("<!-- codex-agent-skills -->", agents_text)
        self.assertIn("$memory-resume", agents_text)

    def test_main_skip_agents_leaves_agents_target_untouched(self) -> None:
        target = self.tmp / "skills"
        agents = self.tmp / "AGENTS.md"
        argv = [
            "install_codex.py",
            "--skip-qmd",
            "--skip-agents",
            "--target",
            str(target),
            "--agents-target",
            str(agents),
        ]

        with mock.patch.object(sys, "argv", argv):
            self.assertEqual(quiet_call(install_codex.main), 0)

        self.assertTrue((target / "task-memory-bank" / "SKILL.md").exists())
        self.assertFalse(agents.exists())

    def test_main_dry_run_writes_nothing(self) -> None:
        target = self.tmp / "skills"
        agents = self.tmp / "AGENTS.md"
        argv = [
            "install_codex.py",
            "--dry-run",
            "--skip-qmd",
            "--target",
            str(target),
            "--agents-target",
            str(agents),
        ]

        with mock.patch.object(sys, "argv", argv):
            self.assertEqual(quiet_call(install_codex.main), 0)

        self.assertFalse(target.exists())
        self.assertFalse(agents.exists())

    def test_main_skip_qmd_does_not_call_qmd_install(self) -> None:
        target = self.tmp / "skills"
        agents = self.tmp / "AGENTS.md"
        argv = [
            "install_codex.py",
            "--skip-qmd",
            "--target",
            str(target),
            "--agents-target",
            str(agents),
        ]

        with mock.patch.object(sys, "argv", argv):
            with mock.patch.object(install_codex, "install_qmd_skill") as install_qmd:
                self.assertEqual(quiet_call(install_codex.main), 0)

        install_qmd.assert_not_called()

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
