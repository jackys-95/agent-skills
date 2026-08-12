#!/usr/bin/env python3
"""Lifecycle tests for the Codex CLI + Zed hooks."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

ZED_DIR = Path(__file__).resolve().parents[2]
HOOKS_DIR = ZED_DIR / "hooks"
CORE_DIR = ZED_DIR.parent / "core"
sys.path[:0] = [str(HOOKS_DIR), str(CORE_DIR)]

import manifest  # noqa: E402
import post_apply_patch_zed_touch as post_hook  # noqa: E402
import pre_apply_patch_zed_snapshot as pre_hook  # noqa: E402
import reset_codex_zed_turn as reset_hook  # noqa: E402
import revert_codex_zed_snapshot as revert_hook  # noqa: E402
import snapshot_revert  # noqa: E402
import stop_flush_codex_zed_diffs as stop_hook  # noqa: E402


NAMESPACE = "codex_zed"


class TestCodexHooks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(os.path.realpath(self.tmp.name))
        self.session_id = f"codex-hook-{uuid.uuid4().hex}"
        self.paths = []

    def tearDown(self):
        for path in self.paths:
            try:
                os.remove(snapshot_revert.pointer_path(NAMESPACE, str(path)))
            except OSError:
                pass
        try:
            os.remove(snapshot_revert.manifest_path(NAMESPACE, self.session_id))
        except OSError:
            pass
        shutil.rmtree(
            snapshot_revert.snapshot_dir(NAMESPACE, self.session_id),
            ignore_errors=True,
        )
        self.tmp.cleanup()

    def track(self, *paths):
        self.paths.extend(paths)
        return paths

    def run_hook(self, module, event, enabled=True):
        stdout = io.StringIO()
        stderr = io.StringIO()
        env = {"CODEX_ZED_HOOK": "1"} if enabled else {}
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(event))):
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(
                    stderr
                ):
                    result = module.main()
        return result, stdout.getvalue(), stderr.getvalue()

    def patch_event(self, command):
        return {
            "session_id": self.session_id,
            "cwd": str(self.root),
            "tool_name": "apply_patch",
            "tool_input": {"command": command},
        }

    def test_guarded_hooks_are_silent_noops(self):
        event = self.patch_event(
            "*** Begin Patch\n*** Add File: x.txt\n+x\n*** End Patch\n"
        )
        for module in (reset_hook, pre_hook, post_hook, stop_hook):
            _, stdout, stderr = self.run_hook(module, event, enabled=False)
            self.assertEqual(stdout, "")
            self.assertEqual(stderr, "")

    def test_child_prompt_does_not_clear_parent_manifest(self):
        path = self.root / "existing.txt"
        path.write_text("original\n", encoding="utf-8")
        self.track(path)
        manifest.seed_if_new(NAMESPACE, self.session_id, str(path))
        manifest_path = snapshot_revert.manifest_path(NAMESPACE, self.session_id)

        self.run_hook(
            reset_hook,
            {"session_id": self.session_id, "agent_id": "child-agent"},
        )
        self.assertTrue(os.path.exists(manifest_path))

        self.run_hook(reset_hook, {"session_id": self.session_id})
        self.assertFalse(os.path.exists(manifest_path))

    def test_multi_file_move_delete_diff_and_revert(self):
        existing, deleted, move_old = self.track(
            self.root / "existing.txt",
            self.root / "delete.txt",
            self.root / "move.txt",
        )
        new = self.root / "new file.txt"
        move_new = self.root / "moved" / "move.txt"
        self.track(new, move_new)
        existing.write_text("existing original\n", encoding="utf-8")
        deleted.write_text("delete original\n", encoding="utf-8")
        move_old.write_text("move original\n", encoding="utf-8")

        command = """\
*** Begin Patch
*** Add File: new file.txt
+new
*** Update File: existing.txt
@@
-existing original
+existing changed
*** Delete File: delete.txt
*** Update File: move.txt
*** Move to: moved/move.txt
@@
 move original
*** End Patch
"""
        event = self.patch_event(command)
        _, stdout, _ = self.run_hook(pre_hook, event)

        output = json.loads(stdout)
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("new file.txt", context)
        self.assertIn("moved/move.txt", context)
        data = manifest._load(NAMESPACE, self.session_id)
        self.assertEqual(len(data["entries"]), 5)

        first_bases = {
            entry["path"]: entry["base"] for entry in data["entries"].values()
        }
        _, second_stdout, _ = self.run_hook(pre_hook, event)
        self.assertEqual(second_stdout, "")
        self.assertEqual(
            first_bases,
            {
                entry["path"]: entry["base"]
                for entry in manifest._load(NAMESPACE, self.session_id)[
                    "entries"
                ].values()
            },
        )

        existing.write_text("existing changed\n", encoding="utf-8")
        new.write_text("new\n", encoding="utf-8")
        deleted.unlink()
        move_new.parent.mkdir()
        move_old.rename(move_new)
        _, post_stdout, _ = self.run_hook(post_hook, event)
        self.assertEqual(post_stdout, "")

        with mock.patch.object(stop_hook, "resolve_zed", return_value="/fake/zed"):
            with mock.patch.object(stop_hook.subprocess, "Popen") as popen:
                _, stop_stdout, _ = self.run_hook(
                    stop_hook, {"session_id": self.session_id}
                )

        self.assertEqual(stop_stdout, "")
        cmd = popen.call_args.args[0]
        pairs = [tuple(cmd[index + 1 : index + 3]) for index in range(2, len(cmd), 3)]
        self.assertEqual(cmd[:2], ["/fake/zed", "-a"])
        self.assertIn((os.devnull, str(new)), pairs)
        self.assertIn((first_bases[str(deleted)], os.devnull), pairs)
        self.assertIn((first_bases[str(move_old)], os.devnull), pairs)
        self.assertIn((os.devnull, str(move_new)), pairs)
        self.assertFalse(
            os.path.exists(
                snapshot_revert.manifest_path(NAMESPACE, self.session_id)
            )
        )

        for path in (existing, deleted, move_old, new, move_new):
            self.assertTrue(snapshot_revert.revert(NAMESPACE, str(path)))
        self.assertEqual(existing.read_text(encoding="utf-8"), "existing original\n")
        self.assertEqual(deleted.read_text(encoding="utf-8"), "delete original\n")
        self.assertEqual(move_old.read_text(encoding="utf-8"), "move original\n")
        self.assertFalse(new.exists())
        self.assertFalse(move_new.exists())

    def test_added_then_deleted_file_does_not_open_empty_diff(self):
        path = self.root / "transient.txt"
        self.track(path)
        event = self.patch_event(
            "*** Begin Patch\n"
            "*** Add File: transient.txt\n"
            "+temporary\n"
            "*** End Patch\n"
        )
        self.run_hook(pre_hook, event)

        with mock.patch.object(stop_hook, "resolve_zed", return_value="/fake/zed"):
            with mock.patch.object(stop_hook.subprocess, "Popen") as popen:
                self.run_hook(stop_hook, {"session_id": self.session_id})
        popen.assert_not_called()

    def test_failed_update_does_not_open_unchanged_diff(self):
        path = self.root / "unchanged.txt"
        self.track(path)
        path.write_text("original\n", encoding="utf-8")
        event = self.patch_event(
            "*** Begin Patch\n"
            "*** Update File: unchanged.txt\n"
            "@@\n"
            "-missing context\n"
            "+replacement\n"
            "*** End Patch\n"
        )

        # A failed apply_patch emits PreToolUse but no PostToolUse.
        self.run_hook(pre_hook, event)

        with mock.patch.object(stop_hook, "resolve_zed") as resolve_zed:
            with mock.patch.object(stop_hook.subprocess, "Popen") as popen:
                self.run_hook(stop_hook, {"session_id": self.session_id})

        resolve_zed.assert_not_called()
        popen.assert_not_called()

    def test_stop_missing_zed_returns_structured_warning(self):
        path = self.root / "new.txt"
        self.track(path)
        event = self.patch_event(
            "*** Begin Patch\n*** Add File: new.txt\n+x\n*** End Patch\n"
        )
        self.run_hook(pre_hook, event)
        path.write_text("x\n", encoding="utf-8")

        with mock.patch.object(stop_hook, "resolve_zed", return_value=None):
            _, stdout, _ = self.run_hook(
                stop_hook, {"session_id": self.session_id}
            )
        warning = json.loads(stdout)
        self.assertIn("systemMessage", warning)
        self.assertIn("not found", warning["systemMessage"])

    def test_revert_cli_restores_existing_and_removes_new_file(self):
        existing = self.root / "existing.txt"
        new = self.root / "new.txt"
        self.track(existing, new)
        existing.write_text("original\n", encoding="utf-8")
        manifest.seed_if_new(NAMESPACE, self.session_id, str(existing))
        manifest.seed_if_new(NAMESPACE, self.session_id, str(new))
        existing.write_text("changed\n", encoding="utf-8")
        new.write_text("created\n", encoding="utf-8")

        with mock.patch.object(sys, "argv", ["revert", str(existing)]):
            self.assertEqual(revert_hook.main(), 0)
        with mock.patch.object(sys, "argv", ["revert", str(new)]):
            self.assertEqual(revert_hook.main(), 0)

        self.assertEqual(existing.read_text(encoding="utf-8"), "original\n")
        self.assertFalse(new.exists())

    def test_revert_matches_symlinked_hook_cwd_to_physical_process_cwd(self):
        physical = self.root / "physical"
        logical = self.root / "logical"
        physical.mkdir()
        logical.symlink_to(physical, target_is_directory=True)
        existing = physical / "existing.txt"
        self.track(existing)
        existing.write_text("original\n", encoding="utf-8")

        event = {
            "session_id": self.session_id,
            "cwd": str(logical),
            "tool_name": "apply_patch",
            "tool_input": {
                "command": (
                    "*** Begin Patch\n"
                    "*** Update File: existing.txt\n"
                    "@@\n"
                    "-original\n"
                    "+changed\n"
                    "*** End Patch\n"
                )
            },
        }
        self.run_hook(pre_hook, event)
        existing.write_text("changed\n", encoding="utf-8")

        with mock.patch.object(sys, "argv", ["revert", "existing.txt"]):
            with mock.patch.object(revert_hook.os, "getcwd", return_value=str(physical)):
                self.assertEqual(revert_hook.main(), 0)

        self.assertEqual(existing.read_text(encoding="utf-8"), "original\n")


if __name__ == "__main__":
    unittest.main()
