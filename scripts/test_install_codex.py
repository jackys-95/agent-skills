#!/usr/bin/env python3
"""Tests for the Codex installer."""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
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


def normalized_prose(text: str) -> str:
    return " ".join(text.replace("\\\n", " ").split())


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

        install_output = io.StringIO()
        with mock.patch.object(sys, "argv", argv):
            with contextlib.redirect_stdout(install_output):
                self.assertEqual(install_codex.main(), 0)

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

        helper_name = "codex_sandbox_access.py"
        init_helper = target / "memory-init-project" / "scripts" / helper_name
        doctor_helper = target / "memory-doctor" / "scripts" / helper_name
        knowledge_helper = target / "knowledge-files" / "scripts" / helper_name
        self.assertTrue(init_helper.exists())
        self.assertTrue(doctor_helper.exists())
        self.assertTrue(knowledge_helper.exists())
        self.assertFalse((target / "memory-resume" / "scripts" / helper_name).exists())
        module_names = ("codex_sandbox_config.py", "knowledge_base_catalog.py")
        for module_name in module_names:
            for skill in (
                "memory-init-project",
                "memory-doctor",
                "knowledge-files",
            ):
                self.assertTrue(
                    (target / skill / "scripts" / module_name).exists()
                )
            self.assertFalse(
                (target / "memory-resume" / "scripts" / module_name).exists()
            )
        installed_helper = subprocess.run(
            [sys.executable, str(init_helper), "--help"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(
            installed_helper.returncode,
            0,
            installed_helper.stderr,
        )

        init_wrapper = (target / "memory-init-project" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        doctor_wrapper = (target / "memory-doctor" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("codex_sandbox_access.py check", init_wrapper)
        self.assertIn("explicit `add-roots`", init_wrapper)
        self.assertIn("codex_sandbox_access.py check", doctor_wrapper)
        reindex_wrapper = (target / "memory-reindex" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("one-shot approval", reindex_wrapper)
        self.assertIn("qmd embed -c <collection>", reindex_wrapper)
        self.assertIn("Never request a bare `qmd embed`", reindex_wrapper)
        self.assertNotIn("Run the shared reindex flow", reindex_wrapper)
        knowledge_skill = (target / "knowledge-files" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Reindex every settled authoring", knowledge_skill)
        self.assertIn("A healthy harness lifecycle", knowledge_skill)
        self.assertEqual(knowledge_skill.count("<!-- codex-knowledge-files -->"), 2)
        self.assertIn("## Codex Write Permissions", knowledge_skill)
        self.assertIn("check --collection <collection>", knowledge_skill)
        self.assertIn("without a permission prompt", knowledge_skill)
        self.assertIn("resolved exact child path", knowledge_skill)
        self.assertIn("codex --add-dir <exact-path>", knowledge_skill)
        self.assertIn(
            "add-roots --collection <collection> "
            "--expected-root <collection> <exact-path-shown-by-check>",
            knowledge_skill,
        )
        self.assertIn("explicit approval", knowledge_skill)
        self.assertIn("new Codex process", knowledge_skill)
        self.assertIn("`/status`", knowledge_skill)
        self.assertIn(
            "plan-new-collection --collection <new-collection> "
            "--expected-root <new-collection> <planned-exact-path> "
            "--contains <knowledge-or-learning> --domain <domain>",
            knowledge_skill,
        )
        self.assertIn("before creating the root", knowledge_skill)
        self.assertIn("absent from both catalogs", knowledge_skill)
        self.assertIn("do not ask a setup question", knowledge_skill)
        self.assertIn("exact session-only restart", knowledge_skill)
        self.assertIn("without inferring or changing names or paths", knowledge_skill)
        self.assertIn(
            "Declining before a session grant leaves the collection root, "
            "qmd catalog, shared registry, and Codex config unchanged",
            knowledge_skill,
        )
        self.assertIn(
            "check --collection <new-collection> "
            "--expected-root <new-collection> <planned-exact-path>",
            knowledge_skill,
        )
        self.assertIn("A changed qmd path is a hard error", knowledge_skill)
        self.assertIn(
            "add-roots --collection <knowledge-collection> "
            "--expected-root <knowledge-collection> <knowledge-path> "
            "--collection <learning-collection> "
            "--expected-root <learning-collection> <learning-path>",
            knowledge_skill,
        )
        self.assertIn("same explicit registry domain", knowledge_skill)
        self.assertIn("without inferring names or paths", knowledge_skill)
        self.assertIn("session-only access", knowledge_skill)
        self.assertIn("actual write", knowledge_skill)
        self.assertIn(
            "check --collection my-product-knowledge",
            knowledge_skill,
        )
        self.assertIn(
            "resolve-knowledge-learning-pair --collection my-product-knowledge",
            knowledge_skill,
        )
        self.assertIn(
            "my-product-knowledge` at "
            "`/Users/example/Documents/MyProduct/knowledge",
            knowledge_skill,
        )
        self.assertIn(
            "my-product-learning` at "
            "`/Users/example/Documents/MyProduct/learning",
            knowledge_skill,
        )
        self.assertIn(
            "Add persistent Codex write access to these two exact collection roots?",
            knowledge_skill,
        )
        self.assertIn(
            "--expected-root my-product-knowledge "
            "/Users/example/Documents/MyProduct/knowledge",
            knowledge_skill,
        )
        self.assertIn(
            "--expected-root my-product-learning "
            "/Users/example/Documents/MyProduct/learning",
            knowledge_skill,
        )
        self.assertIn(
            "never substitute the shared parent "
            "`/Users/example/Documents/MyProduct`",
            knowledge_skill,
        )
        self.assertIn(
            "plan-new-collection --collection my-product-learning "
            "--expected-root my-product-learning "
            "/Users/example/Documents/MyProduct/learning "
            "--contains learning --domain my-product",
            knowledge_skill,
        )
        self.assertIn(
            "check --collection my-product-learning "
            "--expected-root my-product-learning "
            "/Users/example/Documents/MyProduct/learning",
            knowledge_skill,
        )
        self.assertNotIn("--knowledge-root", knowledge_skill)
        self.assertIn("Do not use `$memory-reindex`", knowledge_skill)
        knowledge_prose = normalized_prose(knowledge_skill)
        self.assertIn(
            "one-shot approval for the exact `qmd update` command",
            knowledge_prose,
        )
        self.assertIn(
            "separate one-shot approval for the exact "
            "`qmd embed -c <collection>` command",
            knowledge_prose,
        )
        self.assertIn("The harness invokes both commands", knowledge_prose)
        self.assertIn("verify retrieval through qmd MCP", knowledge_prose)

        agents_text = agents.read_text(encoding="utf-8")
        self.assertIn("<!-- codex-agent-skills -->", agents_text)
        self.assertIn("$memory-resume", agents_text)
        self.assertIn("qmd MCP `query`, `get`, and `multi_get`", agents_text)
        self.assertIn("lexical `qmd search`", agents_text)
        self.assertIn("## Codex Write Permissions", agents_text)
        self.assertIn("do not write until its preflight succeeds", agents_text)
        self.assertNotIn("codex_sandbox_access.py", agents_text)
        self.assertIn("Do not respond", agents_text)
        self.assertIn("broad qmd, Python, or shell command prefixes", agents_text)
        self.assertNotIn("<!-- zed-codex-adapter -->", agents_text)
        self.assertNotIn("<!-- phase-turns -->", agents_text)
        self.assertIn(
            "Memory wrappers automatically check selected bank roots.",
            install_output.getvalue(),
        )
        self.assertIn(
            "installed knowledge-files skill automatically checks selected "
            "knowledge or learning collections",
            install_output.getvalue(),
        )
        self.assertIn(
            "add-roots --collection <name> "
            "--expected-root <name> <approved-path>",
            install_output.getvalue(),
        )
        self.assertNotIn(
            "--skip-agents` left global Codex AGENTS.md guidance unchanged",
            install_output.getvalue(),
        )
        hooks = json.loads((codex_home / "hooks.json").read_text(encoding="utf-8"))
        self.assertEqual(
            set(hooks["hooks"]),
            {"PostToolUse", "UserPromptSubmit", "SessionStart", "SessionEnd"},
        )
        # Session matcher: matches exactly "startup", "resume", or "clear";
        # it does not match "compact" or "startup-extra".
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

        install_output = io.StringIO()
        with mock.patch.object(sys, "argv", argv):
            with contextlib.redirect_stdout(install_output):
                self.assertEqual(install_codex.main(), 0)

        self.assertTrue((target / "task-memory-bank" / "SKILL.md").exists())
        self.assertFalse(agents.exists())
        knowledge_skill = (target / "knowledge-files" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("## Codex Write Permissions", knowledge_skill)
        self.assertIn(
            "check --collection my-product-knowledge",
            knowledge_skill,
        )
        rendered = install_output.getvalue()
        self.assertIn(
            "Memory wrappers automatically check selected bank roots.",
            rendered,
        )
        self.assertIn(
            "--skip-agents` left global Codex AGENTS.md guidance unchanged",
            rendered,
        )
        self.assertIn(
            "skill-local sandbox access preflight was still installed",
            rendered,
        )
        self.assertIn(
            "installed knowledge-files skill automatically checks selected "
            "knowledge or learning collections",
            rendered,
        )
        self.assertNotIn(
            "did not install or update automatic knowledge or learning "
            "permission preflight",
            rendered,
        )

    def test_knowledge_permission_guidance_uses_collection_interface(self) -> None:
        guidance_paths = (
            install_codex.KNOWLEDGE_SKILL_GUIDANCE,
            install_codex.ADAPTER_DIR / "README.md",
            install_codex.REPO_ROOT
            / "docs"
            / "task-memory-bank-adapters"
            / "codex-adapter.md",
        )

        for path in guidance_paths:
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                self.assertIn("check --collection", text)
                self.assertIn("add-roots --collection", text)
                self.assertNotIn("--knowledge-root", text)

    def test_codex_permission_guidance_is_not_in_canonical_knowledge_skill(
        self,
    ) -> None:
        canonical_skill = (
            install_codex.REPO_ROOT / "skills" / "knowledge-files" / "SKILL.md"
        ).read_text(encoding="utf-8")

        self.assertNotIn("## Codex Write Permissions", canonical_skill)
        self.assertNotIn("codex_sandbox_access.py", canonical_skill)

    def test_new_collection_is_preflighted_and_registered_before_content(self) -> None:
        skill = normalized_prose(
            (
                install_codex.REPO_ROOT / "skills" / "knowledge-files" / "SKILL.md"
            ).read_text(encoding="utf-8")
        )

        preflight = skill.index("platform-specific pre-registration permission check")
        registration = skill.index("register it in **both** catalogs")
        first_write = skill.index("Write to the contract")
        self.assertLess(preflight, registration)
        self.assertLess(registration, first_write)
        self.assertIn("before the first content write", skill)

    def test_new_collection_permission_guidance_is_consent_gated(self) -> None:
        guidance_paths = (
            install_codex.KNOWLEDGE_SKILL_GUIDANCE,
            install_codex.ADAPTER_DIR / "README.md",
            install_codex.REPO_ROOT
            / "docs"
            / "task-memory-bank-adapters"
            / "codex-adapter.md",
        )

        for path in guidance_paths:
            with self.subTest(path=path):
                text = normalized_prose(path.read_text(encoding="utf-8"))
                self.assertIn("plan-new-collection", text)
                self.assertIn("--expected-root", text)
                self.assertIn("--contains", text)
                self.assertIn("--domain", text)
                self.assertIn("before creating", text)
                self.assertIn("both catalogs", text)
                self.assertIn("exact session-only", text)
                self.assertIn("Declining before a session grant", text)
                self.assertIn(
                    "check --collection <new-collection> "
                    "--expected-root <new-collection> <planned-exact-path>",
                    text,
                )

    def test_pair_permission_guidance_uses_deterministic_helper_resolution(
        self,
    ) -> None:
        guidance_paths = (
            install_codex.KNOWLEDGE_SKILL_GUIDANCE,
            install_codex.ADAPTER_DIR / "README.md",
            install_codex.REPO_ROOT
            / "docs"
            / "task-memory-bank-adapters"
            / "codex-adapter.md",
        )

        for path in guidance_paths:
            with self.subTest(path=path):
                text = normalized_prose(path.read_text(encoding="utf-8"))
                self.assertIn(
                    "resolve-knowledge-learning-pair --collection",
                    text,
                )
                self.assertIn("same explicit registry domain", text)
                self.assertIn("both collection names and exact paths", text)
                self.assertIn("without inferring names or paths", text)
                self.assertIn(
                    "add-roots --collection <knowledge-collection> "
                    "--expected-root <knowledge-collection> <knowledge-path> "
                    "--collection <learning-collection> "
                    "--expected-root <learning-collection> <learning-path>",
                    text,
                )
                self.assertIn("exact-path-shown-by-check", text)
                self.assertIn("absent or ambiguous", text)
                self.assertIn("session-only", text)
                self.assertIn("actual write", text)

    def test_knowledge_fallback_uses_exact_host_approvals(self) -> None:
        guidance_paths = (
            install_codex.KNOWLEDGE_SKILL_GUIDANCE,
            install_codex.ADAPTER_DIR / "README.md",
            install_codex.REPO_ROOT
            / "docs"
            / "task-memory-bank-adapters"
            / "codex-adapter.md",
        )

        for path in guidance_paths:
            with self.subTest(path=path):
                text = normalized_prose(path.read_text(encoding="utf-8"))
                self.assertIn(
                    "one-shot approval for the exact `qmd update` command "
                    "outside the spawned-command sandbox",
                    text,
                )
                self.assertIn(
                    "separate one-shot approval for the exact "
                    "`qmd embed -c <collection>` command",
                    text,
                )
                self.assertIn("The harness invokes both commands", text)

    def test_existing_collection_session_example_grants_only_collection_root(
        self,
    ) -> None:
        readme = (install_codex.ADAPTER_DIR / "README.md").read_text(
            encoding="utf-8"
        )
        start = readme.index(
            "offer session-only access with scoped launch grants:"
        )
        end = readme.index("Repeat `--add-dir`", start)
        session_example = readme[start:end]

        self.assertIn('codex --add-dir "$COLLECTION_ROOT"', session_example)
        self.assertNotIn("XDG_CACHE_HOME", session_example)
        self.assertNotIn("XDG_CONFIG_HOME", session_example)

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
