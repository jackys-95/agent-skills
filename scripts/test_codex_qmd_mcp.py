#!/usr/bin/env python3
"""Tests for Codex qmd MCP installer behavior."""

from __future__ import annotations

import contextlib
import io
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


class TestCodexQmdMcp(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

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

        # Error text: matches a message containing "Malformed"; does not match
        # a generic message such as "Invalid Codex config".
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


if __name__ == "__main__":
    unittest.main()
