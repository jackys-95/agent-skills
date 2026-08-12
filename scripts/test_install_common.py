#!/usr/bin/env python3
"""Tests for shared installer helpers."""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
from install_common import (  # noqa: E402
    copy_skill,
    install_canonical_skills,
    install_memory_bank_adapter,
    install_plain_skills,
    install_qmd_skill,
    install_tagged_blocks,
    load_manifest,
    render,
)


def quiet_call(func, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return func(*args, **kwargs)


def dedent(text: str) -> str:
    return textwrap.dedent(text).lstrip("\n")


class TestInstallCommon(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_load_manifest_reads_toml(self) -> None:
        manifest = self.tmp / "wrappers.toml"
        manifest.write_text(
            dedent(
                """\
                canonical_skill = "task-memory-bank"

                [[wrappers]]
                name = "memory-resume"
                """
            ),
            encoding="utf-8",
        )

        data = load_manifest(manifest)

        self.assertEqual(data["canonical_skill"], "task-memory-bank")
        self.assertEqual(data["wrappers"][0]["name"], "memory-resume")

    def test_render_replaces_values_and_ends_with_newline(self) -> None:
        output = render("Hello {{name}}\n{{body}}\n", {"name": "Codex", "body": "Done"})

        self.assertEqual(output, "Hello Codex\nDone\n")

    def test_copy_skill_ignores_generated_files(self) -> None:
        source = self.tmp / "source"
        source.mkdir()
        (source / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
        (source / ".DS_Store").write_text("ignore", encoding="utf-8")
        pycache = source / "__pycache__"
        pycache.mkdir()
        (pycache / "x.pyc").write_bytes(b"ignore")
        target = self.tmp / "target"

        quiet_call(copy_skill, "test", source, target, dry_run=False)

        self.assertTrue((target / "SKILL.md").exists())
        self.assertFalse((target / ".DS_Store").exists())
        self.assertFalse((target / "__pycache__").exists())

    def test_copy_skill_excludes_test_files(self) -> None:
        source = self.tmp / "source"
        scripts = source / "scripts"
        scripts.mkdir(parents=True)
        (source / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
        (scripts / "tool.py").write_text("# runtime\n", encoding="utf-8")
        (scripts / "test_tool.py").write_text("# unit test\n", encoding="utf-8")
        (scripts / "tool_test.py").write_text("# unit test\n", encoding="utf-8")
        tests_dir = source / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_extra.py").write_text("# unit test\n", encoding="utf-8")
        target = self.tmp / "target"

        quiet_call(copy_skill, "test", source, target, dry_run=False)

        # Runtime code ships; developer-only test files do not.
        self.assertTrue((target / "scripts" / "tool.py").exists())
        self.assertFalse((target / "scripts" / "test_tool.py").exists())
        self.assertFalse((target / "scripts" / "tool_test.py").exists())
        self.assertFalse((target / "tests").exists())

    def test_copy_skill_dry_run_does_not_write(self) -> None:
        source = self.tmp / "source"
        source.mkdir()
        (source / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
        target = self.tmp / "target"

        quiet_call(copy_skill, "test", source, target, dry_run=True)

        self.assertFalse(target.exists())

    def test_install_canonical_and_plain_skills(self) -> None:
        repo = self.tmp / "repo"
        canonical = repo / "skills" / "task-memory-bank"
        plain = repo / "skills" / "query-kb"
        canonical.mkdir(parents=True)
        plain.mkdir(parents=True)
        (canonical / "SKILL.md").write_text("# TMB\n", encoding="utf-8")
        (plain / "SKILL.md").write_text("# Query\n", encoding="utf-8")
        target = self.tmp / "target"
        manifest = {
            "canonical_skill": "task-memory-bank",
            "canonical_skill_source": "skills/task-memory-bank",
            "skills": [{"name": "query-kb", "source": "skills/query-kb"}],
            "wrappers": [
                {
                    "name": "memory-resume",
                    "description": "Resume memory.",
                    "argument_hint": "[project]",
                    "workflow": "memory.resume",
                    "body": "Resume now.",
                }
            ],
        }
        template = dedent(
            """\
            ---
            name: {{name}}
            description: {{description}}
            argument-hint: "{{argument_hint}}"
            ---

            Read {{canonical_skill_path}} for {{workflow}}.
            {{body}}
            """
        )

        quiet_call(install_canonical_skills, repo, manifest, template, target, dry_run=False)
        quiet_call(install_plain_skills, repo, manifest, target, dry_run=False)

        wrapper = (target / "memory-resume" / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue((target / "task-memory-bank" / "SKILL.md").exists())
        self.assertTrue((target / "query-kb" / "SKILL.md").exists())
        self.assertIn("Read task-memory-bank/SKILL.md", wrapper)
        self.assertIn("Resume now.", wrapper)

    def test_install_memory_bank_adapter_composes_public_entrypoint(self) -> None:
        repo = self.tmp / "repo"
        canonical = repo / "skills" / "task-memory-bank" / "scripts" / "memory_bank.py"
        facade = repo / "adapters" / "core" / "memory_bank_adapter.py"
        state = repo / "adapters" / "core" / "reindex_state.py"
        canonical.parent.mkdir(parents=True)
        facade.parent.mkdir(parents=True)
        canonical.write_text("# canonical\n", encoding="utf-8")
        facade.write_text("# facade\n", encoding="utf-8")
        state.write_text("# state\n", encoding="utf-8")
        target = self.tmp / "custom-skills"

        quiet_call(
            install_memory_bank_adapter,
            repo,
            target,
            dry_run=False,
        )

        scripts = target / "task-memory-bank" / "scripts"
        self.assertEqual(
            (scripts / "_memory_bank.py").read_text(encoding="utf-8"),
            "# canonical\n",
        )
        self.assertEqual(
            (scripts / "memory_bank.py").read_text(encoding="utf-8"),
            "# facade\n",
        )
        self.assertEqual(
            (scripts / "reindex_state.py").read_text(encoding="utf-8"),
            "# state\n",
        )

    def test_install_memory_bank_adapter_dry_run_writes_nothing(self) -> None:
        target = self.tmp / "custom-skills"

        quiet_call(
            install_memory_bank_adapter,
            self.tmp / "repo",
            target,
            dry_run=True,
        )

        self.assertFalse(target.exists())

    def test_install_tagged_blocks_creates_replaces_and_preserves_content(self) -> None:
        source = self.tmp / "source.md"
        target = self.tmp / "target.md"
        source.write_text(
            dedent(
                """\
                <!-- block-a -->
                New A
                <!-- block-a -->

                <!-- block-b -->
                New B
                <!-- block-b -->
                """
            ),
            encoding="utf-8",
        )
        target.write_text(
            dedent(
                """\
                # Preamble

                <!-- block-a -->
                Old A
                <!-- block-a -->

                # Custom
                """
            ),
            encoding="utf-8",
        )

        quiet_call(install_tagged_blocks, source, target, dry_run=False, label="TEST")
        first = target.read_text(encoding="utf-8")
        quiet_call(install_tagged_blocks, source, target, dry_run=False, label="TEST")
        second = target.read_text(encoding="utf-8")

        self.assertEqual(first, second)
        self.assertIn("# Preamble", first)
        self.assertIn("# Custom", first)
        self.assertIn("New A", first)
        self.assertIn("New B", first)
        self.assertNotIn("Old A", first)

    def test_install_tagged_blocks_dry_run_does_not_write(self) -> None:
        source = self.tmp / "source.md"
        target = self.tmp / "target.md"
        source.write_text("<!-- block -->\nNew\n<!-- block -->\n", encoding="utf-8")

        quiet_call(install_tagged_blocks, source, target, dry_run=True, label="TEST")

        self.assertFalse(target.exists())

    def test_install_tagged_blocks_can_filter_source_tags(self) -> None:
        source = self.tmp / "source.md"
        target = self.tmp / "target.md"
        source.write_text(
            "<!-- keep -->\nKeep\n<!-- keep -->\n\n"
            "<!-- skip -->\nSkip\n<!-- skip -->\n",
            encoding="utf-8",
        )

        quiet_call(
            install_tagged_blocks,
            source,
            target,
            dry_run=False,
            label="TEST",
            tags={"keep"},
        )

        text = target.read_text(encoding="utf-8")
        self.assertIn("Keep", text)
        self.assertNotIn("Skip", text)

    def test_install_qmd_skill_dry_run_does_not_run_commands(self) -> None:
        with mock.patch("install_common.shutil.which", return_value="/usr/bin/qmd"):
            with mock.patch("install_common.subprocess.run") as run:
                quiet_call(install_qmd_skill, dry_run=True)

        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
