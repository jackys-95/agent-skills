#!/usr/bin/env python3
"""Tests for Codex reindex-hook installer behavior."""

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


class TtyInput(io.StringIO):
    def isatty(self) -> bool:
        return True


class NoReadTty(TtyInput):
    def readline(self, *args, **kwargs) -> str:
        raise AssertionError("dry-run must not prompt")


class TestCodexReindexInstall(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_noninteractive_install_requires_explicit_hook_choice(self) -> None:
        target = self.tmp / "skills"
        codex_home = self.tmp / "codex"
        argv = [
            "install_codex.py",
            "--skip-qmd",
            "--skip-agents",
            "--target",
            str(target),
            "--codex-home",
            str(codex_home),
        ]

        with mock.patch.object(sys, "argv", argv):
            with mock.patch.object(sys, "stdin", io.StringIO()):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    self.assertEqual(quiet_call(install_codex.main), 2)

        self.assertFalse(target.exists())
        self.assertIn("--enable-hooks or --skip-hooks", stderr.getvalue())

    def test_interactive_hook_consent_accepts_and_installs_hooks(self) -> None:
        target = self.tmp / "skills"
        codex_home = self.tmp / "codex"
        argv = [
            "install_codex.py",
            "--skip-qmd",
            "--skip-agents",
            "--target",
            str(target),
            "--codex-home",
            str(codex_home),
        ]

        with mock.patch.object(sys, "argv", argv):
            with mock.patch.object(sys, "stdin", TtyInput("yes\n")):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(install_codex.main(), 0)

        self.assertTrue((codex_home / "hooks.json").exists())
        self.assertTrue(
            (target / "task-memory-bank" / "scripts" / "_memory_bank.py").exists()
        )
        self.assertIn("host user permissions", output.getvalue())
        self.assertIn("separate review and trust in /hooks", output.getvalue())

    def test_interactive_hook_consent_declines_without_disabling_skills(self) -> None:
        target = self.tmp / "skills"
        codex_home = self.tmp / "codex"
        argv = [
            "install_codex.py",
            "--skip-qmd",
            "--skip-agents",
            "--target",
            str(target),
            "--codex-home",
            str(codex_home),
        ]

        with mock.patch.object(sys, "argv", argv):
            with mock.patch.object(sys, "stdin", TtyInput("\n")):
                self.assertEqual(quiet_call(install_codex.main), 0)

        self.assertTrue((target / "task-memory-bank" / "SKILL.md").exists())
        self.assertFalse((codex_home / "hooks.json").exists())
        scripts = target / "task-memory-bank" / "scripts"
        self.assertFalse((scripts / "_memory_bank.py").exists())

    def test_dry_run_without_hook_choice_never_prompts(self) -> None:
        target = self.tmp / "skills"
        codex_home = self.tmp / "codex"
        argv = [
            "install_codex.py",
            "--dry-run",
            "--target",
            str(target),
            "--codex-home",
            str(codex_home),
        ]

        with mock.patch.object(sys, "argv", argv):
            with mock.patch.object(sys, "stdin", NoReadTty()):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(install_codex.main(), 0)

        self.assertFalse(target.exists())
        self.assertFalse(codex_home.exists())
        self.assertIn("dry-run plans no hook installation", output.getvalue())
        self.assertIn("Configure Codex qmd MCP", output.getvalue())

    def test_dry_run_with_explicit_hook_enablement_plans_hooks(self) -> None:
        target = self.tmp / "skills"
        codex_home = self.tmp / "codex"
        argv = [
            "install_codex.py",
            "--dry-run",
            "--skip-qmd",
            "--skip-agents",
            "--enable-hooks",
            "--target",
            str(target),
            "--codex-home",
            str(codex_home),
        ]

        with mock.patch.object(sys, "argv", argv):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(install_codex.main(), 0)

        self.assertFalse(target.exists())
        self.assertFalse(codex_home.exists())
        self.assertIn("explicitly enabled", output.getvalue())
        self.assertIn("Install Codex reindex runtime", output.getvalue())

    def test_skip_hooks_keeps_canonical_entrypoint_unwrapped(self) -> None:
        target = self.tmp / "skills"
        codex_home = self.tmp / "codex"
        argv = [
            "install_codex.py",
            "--skip-qmd",
            "--skip-agents",
            "--skip-hooks",
            "--target",
            str(target),
            "--codex-home",
            str(codex_home),
        ]

        with mock.patch.object(sys, "argv", argv):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(install_codex.main(), 0)

        scripts = target / "task-memory-bank" / "scripts"
        self.assertIn(
            "Scaffold and maintain",
            (scripts / "memory_bank.py").read_text(encoding="utf-8"),
        )
        self.assertFalse((scripts / "_memory_bank.py").exists())
        self.assertFalse((scripts / "reindex_state.py").exists())
        self.assertFalse((codex_home / "hooks.json").exists())
        self.assertIn("installation: explicitly skipped", output.getvalue())
        self.assertNotIn("disabled", output.getvalue())

    def test_skip_hooks_preserves_complete_existing_installation(self) -> None:
        target = self.tmp / "skills"
        codex_home = self.tmp / "codex"
        common = [
            "--skip-qmd",
            "--skip-agents",
            "--target",
            str(target),
            "--codex-home",
            str(codex_home),
        ]

        with mock.patch.object(
            sys,
            "argv",
            ["install_codex.py", "--enable-hooks", *common],
        ):
            self.assertEqual(quiet_call(install_codex.main), 0)
        config = codex_home / "hooks.json"
        original_hooks = config.read_text(encoding="utf-8")

        output = io.StringIO()
        with mock.patch.object(
            sys,
            "argv",
            ["install_codex.py", "--skip-hooks", *common],
        ):
            with contextlib.redirect_stdout(output):
                self.assertEqual(install_codex.main(), 0)

        scripts = target / "task-memory-bank" / "scripts"
        self.assertEqual(config.read_text(encoding="utf-8"), original_hooks)
        self.assertIn(
            "Adapter-owned facade",
            (scripts / "memory_bank.py").read_text(encoding="utf-8"),
        )
        self.assertTrue((scripts / "_memory_bank.py").exists())
        self.assertIn("Preserve existing Codex qmd reindex hooks", output.getvalue())
        self.assertNotIn("Install Codex reindex runtime", output.getvalue())

    def test_interactive_decline_preserves_complete_existing_installation(self) -> None:
        target = self.tmp / "skills"
        codex_home = self.tmp / "codex"
        common = [
            "--skip-qmd",
            "--skip-agents",
            "--target",
            str(target),
            "--codex-home",
            str(codex_home),
        ]
        with mock.patch.object(
            sys,
            "argv",
            ["install_codex.py", "--enable-hooks", *common],
        ):
            self.assertEqual(quiet_call(install_codex.main), 0)
        config = codex_home / "hooks.json"
        original_hooks = config.read_text(encoding="utf-8")

        output = io.StringIO()
        with mock.patch.object(sys, "argv", ["install_codex.py", *common]):
            with mock.patch.object(sys, "stdin", TtyInput("\n")):
                with contextlib.redirect_stdout(output):
                    self.assertEqual(install_codex.main(), 0)

        scripts = target / "task-memory-bank" / "scripts"
        self.assertEqual(config.read_text(encoding="utf-8"), original_hooks)
        self.assertIn(
            "Adapter-owned facade",
            (scripts / "memory_bank.py").read_text(encoding="utf-8"),
        )
        self.assertIn("Declining leaves it unchanged", output.getvalue())
        self.assertIn("installation: declined", output.getvalue())

    def test_skip_hooks_rejects_partial_installation_before_skill_writes(self) -> None:
        target = self.tmp / "skills"
        codex_home = self.tmp / "codex"
        common = [
            "--skip-qmd",
            "--skip-agents",
            "--target",
            str(target),
            "--codex-home",
            str(codex_home),
        ]
        with mock.patch.object(
            sys,
            "argv",
            ["install_codex.py", "--enable-hooks", *common],
        ):
            self.assertEqual(quiet_call(install_codex.main), 0)

        config = codex_home / "hooks.json"
        data = json.loads(config.read_text(encoding="utf-8"))
        del data["hooks"]["SessionEnd"]
        config.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        entrypoint = target / "task-memory-bank" / "scripts" / "memory_bank.py"
        entrypoint.write_text("leave me\n", encoding="utf-8")

        stderr = io.StringIO()
        with mock.patch.object(
            sys,
            "argv",
            ["install_codex.py", "--skip-hooks", *common],
        ):
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(quiet_call(install_codex.main), 2)

        self.assertEqual(entrypoint.read_text(encoding="utf-8"), "leave me\n")
        self.assertIn("installation is partial", stderr.getvalue())
        self.assertIn("--enable-hooks to repair", stderr.getvalue())

        with mock.patch.object(
            sys,
            "argv",
            ["install_codex.py", "--enable-hooks", *common],
        ):
            self.assertEqual(quiet_call(install_codex.main), 0)
        self.assertIs(
            install_codex.inspect_reindex_hook_state(target, codex_home),
            install_codex.ReindexHookState.COMPLETE,
        )

    def test_hook_health_checks_timeout_but_ignores_status_message(self) -> None:
        target = self.tmp / "skills"
        codex_home = self.tmp / "codex"
        argv = [
            "install_codex.py",
            "--skip-qmd",
            "--skip-agents",
            "--enable-hooks",
            "--target",
            str(target),
            "--codex-home",
            str(codex_home),
        ]
        with mock.patch.object(sys, "argv", argv):
            self.assertEqual(quiet_call(install_codex.main), 0)

        config = codex_home / "hooks.json"
        data = json.loads(config.read_text(encoding="utf-8"))
        handler = data["hooks"]["SessionEnd"][0]["hooks"][0]
        handler["statusMessage"] = "User-selected status text"
        config.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        self.assertIs(
            install_codex.inspect_reindex_hook_state(target, codex_home),
            install_codex.ReindexHookState.COMPLETE,
        )

        handler["timeout"] = 30
        config.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        self.assertIs(
            install_codex.inspect_reindex_hook_state(target, codex_home),
            install_codex.ReindexHookState.PARTIAL,
        )

    def test_hook_health_requires_current_runtime(self) -> None:
        target = self.tmp / "skills"
        codex_home = self.tmp / "codex"
        common = [
            "--skip-qmd",
            "--skip-agents",
            "--target",
            str(target),
            "--codex-home",
            str(codex_home),
        ]
        with mock.patch.object(
            sys,
            "argv",
            ["install_codex.py", "--enable-hooks", *common],
        ):
            self.assertEqual(quiet_call(install_codex.main), 0)

        runtime = (
            codex_home / "hooks" / "agent-skills" / "reindex_dirty_collections.py"
        )
        runtime.unlink()
        self.assertIs(
            install_codex.inspect_reindex_hook_state(target, codex_home),
            install_codex.ReindexHookState.PARTIAL,
        )

        with mock.patch.object(
            sys,
            "argv",
            ["install_codex.py", "--enable-hooks", *common],
        ):
            self.assertEqual(quiet_call(install_codex.main), 0)
        self.assertTrue(runtime.is_file())
        self.assertIs(
            install_codex.inspect_reindex_hook_state(target, codex_home),
            install_codex.ReindexHookState.COMPLETE,
        )

    def test_non_string_hook_matcher_is_rejected_as_config_error(self) -> None:
        config = {
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": ["apply_patch"],
                        "hooks": [{"type": "command", "command": "python3 hook.py"}],
                    }
                ]
            }
        }

        # Error-text regex: matches a message containing "matcher"; does not
        # match an unrelated message such as "invalid hook command".
        with self.assertRaisesRegex(install_codex.InstallError, "matcher"):
            list(install_codex._iter_hook_handlers(config))

    def test_conflicting_managed_hook_fails_before_skill_writes(self) -> None:
        target = self.tmp / "skills"
        codex_home = self.tmp / "codex"
        common = [
            "--skip-qmd",
            "--skip-agents",
            "--target",
            str(target),
            "--codex-home",
            str(codex_home),
        ]
        with mock.patch.object(
            sys,
            "argv",
            ["install_codex.py", "--enable-hooks", *common],
        ):
            self.assertEqual(quiet_call(install_codex.main), 0)

        config = codex_home / "hooks.json"
        data = json.loads(config.read_text(encoding="utf-8"))
        handler = data["hooks"]["UserPromptSubmit"][0]["hooks"][0]
        expected_entrypoint = target / "task-memory-bank" / "scripts" / "memory_bank.py"
        handler["command"] = handler["command"].replace(
            str(expected_entrypoint),
            str(self.tmp / "other" / "memory_bank.py"),
        )
        config.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        entrypoint = target / "task-memory-bank" / "scripts" / "memory_bank.py"
        entrypoint.write_text("leave me\n", encoding="utf-8")

        stderr = io.StringIO()
        with mock.patch.object(
            sys,
            "argv",
            ["install_codex.py", "--enable-hooks", *common],
        ):
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(quiet_call(install_codex.main), 2)

        self.assertEqual(entrypoint.read_text(encoding="utf-8"), "leave me\n")
        self.assertIn("managed commands that conflict", stderr.getvalue())

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
                                # Hook matcher: matches only "apply_patch"; does
                                # not match "functions.apply_patch" or
                                # "apply_patch_file".
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
            "--enable-hooks",
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


if __name__ == "__main__":
    unittest.main()
