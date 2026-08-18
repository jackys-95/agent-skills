#!/usr/bin/env python3
"""Tests for the Codex installer."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import tomllib
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
        reindex_wrapper = (target / "memory-reindex" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("one-shot approval", reindex_wrapper)
        self.assertIn("qmd embed -c <collection>", reindex_wrapper)
        self.assertIn("Never request a bare `qmd embed`", reindex_wrapper)
        self.assertNotIn("Run the shared reindex flow", reindex_wrapper)

        agents_text = agents.read_text(encoding="utf-8")
        self.assertIn("<!-- codex-agent-skills -->", agents_text)
        self.assertIn("$memory-resume", agents_text)
        self.assertIn("qmd MCP `query`, `get`, and `multi_get`", agents_text)
        self.assertIn("lexical `qmd search`", agents_text)
        self.assertIn("one-shot approval", agents_text)
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
        scripts = target / "task-memory-bank" / "scripts"
        self.assertTrue((scripts / "_memory_bank.py").exists())
        self.assertIn(
            "Adapter-owned facade",
            (scripts / "memory_bank.py").read_text(encoding="utf-8"),
        )
        self.assertTrue((scripts / "reindex_state.py").exists())
        flush_command = hooks["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
        self.assertIn(str(scripts / "memory_bank.py"), flush_command)

    def test_main_skip_agents_leaves_agents_target_untouched(self) -> None:
        target = self.tmp / "skills"
        agents = self.tmp / "AGENTS.md"
        codex_home = self.tmp / "codex"
        argv = [
            "install_codex.py",
            "--skip-qmd",
            "--skip-hooks",
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
        codex_home.mkdir()
        config = codex_home / "config.toml"
        original = 'model = "keep-me"\n'
        config.write_text(original, encoding="utf-8")
        argv = [
            "install_codex.py",
            "--skip-qmd",
            "--skip-hooks",
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
        self.assertEqual(config.read_text(encoding="utf-8"), original)

    def test_main_configures_qmd_mcp_and_preserves_unrelated_config(self) -> None:
        target = self.tmp / "skills"
        codex_home = self.tmp / "codex"
        codex_home.mkdir()
        config = codex_home / "config.toml"
        original = (
            '# Keep this comment.\n'
            'model = "gpt-example"\n\n'
            "[mcp_servers.docs]\n"
            'url = "https://example.test/mcp"\n\n'
            "[sandbox_workspace_write]\n"
            'writable_roots = ["/tmp/example"]\n'
        )
        config.write_text(original, encoding="utf-8")
        argv = [
            "install_codex.py",
            "--skip-agents",
            "--skip-hooks",
            "--target",
            str(target),
            "--codex-home",
            str(codex_home),
        ]

        with mock.patch.object(sys, "argv", argv):
            with mock.patch.object(install_codex, "install_qmd_skill") as install_qmd:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(install_codex.main(), 0)
                    first = config.read_text(encoding="utf-8")
                    self.assertEqual(install_codex.main(), 0)

        self.assertEqual(config.read_text(encoding="utf-8"), first)
        self.assertTrue(first.startswith(original + "\n"))
        data = tomllib.loads(first)
        self.assertEqual(data["model"], "gpt-example")
        self.assertEqual(
            data["mcp_servers"]["docs"]["url"], "https://example.test/mcp"
        )
        self.assertEqual(data["mcp_servers"]["qmd"]["command"], "qmd")
        self.assertEqual(data["mcp_servers"]["qmd"]["args"], ["mcp"])
        self.assertEqual(install_qmd.call_count, 2)
        self.assertIn("Configure Codex qmd MCP", output.getvalue())
        self.assertIn("Verified Codex qmd MCP config", output.getvalue())
        self.assertIn("use /mcp to verify", output.getvalue())

    def test_existing_compatible_qmd_mcp_config_is_unchanged(self) -> None:
        config = self.tmp / "config.toml"
        original = (
            "[mcp_servers.qmd]\n"
            'command = "/opt/homebrew/bin/qmd"\n'
            'args = ["mcp"]\n'
            'enabled_tools = ["query", "get", "multi_get", "status"]\n'
            "tool_timeout_sec = 120\n"
        )
        config.write_text(original, encoding="utf-8")

        plan = install_codex.prepare_qmd_mcp_config(config)
        quiet_call(install_codex.apply_qmd_mcp_config, plan, False)

        self.assertFalse(plan.changed)
        self.assertEqual(config.read_text(encoding="utf-8"), original)

    def test_existing_streamable_http_qmd_config_is_unchanged(self) -> None:
        config = self.tmp / "config.toml"
        original = (
            "[mcp_servers.qmd]\n"
            'url = "http://localhost:8181/mcp"\n'
            "startup_timeout_sec = 20\n"
        )
        config.write_text(original, encoding="utf-8")

        plan = install_codex.prepare_qmd_mcp_config(config)
        quiet_call(install_codex.apply_qmd_mcp_config, plan, False)

        self.assertFalse(plan.changed)
        self.assertEqual(config.read_text(encoding="utf-8"), original)

    def test_conflicting_qmd_mcp_config_fails_before_install_writes(self) -> None:
        target = self.tmp / "skills"
        codex_home = self.tmp / "codex"
        codex_home.mkdir()
        config = codex_home / "config.toml"
        original = (
            "[mcp_servers.qmd]\n"
            'command = "custom-qmd-wrapper"\n'
            'args = ["serve"]\n'
        )
        config.write_text(original, encoding="utf-8")
        argv = [
            "install_codex.py",
            "--skip-agents",
            "--skip-hooks",
            "--target",
            str(target),
            "--codex-home",
            str(codex_home),
        ]

        with mock.patch.object(sys, "argv", argv):
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(quiet_call(install_codex.main), 2)

        self.assertFalse(target.exists())
        self.assertEqual(config.read_text(encoding="utf-8"), original)
        self.assertIn("already exists with a different command", stderr.getvalue())

    def test_restrictive_qmd_mcp_tool_filters_are_rejected(self) -> None:
        cases = (
            'enabled_tools = ["query", "get"]\n',
            'disabled_tools = ["multi_get"]\n',
        )
        for index, tool_filter in enumerate(cases):
            with self.subTest(tool_filter=tool_filter):
                config = self.tmp / f"config-{index}.toml"
                config.write_text(
                    "[mcp_servers.qmd]\n"
                    'command = "qmd"\n'
                    'args = ["mcp"]\n'
                    + tool_filter,
                    encoding="utf-8",
                )
                with self.assertRaises(install_codex.InstallError):
                    install_codex.prepare_qmd_mcp_config(config)

    def test_malformed_codex_config_is_rejected_without_changes(self) -> None:
        config = self.tmp / "config.toml"
        original = '[mcp_servers.qmd\ncommand = "qmd"\n'
        config.write_text(original, encoding="utf-8")

        with self.assertRaisesRegex(install_codex.InstallError, "Malformed"):
            install_codex.prepare_qmd_mcp_config(config)

        self.assertEqual(config.read_text(encoding="utf-8"), original)

    def test_qmd_mcp_dry_run_does_not_write_config(self) -> None:
        config = self.tmp / "codex" / "config.toml"
        plan = install_codex.prepare_qmd_mcp_config(config)

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            install_codex.apply_qmd_mcp_config(plan, dry_run=True)

        self.assertFalse(config.exists())
        self.assertIn(str(config), output.getvalue())

    def test_qmd_mcp_apply_preserves_config_changed_after_preflight(self) -> None:
        config = self.tmp / "config.toml"
        config.write_text('model = "before"\n', encoding="utf-8")
        plan = install_codex.prepare_qmd_mcp_config(config)
        changed = '# Added concurrently.\nmodel = "after"\n\n'
        config.write_text(changed, encoding="utf-8")

        quiet_call(install_codex.apply_qmd_mcp_config, plan, False)

        updated = config.read_text(encoding="utf-8")
        self.assertTrue(updated.startswith(changed))
        self.assertEqual(tomllib.loads(updated)["model"], "after")
        self.assertEqual(
            tomllib.loads(updated)["mcp_servers"]["qmd"]["args"], ["mcp"]
        )

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

    def test_parser_identifies_skill_and_codex_home_destinations(self) -> None:
        help_text = install_codex.build_parser().format_help()

        self.assertIn("--target SKILLS_DIR", help_text)
        self.assertIn("Directory where Codex skills are installed", help_text)
        self.assertIn("--codex-home CODEX_HOME", help_text)
        self.assertIn("config.toml, hooks.json", help_text)


if __name__ == "__main__":
    unittest.main()
