#!/usr/bin/env python3
"""Tests for persistent Codex sandbox configuration."""

from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import codex_sandbox_config as sandbox_config  # noqa: E402


def dedent(text: str) -> str:
    return textwrap.dedent(text).lstrip("\n")


class TestCodexSandboxConfig(unittest.TestCase):
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
        self.required = sandbox_config.required_sandbox_paths(
            self.memory,
            [str(self.knowledge)],
            self.environ,
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_config(self, text: str) -> None:
        self.config.parent.mkdir(parents=True, exist_ok=True)
        self.config.write_text(dedent(text), encoding="utf-8")

    def test_required_sandbox_paths_apply_operation_specific_qmd_policy(self) -> None:
        existing_knowledge = sandbox_config.required_sandbox_paths(
            knowledge_paths=[str(self.knowledge)],
            environ=self.environ,
        )
        registration = sandbox_config.required_sandbox_paths(
            knowledge_paths=[str(self.knowledge)],
            environ=self.environ,
            include_qmd_state=True,
        )

        self.assertEqual(
            existing_knowledge,
            (str(self.knowledge.resolve()),),
        )
        self.assertEqual(
            registration,
            (
                str(self.knowledge.resolve()),
                str((self.tmp / "cache" / "qmd").resolve()),
                str((self.tmp / "config" / "qmd").resolve()),
            ),
        )

    def test_required_sandbox_paths_normalize_and_deduplicate_paths(self) -> None:
        paths = sandbox_config.required_sandbox_paths(
            self.memory,
            [str(self.memory / ".." / "memory")],
            self.environ,
        )

        self.assertEqual(
            paths,
            (
                str(self.memory.resolve()),
                str((self.tmp / "cache" / "qmd").resolve()),
                str((self.tmp / "config" / "qmd").resolve()),
            ),
        )

    def test_default_config_path_honors_codex_home(self) -> None:
        environ = {
            "HOME": str(self.tmp / "home"),
            "CODEX_HOME": str(self.tmp / "custom-codex"),
        }

        self.assertEqual(
            sandbox_config.default_config_path(environ),
            (self.tmp / "custom-codex" / "config.toml").resolve(),
        )

    def test_analyze_sandbox_config_distinguishes_ancestor_and_sibling_paths(
        self,
    ) -> None:
        parent = str((self.tmp / "domain").resolve())
        required = str((self.tmp / "domain" / "knowledge").resolve())
        sibling = str((self.tmp / "domain" / "learning").resolve())
        cases = (
            (
                "legacy ancestor",
                {
                    "sandbox_mode": "workspace-write",
                    "sandbox_workspace_write": {
                        "writable_roots": [parent],
                    },
                },
                (),
            ),
            (
                "legacy sibling",
                {
                    "sandbox_mode": "workspace-write",
                    "sandbox_workspace_write": {
                        "writable_roots": [sibling],
                    },
                },
                (required,),
            ),
            (
                "profile ancestor",
                {
                    "default_permissions": "main",
                    "permissions": {
                        "main": {
                            "workspace_roots": {
                                parent: True,
                            },
                        },
                    },
                },
                (),
            ),
            (
                "profile sibling",
                {
                    "default_permissions": "main",
                    "permissions": {
                        "main": {
                            "workspace_roots": {
                                sibling: True,
                            },
                        },
                    },
                },
                (required,),
            ),
        )

        for name, data, expected_missing in cases:
            with self.subTest(name=name):
                state = sandbox_config.analyze_sandbox_config(data, (required,))

                self.assertEqual(state.missing_paths, expected_missing)

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

        changed, backup = sandbox_config.add_sandbox_paths_to_config(
            self.config,
            self.required,
        )
        first = self.config.read_text(encoding="utf-8")
        changed_again, second_backup = sandbox_config.add_sandbox_paths_to_config(
            self.config,
            self.required,
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

    def test_legacy_merge_uses_closing_bracket_indentation(self) -> None:
        self.write_config(
            """\
            sandbox_mode = "workspace-write"
            [sandbox_workspace_write]
            writable_roots = [
                "/existing"
              ]
            """
        )

        sandbox_config.add_sandbox_paths_to_config(self.config, self.required)

        text = self.config.read_text(encoding="utf-8")
        for path in self.required:
            self.assertIn(f'    "{path}",\n', text)
        self.assertIn('    "/existing",\n', text)
        self.assertIn("  ]\n", text)

    def test_single_line_legacy_array_is_extended_in_place(self) -> None:
        self.write_config(
            """\
            sandbox_mode = "workspace-write"
            [sandbox_workspace_write]
            writable_roots = ["/existing"] # keep
            """
        )

        sandbox_config.add_sandbox_paths_to_config(self.config, self.required)

        text = self.config.read_text(encoding="utf-8")
        self.assertIn('writable_roots = ["/existing", ', text)
        self.assertIn("] # keep", text)

    def test_custom_profile_enables_and_adds_paths(self) -> None:
        self.write_config(
            f"""\
            default_permissions = "memory"

            [permissions.memory]
            extends = ":workspace"

            [permissions.memory.workspace_roots]
            "{self.required[0]}" = false # enable me
            """
        )

        sandbox_config.add_sandbox_paths_to_config(self.config, self.required)

        text = self.config.read_text(encoding="utf-8")
        self.assertIn(
            f'"{self.required[0]}" = true # enable me',
            text,
        )
        for path in self.required[1:]:
            self.assertIn(f'"{path}" = true', text)
        _, _, state = sandbox_config.load_sandbox_config_state(
            self.config,
            self.required,
        )
        self.assertEqual(state.model, "profile")
        self.assertEqual(state.missing_paths, ())

    def test_malformed_and_unsupported_configs_are_not_modified(self) -> None:
        cases = (
            ("malformed", "[sandbox_workspace_write\n", "Malformed"),
            (
                "mixed models",
                dedent(
                    """\
                    sandbox_mode = "workspace-write"
                    default_permissions = "memory"
                    [permissions.memory]
                    extends = ":workspace"
                    """
                ),
                "mixes",
            ),
            (
                "built-in profile",
                'default_permissions = ":workspace"\n',
                "Built-in",
            ),
            (
                "read-only sandbox",
                'sandbox_mode = "read-only"\n',
                "workspace-write",
            ),
            (
                "external profile",
                'profile = "memory"\n',
                "profile file",
            ),
        )

        for case_name, config_text, expected_error in cases:
            with self.subTest(name=case_name):
                self.write_config(config_text)
                before = self.config.read_bytes()

                with self.assertRaises(
                    sandbox_config.CodexSandboxConfigError
                ) as raised:
                    sandbox_config.add_sandbox_paths_to_config(
                        self.config,
                        self.required,
                    )

                self.assertIn(expected_error, str(raised.exception))
                self.assertEqual(self.config.read_bytes(), before)
                self.assertEqual(
                    list(self.config.parent.glob("config.toml.bak-*")),
                    [],
                )


if __name__ == "__main__":
    unittest.main()
