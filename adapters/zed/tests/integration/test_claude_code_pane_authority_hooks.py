#!/usr/bin/env python3
"""Integration tests for Claude Code pane authority and Stop wiring."""

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
HOOKS_CORE_DIR = ZED_DIR / "hooks" / "core"
HOOKS_CLAUDE_CODE_DIR = ZED_DIR / "hooks" / "claude-code"
CORE_DIR = ZED_DIR.parent / "core"
sys.path[:0] = [
    str(HOOKS_CLAUDE_CODE_DIR),
    str(HOOKS_CORE_DIR),
    str(CORE_DIR),
]

import manifest  # noqa: E402
import snapshot_revert  # noqa: E402
import stop_flush_claude_code_zed_diffs as stop_hook  # noqa: E402
import tmux_pane_authority as authority  # noqa: E402
import zed_turn_lifecycle as lifecycle_hook  # noqa: E402


NAMESPACE = "cc_zed"


class TestClaudeCodePaneAuthorityHooks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state_dir = self.root / "authority"
        self.state_dir.mkdir()
        self.state_patch = mock.patch.object(
            authority,
            "STATE_DIR",
            self.state_dir,
        )
        self.state_patch.start()
        self.session_id = f"cc-authority-{uuid.uuid4().hex}"
        self.tmux = "/tmp/tmux-501/default,1234,0"
        self.pane = "%7"
        self.owner = authority.OwnerIdentity(4321, "owner-start")
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
        self.state_patch.stop()
        self.tmp.cleanup()

    def run_hook(self, module, event, *, tmux=True, action=None):
        stdout = io.StringIO()
        stderr = io.StringIO()
        env = {"CC_ZED_HOOK": "1"}
        if tmux:
            env.update({"TMUX": self.tmux, "TMUX_PANE": self.pane})
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(event))):
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(
                    stderr
                ):
                    try:
                        if module is lifecycle_hook:
                            result = module.run("cc", action)
                        else:
                            result = module.main()
                    except SystemExit as exc:
                        result = exc.code
        return result, stdout.getvalue(), stderr.getvalue()

    def seed_edit(self):
        path = self.root / f"edited-{len(self.paths)}.txt"
        path.write_text("before\n", encoding="utf-8")
        self.paths.append(path)
        manifest.seed_if_new(NAMESPACE, self.session_id, str(path))
        path.write_text("after\n", encoding="utf-8")
        return path

    def test_prompt_clears_manifest_and_restakes_cc_claim(self):
        path = self.seed_edit()
        manifest_path = snapshot_revert.manifest_path(
            NAMESPACE,
            self.session_id,
        )
        self.assertTrue(os.path.exists(manifest_path))

        with mock.patch.object(
            authority,
            "current_owner_identity",
            return_value=self.owner,
        ):
            self.run_hook(
                lifecycle_hook,
                {"session_id": self.session_id},
                action="begin",
            )

        self.assertFalse(os.path.exists(manifest_path))
        claim = authority.read_pane_claim(self.tmux, self.pane)
        self.assertIsNotNone(claim)
        self.assertEqual(claim.harness, "cc")
        self.assertEqual(claim.session_id, self.session_id)
        self.assertEqual(claim.identity.owner_pid, self.owner.pid)
        self.assertEqual(path.read_text(encoding="utf-8"), "after\n")

    def test_session_start_and_end_use_distinct_revocation_rules(self):
        claim = authority.claim_pane_turn(
            self.tmux,
            self.pane,
            "cc",
            self.session_id,
            self.owner,
            token="token-a",
        )
        with mock.patch.object(
            authority,
            "current_owner_identity",
            return_value=self.owner,
        ):
            self.run_hook(
                lifecycle_hook,
                {
                    "hook_event_name": "SessionStart",
                    "session_id": self.session_id,
                },
                action="reconcile",
            )
            self.assertEqual(
                authority.read_pane_claim(self.tmux, self.pane),
                claim,
            )

            self.run_hook(
                lifecycle_hook,
                {
                    "hook_event_name": "SessionEnd",
                    "session_id": "different-session",
                },
                action="reconcile",
            )
            self.assertEqual(
                authority.read_pane_claim(self.tmux, self.pane),
                claim,
            )

            self.run_hook(
                lifecycle_hook,
                {
                    "hook_event_name": "SessionEnd",
                    "session_id": self.session_id,
                },
                action="reconcile",
            )
            self.assertIsNone(
                authority.read_pane_claim(self.tmux, self.pane)
            )

    def test_stop_launches_watchers_only_for_current_matching_claim(self):
        self.seed_edit()
        claim = authority.claim_pane_turn(
            self.tmux,
            self.pane,
            "cc",
            self.session_id,
            self.owner,
            token="token-a",
        )
        with mock.patch.object(
            authority,
            "current_owner_identity",
            return_value=self.owner,
        ), mock.patch.object(
            authority,
            "process_start_time",
            return_value=self.owner.start,
        ), mock.patch.object(
            stop_hook,
            "resolve_zed",
            return_value="/fake/zed",
        ), mock.patch.object(
            stop_hook.subprocess,
            "Popen",
        ) as zed_open, mock.patch.object(
            stop_hook,
            "launch_watchers",
        ) as launch:
            self.run_hook(
                stop_hook,
                {"session_id": self.session_id},
            )

        zed_open.assert_called_once()
        launch.assert_called_once()
        self.assertEqual(launch.call_args.args[1], self.pane)
        self.assertEqual(
            launch.call_args.kwargs["expected_claim"],
            claim,
        )

    def test_denied_stop_still_opens_zed_diff(self):
        self.seed_edit()
        with mock.patch.object(
            authority,
            "current_owner_identity",
            return_value=self.owner,
        ), mock.patch.object(
            stop_hook,
            "resolve_zed",
            return_value="/fake/zed",
        ), mock.patch.object(
            stop_hook.subprocess,
            "Popen",
        ) as zed_open, mock.patch.object(
            stop_hook,
            "launch_watchers",
        ) as launch:
            self.run_hook(
                stop_hook,
                {"session_id": self.session_id},
            )

        zed_open.assert_called_once()
        launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
