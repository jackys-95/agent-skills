#!/usr/bin/env python3
"""Tests for Codex memory-workflow permission configuration."""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import codex_memory_permissions as permissions  # noqa: E402


def dedent(text: str) -> str:
    return textwrap.dedent(text).lstrip("\n")


class TestCodexMemoryPermissions(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.config = self.tmp / "codex" / "config.toml"
        self.memory = self.tmp / "memory"
        self.knowledge = self.tmp / "knowledge"
        self.environ = {
            "HOME": str(self.tmp),
            "XDG_CACHE_HOME": str(self.tmp / "cache"),
            "XDG_CONFIG_HOME": str(self.tmp / "config"),
        }
        self.roots = permissions.required_roots(
            self.memory, [str(self.knowledge)], self.environ
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_config(self, text: str) -> None:
        self.config.parent.mkdir(parents=True, exist_ok=True)
        self.config.write_text(dedent(text), encoding="utf-8")

    def test_required_roots_use_xdg_paths_and_deduplicate(self) -> None:
        roots = permissions.required_roots(
            self.memory,
            [str(self.memory / ".." / "memory")],
            self.environ,
        )

        self.assertEqual(
            roots,
            (
                str(self.memory.resolve()),
                str((self.tmp / "cache" / "qmd").resolve()),
                str((self.tmp / "config" / "qmd").resolve()),
            ),
        )

    def test_default_paths_honor_supplied_home(self) -> None:
        environ = {"HOME": str(self.tmp / "home")}

        roots = permissions.required_roots(self.memory, environ=environ)

        self.assertEqual(
            permissions.default_config_path(environ),
            (self.tmp / "home" / ".codex" / "config.toml").resolve(),
        )
        self.assertIn(
            str((self.tmp / "home" / ".cache" / "qmd").resolve()), roots
        )
        self.assertIn(
            str((self.tmp / "home" / ".config" / "qmd").resolve()), roots
        )

    def test_backfill_creates_legacy_workspace_config(self) -> None:
        changed, backup = permissions.backfill_config(self.config, self.roots)

        self.assertTrue(changed)
        self.assertIsNone(backup)
        text = self.config.read_text(encoding="utf-8")
        self.assertIn('sandbox_mode = "workspace-write"', text)
        self.assertIn("[sandbox_workspace_write]", text)
        for root in self.roots:
            self.assertIn(f'"{root}"', text)
        _, _, state = permissions.load_state(self.config, self.roots)
        self.assertEqual(state.missing_roots, ())

    def test_legacy_merge_preserves_comments_and_is_idempotent(self) -> None:
        existing = str(self.memory.resolve())
        self.write_config(
            f"""\
            # user comment
            model = "custom"
            sandbox_mode = "workspace-write"

            [sandbox_workspace_write] # keep table comment
            network_access = false
            writable_roots = [
              "{existing}" # keep root comment
            ]

            [projects."/repo"]
            trust_level = "trusted"
            """
        )
        before = self.config.read_text(encoding="utf-8")

        changed, backup = permissions.backfill_config(self.config, self.roots)
        first = self.config.read_text(encoding="utf-8")
        changed_again, second_backup = permissions.backfill_config(
            self.config, self.roots
        )

        self.assertTrue(changed)
        self.assertIsNotNone(backup)
        self.assertEqual(backup.read_text(encoding="utf-8"), before)
        self.assertIn("# user comment", first)
        self.assertIn("# keep table comment", first)
        self.assertIn("# keep root comment", first)
        self.assertIn('model = "custom"', first)
        self.assertIn('[projects."/repo"]', first)
        self.assertFalse(changed_again)
        self.assertIsNone(second_backup)
        self.assertEqual(self.config.read_text(encoding="utf-8"), first)

    def test_single_line_legacy_array_is_extended(self) -> None:
        self.write_config(
            """\
            sandbox_mode = "workspace-write"
            [sandbox_workspace_write]
            writable_roots = ["/existing"] # keep
            """
        )

        permissions.backfill_config(self.config, self.roots)

        text = self.config.read_text(encoding="utf-8")
        self.assertIn('writable_roots = ["/existing", ', text)
        self.assertIn("] # keep", text)

    def test_custom_profile_workspace_roots_are_extended(self) -> None:
        self.write_config(
            f"""\
            default_permissions = "memory"

            [permissions.memory]
            extends = ":workspace"

            [permissions.memory.workspace_roots]
            "{self.roots[0]}" = false # enable me
            """
        )

        permissions.backfill_config(self.config, self.roots)

        text = self.config.read_text(encoding="utf-8")
        self.assertIn(f'"{self.roots[0]}" = true # enable me', text)
        for root in self.roots[1:]:
            self.assertIn(f'"{root}" = true', text)
        _, _, state = permissions.load_state(self.config, self.roots)
        self.assertEqual(state.model, "profile")
        self.assertEqual(state.missing_roots, ())

    def test_custom_profile_table_is_created_when_missing(self) -> None:
        self.write_config(
            """\
            default_permissions = "memory"
            [permissions.memory]
            extends = ":workspace"
            """
        )

        permissions.backfill_config(self.config, self.roots)

        text = self.config.read_text(encoding="utf-8")
        self.assertIn('[permissions."memory".workspace_roots]', text)

    def test_check_reports_missing_without_writing(self) -> None:
        self.write_config(
            """\
            sandbox_mode = "workspace-write"
            [sandbox_workspace_write]
            writable_roots = []
            """
        )
        before = self.config.read_bytes()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = permissions.main(
                [
                    "check",
                    "--memory-root",
                    str(self.memory),
                    "--knowledge-root",
                    str(self.knowledge),
                    "--config",
                    str(self.config),
                ]
            )

        self.assertEqual(result, permissions.EXIT_MISSING)
        self.assertIn("Missing writable roots", output.getvalue())
        self.assertEqual(self.config.read_bytes(), before)

    def test_backfill_refuses_malformed_config_without_writing(self) -> None:
        self.write_config("[sandbox_workspace_write\n")
        before = self.config.read_bytes()

        with self.assertRaises(permissions.ConfigError):
            permissions.backfill_config(self.config, self.roots)

        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(list(self.config.parent.glob("*.bak-*")), [])

    def test_backfill_refuses_mixed_models(self) -> None:
        self.write_config(
            """\
            sandbox_mode = "workspace-write"
            default_permissions = "memory"
            [permissions.memory]
            extends = ":workspace"
            """
        )

        with self.assertRaisesRegex(permissions.ConfigError, "mixes"):
            permissions.backfill_config(self.config, self.roots)

    def test_backfill_refuses_builtin_profile(self) -> None:
        self.write_config('default_permissions = ":workspace"\n')

        with self.assertRaisesRegex(permissions.ConfigError, "Built-in"):
            permissions.backfill_config(self.config, self.roots)

    def test_backfill_refuses_non_workspace_legacy_mode(self) -> None:
        self.write_config('sandbox_mode = "read-only"\n')

        with self.assertRaisesRegex(permissions.ConfigError, "workspace-write"):
            permissions.backfill_config(self.config, self.roots)

    def test_backfill_refuses_external_profile_selection(self) -> None:
        self.write_config('profile = "memory"\n')

        with self.assertRaisesRegex(permissions.ConfigError, "profile file"):
            permissions.backfill_config(self.config, self.roots)


if __name__ == "__main__":
    unittest.main()
