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
from unittest import mock

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
        self.registry = self.tmp / "config" / "qmd" / "registry.yaml"
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

    def write_registry(self, text: str) -> None:
        self.registry.parent.mkdir(parents=True, exist_ok=True)
        self.registry.write_text(dedent(text), encoding="utf-8")

    def qmd_show_result(
        self, collection: str, root: Path | None = None, returncode: int = 0
    ) -> mock.Mock:
        resolved = root or self.tmp / collection
        stdout = (
            f"Collection: {collection}\n"
            f"  Path:     {resolved}\n"
            "  Pattern:  **/*.md\n"
        )
        return mock.Mock(
            returncode=returncode,
            stdout=stdout if returncode == 0 else "",
            stderr="" if returncode == 0 else f"Collection not found: {collection}\n",
        )

    def test_normalize_path_rejects_empty_and_whitespace_only_values(self) -> None:
        for value in ("", " ", "\t\n"):
            with self.subTest(value=value):
                with self.assertRaises(permissions.ConfigError) as raised:
                    permissions.normalize_path(value)

                self.assertIn(
                    "must not be empty or whitespace-only",
                    str(raised.exception),
                )

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

    def test_existing_knowledge_roots_exclude_qmd_state(self) -> None:
        roots = permissions.required_roots(
            knowledge_roots=[str(self.knowledge)],
            environ=self.environ,
        )

        self.assertEqual(
            roots,
            (str(self.knowledge.resolve()),),
        )

    def test_collection_registration_roots_include_qmd_state(self) -> None:
        roots = permissions.required_roots(
            knowledge_roots=[str(self.knowledge)],
            environ=self.environ,
            include_qmd_state=True,
        )

        self.assertEqual(
            roots,
            (
                str(self.knowledge.resolve()),
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

    def test_resolve_knowledge_collections_joins_registry_to_qmd_paths(self) -> None:
        self.write_registry(
            """\
            collections:
              demo-knowledge:
                contains: "knowledge" # classification
                domain: 'demo'
              demo-learning:
                contains: learning
            """
        )
        knowledge_root = self.tmp / "Demo Program" / "knowledge"
        learning_root = self.tmp / "Demo" / "learning"

        with mock.patch.object(
            permissions.subprocess,
            "run",
            side_effect=[
                self.qmd_show_result("demo-knowledge", knowledge_root),
                self.qmd_show_result("demo-learning", learning_root),
            ],
        ) as run:
            resolved = permissions.resolve_knowledge_collections(
                ["demo-knowledge", "demo-learning"],
                environ=self.environ,
            )

        self.assertEqual(
            resolved,
            (
                permissions.ResolvedCollection(
                    "demo-knowledge",
                    "knowledge",
                    "demo",
                    str(knowledge_root.resolve()),
                ),
                permissions.ResolvedCollection(
                    "demo-learning",
                    "learning",
                    "default",
                    str(learning_root.resolve()),
                ),
            ),
        )
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [
                ["qmd", "collection", "show", "demo-knowledge"],
                ["qmd", "collection", "show", "demo-learning"],
            ],
        )

    def test_resolve_knowledge_collections_rejects_unknown_registry_entry(self) -> None:
        self.write_registry("collections: {}\n")

        with mock.patch.object(permissions.subprocess, "run") as run:
            # Error-text regex: matches "missing-knowledge is not classified in
            # the registry"; does not match "missing-knowledge is not in qmd".
            with self.assertRaisesRegex(
                permissions.ConfigError,
                "not classified in",
            ):
                permissions.resolve_knowledge_collections(
                    ["missing-knowledge"],
                    environ=self.environ,
                )

        run.assert_not_called()

    def test_resolve_knowledge_collections_rejects_task_classification(self) -> None:
        self.write_registry(
            """\
            collections:
              task-notes:
                contains: tasks
                domain: demo
            """
        )

        with mock.patch.object(permissions.subprocess, "run") as run:
            # Error-text regex: matches "task-notes must be knowledge or
            # learning"; does not match "task-notes contains tasks".
            with self.assertRaisesRegex(
                permissions.ConfigError,
                "must be knowledge or learning",
            ):
                permissions.resolve_knowledge_collections(
                    ["task-notes"],
                    environ=self.environ,
                )

        run.assert_not_called()

    def test_resolve_knowledge_collections_reports_qmd_lookup_failure(self) -> None:
        self.write_registry(
            """\
            collections:
              demo-knowledge:
                contains: knowledge
                domain: demo
            """
        )

        with mock.patch.object(
            permissions.subprocess,
            "run",
            return_value=self.qmd_show_result(
                "demo-knowledge",
                returncode=1,
            ),
        ):
            # Error-text regex: matches "qmd cannot resolve collection
            # 'demo-knowledge'"; it does not match the same error for
            # "demo-learning".
            with self.assertRaisesRegex(
                permissions.ConfigError,
                "qmd cannot resolve collection 'demo-knowledge'",
            ):
                permissions.resolve_knowledge_collections(
                    ["demo-knowledge"],
                    environ=self.environ,
                )

    def test_resolve_knowledge_collections_rejects_missing_qmd_path(self) -> None:
        self.write_registry(
            """\
            collections:
              demo-knowledge:
                contains: knowledge
                domain: demo
            """
        )

        with mock.patch.object(
            permissions.subprocess,
            "run",
            return_value=mock.Mock(
                returncode=0,
                stdout="Collection: demo-knowledge\n",
                stderr="",
            ),
        ):
            # Error-text regex: matches "qmd returned 0 Path fields"; it does
            # not match "qmd returned 1 Path field".
            with self.assertRaisesRegex(
                permissions.ConfigError,
                "returned 0 Path fields",
            ):
                permissions.resolve_knowledge_collections(
                    ["demo-knowledge"],
                    environ=self.environ,
                )

    def test_resolve_knowledge_collections_rejects_whitespace_only_qmd_path(
        self,
    ) -> None:
        self.write_registry(
            """\
            collections:
              demo-knowledge:
                contains: knowledge
                domain: demo
            """
        )

        for path_line in ("  Path:     ", "Path:\t\t"):
            with self.subTest(path_line=path_line):
                with mock.patch.object(
                    permissions.subprocess,
                    "run",
                    return_value=mock.Mock(
                        returncode=0,
                        stdout=f"Collection: demo-knowledge\n{path_line}\n",
                        stderr="",
                    ),
                ):
                    # Error-text regex: matches "qmd returned 0 Path fields";
                    # it does not match "qmd returned a blank Path field".
                    with self.assertRaisesRegex(
                        permissions.ConfigError,
                        "returned 0 Path fields",
                    ):
                        permissions.resolve_knowledge_collections(
                            ["demo-knowledge"],
                            environ=self.environ,
                        )

    def test_resolve_pair_is_stable_and_uses_qmd_owned_paths(self) -> None:
        self.write_registry(
            """\
            collections:
              demo-learning:
                contains: learning
                domain: demo
              unrelated-knowledge:
                contains: knowledge
                domain: other
              demo-knowledge:
                contains: knowledge
                domain: demo
            """
        )
        knowledge_root = self.tmp / "Demo" / "knowledge"
        learning_root = self.tmp / "Demo" / "learning"

        with mock.patch.object(
            permissions.subprocess,
            "run",
            side_effect=[
                self.qmd_show_result("demo-knowledge", knowledge_root),
                self.qmd_show_result("demo-learning", learning_root),
            ],
        ) as run:
            pair = permissions.resolve_knowledge_learning_pair(
                "demo-learning",
                environ=self.environ,
            )

        self.assertEqual(
            pair,
            permissions.CollectionPair(
                domain="demo",
                knowledge=permissions.ResolvedCollection(
                    "demo-knowledge",
                    "knowledge",
                    "demo",
                    str(knowledge_root.resolve()),
                ),
                learning=permissions.ResolvedCollection(
                    "demo-learning",
                    "learning",
                    "demo",
                    str(learning_root.resolve()),
                ),
            ),
        )
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [
                ["qmd", "collection", "show", "demo-knowledge"],
                ["qmd", "collection", "show", "demo-learning"],
            ],
        )

    def test_resolve_pair_requires_an_explicit_domain(self) -> None:
        self.write_registry(
            """\
            collections:
              demo-knowledge:
                contains: knowledge
              demo-learning:
                contains: learning
            """
        )

        with mock.patch.object(permissions.subprocess, "run") as run:
            with self.assertRaises(permissions.ConfigError) as raised:
                permissions.resolve_knowledge_learning_pair(
                    "demo-knowledge",
                    environ=self.environ,
                )

        self.assertIn("does not have an explicit domain", str(raised.exception))
        run.assert_not_called()

    def test_resolve_pair_rejects_an_absent_counterpart(self) -> None:
        self.write_registry(
            """\
            collections:
              demo-knowledge:
                contains: knowledge
                domain: demo
              other-learning:
                contains: learning
                domain: other
            """
        )

        with mock.patch.object(permissions.subprocess, "run") as run:
            with self.assertRaises(permissions.ConfigError) as raised:
                permissions.resolve_knowledge_learning_pair(
                    "demo-knowledge",
                    environ=self.environ,
                )

        self.assertIn(
            "has no learning counterpart in domain 'demo'",
            str(raised.exception),
        )
        run.assert_not_called()

    def test_resolve_pair_rejects_ambiguous_counterparts(self) -> None:
        self.write_registry(
            """\
            collections:
              demo-knowledge:
                contains: knowledge
                domain: demo
              demo-learning-primary:
                contains: learning
                domain: demo
              demo-learning-secondary:
                contains: learning
                domain: demo
            """
        )

        with mock.patch.object(permissions.subprocess, "run") as run:
            with self.assertRaises(permissions.ConfigError) as raised:
                permissions.resolve_knowledge_learning_pair(
                    "demo-knowledge",
                    environ=self.environ,
                )

        message = str(raised.exception)
        self.assertIn("has multiple learning counterparts in domain 'demo'", message)
        self.assertIn("demo-learning-primary", message)
        self.assertIn("demo-learning-secondary", message)
        run.assert_not_called()

    def test_resolve_pair_rejects_a_shared_qmd_root(self) -> None:
        self.write_registry(
            """\
            collections:
              demo-knowledge:
                contains: knowledge
                domain: demo
              demo-learning:
                contains: learning
                domain: demo
            """
        )
        shared_root = self.tmp / "Demo"

        with mock.patch.object(
            permissions.subprocess,
            "run",
            side_effect=[
                self.qmd_show_result("demo-knowledge", shared_root),
                self.qmd_show_result("demo-learning", shared_root),
            ],
        ):
            with self.assertRaises(permissions.ConfigError) as raised:
                permissions.resolve_knowledge_learning_pair(
                    "demo-knowledge",
                    environ=self.environ,
                )

        self.assertIn(
            "must resolve to distinct qmd roots",
            str(raised.exception),
        )

    def test_plan_new_collection_rejects_blank_expected_root_before_qmd_lookup(
        self,
    ) -> None:
        self.write_config(
            """\
            sandbox_mode = "workspace-write"
            [sandbox_workspace_write]
            writable_roots = []
            """
        )
        before = self.config.read_bytes()

        for root in ("", " \t"):
            with self.subTest(root=root):
                stderr = io.StringIO()
                with mock.patch.dict("os.environ", self.environ, clear=True):
                    with mock.patch.object(
                        permissions.subprocess,
                        "run",
                    ) as run:
                        with contextlib.redirect_stderr(stderr):
                            result = permissions.main(
                                [
                                    "plan-new-collection",
                                    "--collection",
                                    "demo-knowledge",
                                    "--expected-root",
                                    "demo-knowledge",
                                    root,
                                    "--contains",
                                    "knowledge",
                                    "--domain",
                                    "demo",
                                    "--config",
                                    str(self.config),
                                ]
                            )

                self.assertEqual(result, permissions.EXIT_UNSUPPORTED)
                self.assertIn(
                    "must not be empty or whitespace-only",
                    stderr.getvalue(),
                )
                run.assert_not_called()
                self.assertEqual(self.config.read_bytes(), before)
                self.assertEqual(
                    list(self.config.parent.glob("config.toml.bak-*")),
                    [],
                )

    def test_plan_new_collection_preflights_before_registration(self) -> None:
        self.write_config(
            """\
            sandbox_mode = "workspace-write"
            [sandbox_workspace_write]
            writable_roots = []
            """
        )
        before = self.config.read_bytes()
        output = io.StringIO()

        with mock.patch.dict("os.environ", self.environ, clear=True):
            with mock.patch.object(
                permissions.subprocess,
                "run",
                return_value=self.qmd_show_result(
                    "demo-knowledge",
                    returncode=1,
                ),
            ) as run:
                with contextlib.redirect_stdout(output):
                    result = permissions.main(
                        [
                            "plan-new-collection",
                            "--collection",
                            "demo-knowledge",
                            "--expected-root",
                            "demo-knowledge",
                            str(self.knowledge),
                            "--contains",
                            "knowledge",
                            "--domain",
                            "demo",
                            "--config",
                            str(self.config),
                        ]
                    )

        rendered = output.getvalue()
        self.assertEqual(result, permissions.EXIT_MISSING)
        self.assertIn("Planned new collection", rendered)
        self.assertIn("Roots required before registration", rendered)
        self.assertIn("Session-only restart", rendered)
        self.assertIn(f"codex --add-dir {self.knowledge.resolve()}", rendered)
        self.assertIn(
            f"--add-dir {(self.tmp / 'cache' / 'qmd').resolve()}",
            rendered,
        )
        self.assertIn(
            f"--add-dir {(self.tmp / 'config' / 'qmd').resolve()}",
            rendered,
        )
        self.assertIn(
            "add-roots --planned-collection demo-knowledge "
            "--contains knowledge --domain demo "
            f"--expected-root demo-knowledge {self.knowledge.resolve()} "
            f"--config {self.config.resolve()}",
            rendered,
        )
        self.assertFalse(self.registry.exists())
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(list(self.config.parent.glob("config.toml.bak-*")), [])
        run.assert_called_once_with(
            ["qmd", "collection", "show", "demo-knowledge"],
            check=False,
            stdout=permissions.subprocess.PIPE,
            stderr=permissions.subprocess.PIPE,
            text=True,
            env=self.environ,
        )

    def test_plan_new_collection_skips_setup_when_registration_roots_are_covered(
        self,
    ) -> None:
        roots = permissions.required_roots(
            knowledge_roots=[str(self.knowledge)],
            environ=self.environ,
            include_qmd_state=True,
        )
        rendered_roots = ",\n".join(f'  "{root}"' for root in roots)
        self.write_config(
            f"""\
            sandbox_mode = "workspace-write"
            [sandbox_workspace_write]
            writable_roots = [
            {rendered_roots}
            ]
            """
        )
        output = io.StringIO()

        with mock.patch.dict("os.environ", self.environ, clear=True):
            with mock.patch.object(
                permissions.subprocess,
                "run",
                return_value=self.qmd_show_result(
                    "demo-knowledge",
                    returncode=1,
                ),
            ):
                with contextlib.redirect_stdout(output):
                    result = permissions.main(
                        [
                            "plan-new-collection",
                            "--collection",
                            "demo-knowledge",
                            "--expected-root",
                            "demo-knowledge",
                            str(self.knowledge),
                            "--contains",
                            "knowledge",
                            "--domain",
                            "demo",
                            "--config",
                            str(self.config),
                        ]
                    )

        self.assertEqual(result, 0)
        self.assertIn(
            "Persistent config covers every pre-registration root",
            output.getvalue(),
        )
        self.assertNotIn("Persistent setup after explicit approval", output.getvalue())

    def test_plan_new_collection_includes_one_existing_counterpart(self) -> None:
        self.write_registry(
            """\
            collections:
              demo-learning:
                contains: learning
                domain: demo
            """
        )
        self.write_config(
            """\
            sandbox_mode = "workspace-write"
            [sandbox_workspace_write]
            writable_roots = []
            """
        )
        learning = self.tmp / "Demo" / "learning"
        output = io.StringIO()

        with mock.patch.dict("os.environ", self.environ, clear=True):
            with mock.patch.object(
                permissions.subprocess,
                "run",
                side_effect=[
                    self.qmd_show_result("demo-knowledge", returncode=1),
                    self.qmd_show_result("demo-learning", learning),
                ],
            ):
                with contextlib.redirect_stdout(output):
                    result = permissions.main(
                        [
                            "plan-new-collection",
                            "--collection",
                            "demo-knowledge",
                            "--expected-root",
                            "demo-knowledge",
                            str(self.knowledge),
                            "--contains",
                            "knowledge",
                            "--domain",
                            "demo",
                            "--config",
                            str(self.config),
                        ]
                    )

        rendered = output.getvalue()
        session_command = rendered.split("Session-only restart:\n  ", 1)[1].splitlines()[
            0
        ]
        self.assertEqual(result, permissions.EXIT_MISSING)
        self.assertIn("Resolved existing counterpart", rendered)
        self.assertIn(
            "add-roots --planned-collection demo-knowledge "
            "--contains knowledge --domain demo "
            f"--expected-root demo-knowledge {self.knowledge.resolve()} "
            "--collection demo-learning "
            f"--expected-root demo-learning {learning.resolve()} "
            f"--config {self.config.resolve()}",
            rendered,
        )
        self.assertNotIn(str(learning.resolve()), session_command)

    def test_add_roots_revalidates_planned_collection_and_counterpart(self) -> None:
        self.write_registry(
            """\
            collections:
              demo-learning:
                contains: learning
                domain: demo
            """
        )
        registry_before = self.registry.read_bytes()
        self.write_config(
            """\
            sandbox_mode = "workspace-write"
            [sandbox_workspace_write]
            writable_roots = []
            """
        )
        learning = self.tmp / "Demo" / "learning"
        output = io.StringIO()

        with mock.patch.dict("os.environ", self.environ, clear=True):
            with mock.patch.object(
                permissions.subprocess,
                "run",
                side_effect=[
                    self.qmd_show_result("demo-knowledge", returncode=1),
                    self.qmd_show_result("demo-learning", learning),
                ],
            ):
                with contextlib.redirect_stdout(output):
                    result = permissions.main(
                        [
                            "add-roots",
                            "--planned-collection",
                            "demo-knowledge",
                            "--contains",
                            "knowledge",
                            "--domain",
                            "demo",
                            "--expected-root",
                            "demo-knowledge",
                            str(self.knowledge),
                            "--collection",
                            "demo-learning",
                            "--expected-root",
                            "demo-learning",
                            str(learning),
                            "--config",
                            str(self.config),
                        ]
                    )

        self.assertEqual(result, 0)
        self.assertIn("Validated planned new collection", output.getvalue())
        self.assertIn("Validated existing counterpart", output.getvalue())
        self.assertEqual(self.registry.read_bytes(), registry_before)
        _, _, state = permissions.load_state(
            self.config,
            permissions.required_roots(
                knowledge_roots=[str(self.knowledge), str(learning)],
                environ=self.environ,
                include_qmd_state=True,
            ),
        )
        self.assertEqual(state.missing_roots, ())

    def test_add_roots_rejects_planned_collection_registered_after_approval(
        self,
    ) -> None:
        self.write_config(
            """\
            sandbox_mode = "workspace-write"
            [sandbox_workspace_write]
            writable_roots = []
            """
        )
        before = self.config.read_bytes()
        stderr = io.StringIO()

        with mock.patch.dict("os.environ", self.environ, clear=True):
            with mock.patch.object(
                permissions.subprocess,
                "run",
                return_value=self.qmd_show_result(
                    "demo-knowledge",
                    self.knowledge,
                ),
            ):
                with contextlib.redirect_stderr(stderr):
                    result = permissions.main(
                        [
                            "add-roots",
                            "--planned-collection",
                            "demo-knowledge",
                            "--contains",
                            "knowledge",
                            "--domain",
                            "demo",
                            "--expected-root",
                            "demo-knowledge",
                            str(self.knowledge),
                            "--config",
                            str(self.config),
                        ]
                    )

        self.assertEqual(result, permissions.EXIT_UNSUPPORTED)
        self.assertIn("already registered with qmd", stderr.getvalue())
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(list(self.config.parent.glob("config.toml.bak-*")), [])

    def test_add_roots_creates_legacy_workspace_config(self) -> None:
        changed, backup = permissions.add_roots_to_config(self.config, self.roots)

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

        changed, backup = permissions.add_roots_to_config(self.config, self.roots)
        first = self.config.read_text(encoding="utf-8")
        changed_again, second_backup = permissions.add_roots_to_config(
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

        permissions.add_roots_to_config(self.config, self.roots)

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

        permissions.add_roots_to_config(self.config, self.roots)

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

        permissions.add_roots_to_config(self.config, self.roots)

        text = self.config.read_text(encoding="utf-8")
        self.assertIn('[permissions."memory".workspace_roots]', text)

    def test_ancestor_coverage_is_path_aware_for_legacy_and_profiles(self) -> None:
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
                state = permissions.analyze_config(data, (required,))

                self.assertEqual(state.missing_roots, expected_missing)

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

    def test_check_rejects_blank_direct_roots(self) -> None:
        self.write_config(
            """\
            sandbox_mode = "workspace-write"
            [sandbox_workspace_write]
            writable_roots = []
            """
        )
        before = self.config.read_bytes()

        for option, root in (
            ("--memory-root", ""),
            ("--memory-root", " \t"),
            ("--knowledge-root", ""),
            ("--knowledge-root", "\n"),
        ):
            with self.subTest(option=option, root=root):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    result = permissions.main(
                        [
                            "check",
                            option,
                            root,
                            "--config",
                            str(self.config),
                        ]
                    )

                self.assertEqual(result, permissions.EXIT_UNSUPPORTED)
                self.assertIn(
                    "must not be empty or whitespace-only",
                    stderr.getvalue(),
                )
                self.assertEqual(self.config.read_bytes(), before)

    def test_check_rejects_an_explicitly_blank_config_path(self) -> None:
        for config_path in ("", " \t"):
            with self.subTest(config_path=config_path):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    result = permissions.main(
                        [
                            "check",
                            "--knowledge-root",
                            str(self.knowledge),
                            "--config",
                            config_path,
                        ]
                    )

                self.assertEqual(result, permissions.EXIT_UNSUPPORTED)
                self.assertIn(
                    "must not be empty or whitespace-only",
                    stderr.getvalue(),
                )

    def test_check_accepts_knowledge_root_without_memory_root(self) -> None:
        roots = permissions.required_roots(
            knowledge_roots=[str(self.knowledge)],
            environ=self.environ,
        )
        rendered = ",\n".join(f'  "{root}"' for root in roots)
        self.write_config(
            f"""\
            sandbox_mode = "workspace-write"
            [sandbox_workspace_write]
            writable_roots = [
            {rendered}
            ]
            """
        )

        output = io.StringIO()
        with mock.patch.dict("os.environ", self.environ, clear=True):
            with contextlib.redirect_stdout(output):
                result = permissions.main(
                    [
                        "check",
                        "--knowledge-root",
                        str(self.knowledge),
                        "--config",
                        str(self.config),
                    ]
                )

        self.assertEqual(result, 0)
        rendered = output.getvalue()
        self.assertIn(str(self.knowledge.resolve()), rendered)
        self.assertNotIn(str((self.tmp / "cache" / "qmd").resolve()), rendered)
        self.assertNotIn(str((self.tmp / "config" / "qmd").resolve()), rendered)

    def test_bound_check_accepts_collection_root_without_qmd_state(self) -> None:
        self.write_registry(
            """\
            collections:
              demo-knowledge:
                contains: knowledge
                domain: demo
            """
        )
        roots = permissions.required_roots(
            knowledge_roots=[str(self.knowledge)],
            environ=self.environ,
        )
        rendered = ",\n".join(f'  "{root}"' for root in roots)
        self.write_config(
            f"""\
            sandbox_mode = "workspace-write"
            [sandbox_workspace_write]
            writable_roots = [
            {rendered}
            ]
            """
        )

        output = io.StringIO()
        with mock.patch.dict("os.environ", self.environ, clear=True):
            with mock.patch.object(
                permissions.subprocess,
                "run",
                return_value=self.qmd_show_result(
                    "demo-knowledge",
                    self.knowledge,
                ),
            ):
                with contextlib.redirect_stdout(output):
                    result = permissions.main(
                        [
                            "check",
                            "--collection",
                            "demo-knowledge",
                            "--expected-root",
                            "demo-knowledge",
                            str(self.knowledge),
                            "--config",
                            str(self.config),
                        ]
                    )

        self.assertEqual(result, 0)
        rendered = output.getvalue()
        self.assertIn("demo-knowledge", rendered)
        self.assertIn(str(self.knowledge.resolve()), rendered)
        self.assertNotIn(str((self.tmp / "cache" / "qmd").resolve()), rendered)
        self.assertNotIn(str((self.tmp / "config" / "qmd").resolve()), rendered)

    def test_check_rejects_post_registration_root_drift(self) -> None:
        self.write_registry(
            """\
            collections:
              demo-knowledge:
                contains: knowledge
                domain: demo
            """
        )
        self.write_config("[sandbox_workspace_write\n")
        before = self.config.read_bytes()
        moved = self.tmp / "moved" / "knowledge"
        stderr = io.StringIO()

        with mock.patch.dict("os.environ", self.environ, clear=True):
            with mock.patch.object(
                permissions.subprocess,
                "run",
                return_value=self.qmd_show_result("demo-knowledge", moved),
            ):
                with contextlib.redirect_stderr(stderr):
                    result = permissions.main(
                        [
                            "check",
                            "--collection",
                            "demo-knowledge",
                            "--expected-root",
                            "demo-knowledge",
                            str(self.knowledge),
                            "--config",
                            str(self.config),
                        ]
                    )

        self.assertEqual(result, permissions.EXIT_UNSUPPORTED)
        self.assertIn("now resolves to", stderr.getvalue())
        self.assertIn("fresh approval", stderr.getvalue())
        self.assertEqual(self.config.read_bytes(), before)

    def test_add_roots_accepts_path_bound_collection_without_explicit_knowledge_root(
        self,
    ) -> None:
        self.write_registry(
            """\
            collections:
              demo-knowledge:
                contains: knowledge
                domain: demo
            """
        )
        self.write_config(
            """\
            sandbox_mode = "workspace-write"
            [sandbox_workspace_write]
            writable_roots = []
            """
        )

        output = io.StringIO()
        with mock.patch.dict("os.environ", self.environ, clear=True):
            with mock.patch.object(
                permissions.subprocess,
                "run",
                return_value=self.qmd_show_result(
                    "demo-knowledge",
                    self.knowledge,
                ),
            ) as run:
                with contextlib.redirect_stdout(output):
                    result = permissions.main(
                        [
                            "add-roots",
                            "--collection",
                            "demo-knowledge",
                            "--expected-root",
                            "demo-knowledge",
                            str(self.knowledge),
                            "--config",
                            str(self.config),
                        ]
                    )

        self.assertEqual(result, 0)
        self.assertIn("Added Codex writable roots", output.getvalue())
        run.assert_called_once()
        _, _, state = permissions.load_state(
            self.config,
            permissions.required_roots(
                knowledge_roots=[str(self.knowledge)],
                environ=self.environ,
            ),
        )
        self.assertEqual(
            state.configured_roots,
            (str(self.knowledge.resolve()),),
        )
        self.assertEqual(state.missing_roots, ())

    def test_paired_existing_collection_grant_excludes_qmd_state(self) -> None:
        self.write_registry(
            """\
            collections:
              demo-knowledge:
                contains: knowledge
                domain: demo
              demo-learning:
                contains: learning
                domain: demo
            """
        )
        self.write_config(
            """\
            sandbox_mode = "workspace-write"
            [sandbox_workspace_write]
            writable_roots = []
            """
        )
        knowledge_root = self.tmp / "Demo" / "knowledge"
        learning_root = self.tmp / "Demo" / "learning"

        with mock.patch.dict("os.environ", self.environ, clear=True):
            with mock.patch.object(
                permissions.subprocess,
                "run",
                side_effect=[
                    self.qmd_show_result("demo-knowledge", knowledge_root),
                    self.qmd_show_result("demo-learning", learning_root),
                ],
            ):
                result = permissions.main(
                    [
                        "add-roots",
                        "--collection",
                        "demo-knowledge",
                        "--expected-root",
                        "demo-knowledge",
                        str(knowledge_root),
                        "--collection",
                        "demo-learning",
                        "--expected-root",
                        "demo-learning",
                        str(learning_root),
                        "--config",
                        str(self.config),
                    ]
                )

        _, _, state = permissions.load_state(
            self.config,
            (
                str(knowledge_root.resolve()),
                str(learning_root.resolve()),
            ),
        )
        self.assertEqual(result, 0)
        self.assertEqual(
            state.configured_roots,
            (
                str(knowledge_root.resolve()),
                str(learning_root.resolve()),
            ),
        )
        self.assertEqual(state.missing_roots, ())

    def test_add_roots_requires_expected_root_for_collection(self) -> None:
        self.write_config(
            """\
            sandbox_mode = "workspace-write"
            [sandbox_workspace_write]
            writable_roots = []
            """
        )
        before = self.config.read_bytes()
        stderr = io.StringIO()

        with mock.patch.dict("os.environ", self.environ, clear=True):
            with mock.patch.object(permissions.subprocess, "run") as run:
                with contextlib.redirect_stderr(stderr):
                    result = permissions.main(
                        [
                            "add-roots",
                            "--collection",
                            "demo-knowledge",
                            "--config",
                            str(self.config),
                        ]
                    )

        self.assertEqual(result, permissions.EXIT_UNSUPPORTED)
        self.assertIn(
            "--expected-root COLLECTION PATH",
            stderr.getvalue(),
        )
        run.assert_not_called()
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(list(self.config.parent.glob("config.toml.bak-*")), [])

    def test_add_roots_rejects_changed_collection_root_without_writing(
        self,
    ) -> None:
        self.write_registry(
            """\
            collections:
              demo-knowledge:
                contains: knowledge
                domain: demo
            """
        )
        self.write_config(
            """\
            sandbox_mode = "workspace-write"
            [sandbox_workspace_write]
            writable_roots = []
            """
        )
        approved_root = self.knowledge
        current_root = self.tmp / "moved" / "knowledge"
        before = self.config.read_bytes()
        stderr = io.StringIO()

        with mock.patch.dict("os.environ", self.environ, clear=True):
            with mock.patch.object(
                permissions.subprocess,
                "run",
                return_value=self.qmd_show_result(
                    "demo-knowledge",
                    current_root,
                ),
            ):
                with contextlib.redirect_stderr(stderr):
                    result = permissions.main(
                        [
                            "add-roots",
                            "--collection",
                            "demo-knowledge",
                            "--expected-root",
                            "demo-knowledge",
                            str(approved_root),
                            "--config",
                            str(self.config),
                        ]
                    )

        rendered = stderr.getvalue()
        self.assertEqual(result, permissions.EXIT_UNSUPPORTED)
        self.assertIn("now resolves to", rendered)
        self.assertIn(str(current_root.resolve()), rendered)
        self.assertIn(str(approved_root.resolve()), rendered)
        self.assertIn("fresh approval", rendered)
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(list(self.config.parent.glob("config.toml.bak-*")), [])

    def test_resolve_pair_cli_prints_exact_persistent_arguments(self) -> None:
        self.write_registry(
            """\
            collections:
              demo-learning:
                contains: learning
                domain: demo
              demo-knowledge:
                contains: knowledge
                domain: demo
            """
        )
        knowledge_root = self.tmp / "Demo" / "knowledge"
        learning_root = self.tmp / "Demo" / "learning"
        output = io.StringIO()

        with mock.patch.dict("os.environ", self.environ, clear=True):
            with mock.patch.object(
                permissions.subprocess,
                "run",
                side_effect=[
                    self.qmd_show_result("demo-knowledge", knowledge_root),
                    self.qmd_show_result("demo-learning", learning_root),
                ],
            ):
                with contextlib.redirect_stdout(output):
                    result = permissions.main(
                        [
                            "resolve-knowledge-learning-pair",
                            "--collection",
                            "demo-learning",
                        ]
                    )

        rendered = output.getvalue()
        self.assertEqual(result, 0)
        self.assertIn(
            f"demo-knowledge (knowledge, demo): {knowledge_root.resolve()}",
            rendered,
        )
        self.assertIn(
            f"demo-learning (learning, demo): {learning_root.resolve()}",
            rendered,
        )
        self.assertIn(
            "add-roots --collection demo-knowledge "
            f"--expected-root demo-knowledge {knowledge_root.resolve()} "
            "--collection demo-learning "
            f"--expected-root demo-learning {learning_root.resolve()}",
            rendered,
        )
        self.assertFalse(self.config.exists())

    def test_check_requires_only_options_supported_by_check(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                permissions.main(["check", "--config", str(self.config)])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn(
            "at least one of --memory-root, --knowledge-root, "
            "or --collection is required",
            stderr.getvalue(),
        )
        self.assertNotIn("--planned-collection", stderr.getvalue())

    def test_add_roots_missing_input_mentions_planned_collection(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                permissions.main(["add-roots", "--config", str(self.config)])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn(
            "at least one of --memory-root, --knowledge-root, --collection, "
            "or --planned-collection is required",
            stderr.getvalue(),
        )

    def test_cli_exposes_all_permission_commands(self) -> None:
        help_text = permissions._build_parser().format_help()

        self.assertIn(
            "{check,add-roots,plan-new-collection,resolve-knowledge-learning-pair}",
            help_text,
        )

    def test_add_roots_refuses_malformed_config_without_writing(self) -> None:
        self.write_config("[sandbox_workspace_write\n")
        before = self.config.read_bytes()

        with self.assertRaises(permissions.ConfigError):
            permissions.add_roots_to_config(self.config, self.roots)

        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(list(self.config.parent.glob("*.bak-*")), [])

    def test_add_roots_refuses_mixed_models(self) -> None:
        self.write_config(
            """\
            sandbox_mode = "workspace-write"
            default_permissions = "memory"
            [permissions.memory]
            extends = ":workspace"
            """
        )

        with self.assertRaisesRegex(permissions.ConfigError, "mixes"):
            permissions.add_roots_to_config(self.config, self.roots)

    def test_add_roots_refuses_builtin_profile(self) -> None:
        self.write_config('default_permissions = ":workspace"\n')

        with self.assertRaisesRegex(permissions.ConfigError, "Built-in"):
            permissions.add_roots_to_config(self.config, self.roots)

    def test_add_roots_refuses_non_workspace_legacy_mode(self) -> None:
        self.write_config('sandbox_mode = "read-only"\n')

        with self.assertRaisesRegex(permissions.ConfigError, "workspace-write"):
            permissions.add_roots_to_config(self.config, self.roots)

    def test_add_roots_refuses_external_profile_selection(self) -> None:
        self.write_config('profile = "memory"\n')

        with self.assertRaisesRegex(permissions.ConfigError, "profile file"):
            permissions.add_roots_to_config(self.config, self.roots)


if __name__ == "__main__":
    unittest.main()
