#!/usr/bin/env python3
"""Unit tests for memory_bank.py CLI wiring (init-project qmd registration, repo accrual, drift check).

Run: python3 test_memory_bank.py

Stdlib only (unittest + tempfile + mock). qmd is never actually invoked — every
subprocess.run is patched, so these tests assert the *command construction* and
config-vs-qmd drift logic without a live qmd. The pure association primitive
(`append_repo`) is tested in test_collections_yaml.py; here we test that new-work
wires it in and that init-project registers with qmd and drops the manifest.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import collections_yaml
import memory_bank as mb

_MARKER_DIR = tempfile.TemporaryDirectory()
os.environ["TMB_REINDEX_MARKER_DIR"] = _MARKER_DIR.name


def _ok(*_args, **_kwargs):
    """A subprocess.run stand-in that reports success and no output."""
    return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")


class RegisterQmdCollectionTests(unittest.TestCase):
    def test_always_passes_explicit_path_and_name(self):
        # Finding (a): `qmd collection add` with no positional arg silently creates
        # a cwd-named collection, so the path + --name must always be present.
        calls = []
        with mock.patch("subprocess.run", side_effect=lambda cmd, **k: calls.append(cmd) or _ok()):
            mb.register_qmd_collection(Path("/tmp/pdir"), "mb-x", "A summary.")
        self.assertEqual(calls[0], ["qmd", "collection", "add", "/tmp/pdir", "--name", "mb-x"])

    def test_context_add_uses_virtual_path_and_summary(self):
        # The real CLI is `qmd context add <path> "<summary>"` with a virtual
        # collection path — not the wrong `context add <project> <readme-path>`.
        calls = []
        with mock.patch("subprocess.run", side_effect=lambda cmd, **k: calls.append(cmd) or _ok()):
            mb.register_qmd_collection(Path("/tmp/pdir"), "mb-x", "A summary.")
        self.assertEqual(calls[1], ["qmd", "context", "add", "qmd://mb-x/", "A summary."])

    def test_warns_and_stops_on_failure(self):
        # Warn-and-continue: a failing first step short-circuits the second and
        # never raises (a down qmd must not block the markdown/config write).
        def fail(cmd, **k):
            return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="")

        calls = []
        with mock.patch("subprocess.run", side_effect=lambda cmd, **k: calls.append(cmd) or fail(cmd)):
            mb.register_qmd_collection(Path("/tmp/pdir"), "mb-x", "s")  # must not raise
        self.assertEqual(len(calls), 1)  # stopped after the failing collection add


class QmdCollectionNamesTests(unittest.TestCase):
    SAMPLE = (
        "Collections (2):\n\n"
        "mb-agent-skills (qmd://mb-agent-skills/)\n"
        "  Pattern:  **/*.md\n"
        "  Files:    112\n\n"
        "example-knowledge (qmd://example-knowledge/)\n"
        "  Pattern:  **/*.md\n"
    )

    def test_parses_names_from_list_output(self):
        result = subprocess.CompletedProcess(args=[], returncode=0, stdout=self.SAMPLE, stderr="")
        with mock.patch("subprocess.run", return_value=result):
            self.assertEqual(mb.qmd_collection_names(), {"mb-agent-skills", "example-knowledge"})

    def test_returns_none_when_qmd_unavailable(self):
        # None (not empty set) distinguishes "qmd down" from "qmd has zero collections".
        result = subprocess.CompletedProcess(args=[], returncode=127, stdout="", stderr="")
        with mock.patch("subprocess.run", return_value=result):
            self.assertIsNone(mb.qmd_collection_names())


class ReindexTests(unittest.TestCase):
    def test_multiple_collections_share_one_update(self):
        calls = []
        args = argparse.Namespace(collection=["one", "two"], root=None)
        with mock.patch(
            "subprocess.run",
            side_effect=lambda cmd, **kwargs: calls.append(cmd) or _ok(),
        ):
            mb.reindex(args)

        self.assertEqual(
            calls,
            [
                ["qmd", "update"],
                ["qmd", "embed", "-c", "one"],
                ["qmd", "embed", "-c", "two"],
            ],
        )


class NewWorkRepoAccrualTests(unittest.TestCase):
    def _init_bank(self) -> Path:
        root = Path(tempfile.mkdtemp())
        args = argparse.Namespace(
            root=str(root), project="demo", repo=None, description=None, domain=None
        )
        with mock.patch("subprocess.run", side_effect=_ok):
            mb.init_project(args)
        return root

    def _new_work(self, root: Path, repo):
        args = argparse.Namespace(
            root=str(root), project="demo", type="task", title="Do a thing",
            id=None, domain=None, repo=repo, status="open",
        )
        mb.new_work(args)

    def test_explicit_repo_is_accreted(self):
        root = self._init_bank()
        self._new_work(root, "/work/demo-repo")
        data = collections_yaml.parse_collections(root / ".memory-bank" / "collections.yaml")
        self.assertIn("/work/demo-repo", data["mb-demo"]["repos"])

    def test_accrual_is_idempotent(self):
        root = self._init_bank()
        self._new_work(root, "/work/demo-repo")
        self._new_work(root, "/work/demo-repo")
        data = collections_yaml.parse_collections(root / ".memory-bank" / "collections.yaml")
        self.assertEqual(data["mb-demo"]["repos"].count("/work/demo-repo"), 1)

    def test_no_repo_and_no_git_is_a_noop(self):
        root = self._init_bank()
        # No --repo, and current_git_root resolves to "" (no git) -> nothing accreted.
        with mock.patch("memory_bank.current_git_root", return_value=""):
            self._new_work(root, None)
        data = collections_yaml.parse_collections(root / ".memory-bank" / "collections.yaml")
        self.assertEqual(data["mb-demo"]["repos"], [])

    def test_marks_project_dirty_for_deferred_reindex(self):
        root = self._init_bank()
        with mock.patch("memory_bank.mark_collection_dirty") as mark:
            self._new_work(root, "/work/demo-repo")
        mark.assert_called_once_with("mb-demo")


class DoctorDriftTests(unittest.TestCase):
    def _bank_with_one_project(self) -> Path:
        root = Path(tempfile.mkdtemp())
        args = argparse.Namespace(
            root=str(root), project="demo", repo=None, description=None, domain=None
        )
        with mock.patch("subprocess.run", side_effect=_ok):
            mb.init_project(args)
        return root

    def _run_doctor(self, root: Path, registered):
        # qmd --help returns 0 (available); qmd_collection_names patched to `registered`.
        with mock.patch("subprocess.run", side_effect=_ok), \
             mock.patch("memory_bank.qmd_collection_names", return_value=registered):
            captured = []
            with mock.patch("builtins.print", side_effect=lambda *a, **k: captured.append(" ".join(map(str, a)))):
                try:
                    mb.doctor(argparse.Namespace(root=str(root)))
                except SystemExit:
                    pass
            return "\n".join(captured)

    def test_config_not_in_qmd_is_flagged(self):
        root = self._bank_with_one_project()
        out = self._run_doctor(root, registered=set())  # qmd knows nothing
        self.assertIn("not registered with qmd", out)

    def test_in_sync_is_not_flagged(self):
        root = self._bank_with_one_project()
        out = self._run_doctor(root, registered={"mb-demo"})
        self.assertNotIn("not registered with qmd", out)

    def test_other_banks_collection_is_not_orphan_flagged(self):
        # Multi-bank: a qmd collection this bank doesn't know is NOT drift.
        root = self._bank_with_one_project()
        out = self._run_doctor(root, registered={"mb-demo", "mb-other-bank-project"})
        self.assertNotIn("mb-other-bank-project", out)

    def test_qmd_unavailable_skips_drift_check(self):
        root = self._bank_with_one_project()
        out = self._run_doctor(root, registered=None)  # qmd_collection_names -> None
        self.assertNotIn("not registered with qmd", out)


class InitProjectTests(unittest.TestCase):
    def _init(self, **overrides):
        root = Path(tempfile.mkdtemp())
        args = argparse.Namespace(
            root=str(root), project="demo", repo=None, description=None, domain=None
        )
        for k, v in overrides.items():
            setattr(args, k, v)
        with mock.patch("subprocess.run", side_effect=_ok):
            mb.init_project(args)
        return root

    def test_does_not_write_per_project_manifest(self):
        root = self._init()
        self.assertFalse((root / "projects" / "demo" / ".memory-bank" / "collection.yaml").exists())

    def test_threads_description_and_domain_and_repos(self):
        root = self._init(repo=["/a", "/b"], description="My desc", domain="auth")
        data = collections_yaml.parse_collections(root / ".memory-bank" / "collections.yaml")
        block = data["mb-demo"]
        self.assertEqual(block["repos"], ["/a", "/b"])
        self.assertEqual(block["description"], "My desc")
        self.assertEqual(block["domain"], "auth")

    def test_registers_with_qmd(self):
        root = Path(tempfile.mkdtemp())
        args = argparse.Namespace(
            root=str(root), project="demo", repo=None, description="D", domain=None
        )
        calls = []
        with mock.patch("subprocess.run", side_effect=lambda cmd, **k: calls.append(cmd) or _ok()):
            mb.init_project(args)
        cmds = [c for c in calls if c[:2] in (["qmd", "collection"], ["qmd", "context"])]
        self.assertEqual(cmds[0][:3], ["qmd", "collection", "add"])
        self.assertEqual(cmds[1][:3], ["qmd", "context", "add"])

    def test_marks_registered_collection_dirty(self):
        root = Path(tempfile.mkdtemp())
        args = argparse.Namespace(
            root=str(root), project="demo", repo=None, description=None, domain=None
        )
        with mock.patch("subprocess.run", side_effect=_ok), \
             mock.patch("memory_bank.mark_collection_dirty") as mark:
            mb.init_project(args)
        mark.assert_called_once_with("mb-demo")


class MigrateCollectionsManifestTests(unittest.TestCase):
    def _bank_with_manifest(self) -> tuple[Path, Path]:
        """A migrated bank that still carries a stale per-project manifest."""
        root = Path(tempfile.mkdtemp())
        (root / ".memory-bank").mkdir(parents=True)
        # Already on the repos: schema, so the text-migration step is a no-op and
        # only the manifest removal should fire.
        (root / ".memory-bank" / "collections.yaml").write_text(
            "collections:\n  mb-demo:\n    path: x\n    kind: project\n"
            "    project: demo\n    repos: []\n    context: demo\n",
            encoding="utf-8",
        )
        manifest = root / "projects" / "demo" / ".memory-bank" / "collection.yaml"
        manifest.parent.mkdir(parents=True)
        manifest.write_text("collection:\n  name: mb-demo\n  repo: /old\n", encoding="utf-8")
        return root, manifest

    def test_removes_stale_manifest(self):
        root, manifest = self._bank_with_manifest()
        mb.migrate_collections(argparse.Namespace(root=str(root), check=False))
        self.assertFalse(manifest.exists())
        # The now-empty .memory-bank dir is cleaned up too.
        self.assertFalse(manifest.parent.exists())

    def test_check_does_not_remove(self):
        root, manifest = self._bank_with_manifest()
        mb.migrate_collections(argparse.Namespace(root=str(root), check=True))
        self.assertTrue(manifest.exists())

    def test_does_not_touch_root_memory_bank(self):
        root, _ = self._bank_with_manifest()
        mb.migrate_collections(argparse.Namespace(root=str(root), check=False))
        self.assertTrue((root / ".memory-bank" / "collections.yaml").exists())


if __name__ == "__main__":
    unittest.main()
