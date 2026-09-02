#!/usr/bin/env python3
"""Unit tests for shared tmux pane-turn authority."""

from __future__ import annotations

import json
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ZED_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ZED_DIR / "hooks" / "core"))

import tmux_pane_authority as authority


class PaneAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.tmp.name)
        self.state_patch = mock.patch.object(
            authority,
            "STATE_DIR",
            self.state_dir,
        )
        self.state_patch.start()
        self.tmux = "/tmp/tmux-501/default,1234,0"
        self.pane = "%7"
        self.owner = authority.OwnerIdentity(4321, "owner-start")

    def tearDown(self):
        self.state_patch.stop()
        self.tmp.cleanup()

    def claim(self, *, harness="cc", session="session-a", token="token-a"):
        return authority.claim_pane_turn(
            self.tmux,
            self.pane,
            harness,
            session,
            self.owner,
            token=token,
        )

    def test_paths_are_keyed_by_canonical_server_and_pane(self):
        same_server_other_session = "/tmp/tmux-501/default,1234,9"
        other_server = "/tmp/tmux-501/default,9999,0"

        self.assertEqual(
            authority.pane_claim_path(self.tmux, self.pane),
            authority.pane_claim_path(same_server_other_session, self.pane),
        )
        self.assertNotEqual(
            authority.pane_claim_path(self.tmux, self.pane),
            authority.pane_claim_path(other_server, self.pane),
        )
        self.assertNotEqual(
            authority.pane_claim_path(self.tmux, self.pane),
            authority.pane_claim_path(self.tmux, "%8"),
        )
        self.assertEqual(
            authority.pane_claim_path(self.tmux, self.pane).stem,
            authority.pane_claim_lock_path(self.tmux, self.pane).stem,
        )

    def test_locked_atomic_round_trip_uses_private_files(self):
        claimed = self.claim()

        self.assertEqual(
            authority.read_pane_claim(self.tmux, self.pane),
            claimed,
        )
        claim_mode = stat.S_IMODE(
            authority.pane_claim_path(self.tmux, self.pane).stat().st_mode
        )
        lock_mode = stat.S_IMODE(
            authority.pane_claim_lock_path(self.tmux, self.pane).stat().st_mode
        )
        self.assertEqual(claim_mode, 0o600)
        self.assertEqual(lock_mode, 0o600)

    def test_missing_malformed_and_unsupported_claims_fail_closed(self):
        self.assertIsNone(authority.read_pane_claim(self.tmux, self.pane))
        path = authority.pane_claim_path(self.tmux, self.pane)

        path.write_text("{broken", encoding="utf-8")
        self.assertIsNone(authority.read_pane_claim(self.tmux, self.pane))

        path.write_text(
            json.dumps(
                {
                    "version": 2,
                    "harness": "cc",
                    "session_id": "session-a",
                    "turn_authority_token": "token-a",
                    "owner_pid": 4321,
                    "owner_start": "owner-start",
                }
            ),
            encoding="utf-8",
        )
        self.assertIsNone(authority.read_pane_claim(self.tmux, self.pane))

    def test_new_claim_supersedes_prior_turn_and_cross_harness_claim(self):
        first = self.claim()
        second = authority.claim_pane_turn(
            self.tmux,
            self.pane,
            "codex",
            "session-b",
            self.owner,
            token="token-b",
        )

        with mock.patch.object(
            authority,
            "process_start_time",
            return_value=self.owner.start,
        ):
            self.assertFalse(authority.is_current_pane_claim(first))
            self.assertTrue(authority.is_current_pane_claim(second))

    def test_owner_must_be_live_with_matching_start_time(self):
        claim = self.claim()

        with mock.patch.object(
            authority,
            "process_start_time",
            side_effect=[self.owner.start, "reused-start", None],
        ):
            self.assertTrue(authority.is_current_pane_claim(claim))
            self.assertFalse(authority.is_current_pane_claim(claim))
            self.assertFalse(authority.is_current_pane_claim(claim))

    def test_current_owner_uses_direct_parent_pid_and_start_time(self):
        with mock.patch.object(authority.os, "getppid", return_value=7654):
            with mock.patch.object(
                authority,
                "process_start_time",
                return_value="process-start",
            ):
                self.assertEqual(
                    authority.current_owner_identity(),
                    authority.OwnerIdentity(7654, "process-start"),
                )

    def test_process_start_time_normalizes_ps_output(self):
        result = subprocess.CompletedProcess(
            ["ps"],
            0,
            stdout=" Wed  Sep  2  10:11:12 2026 \n",
            stderr="",
        )
        with mock.patch.object(authority.subprocess, "run", return_value=result):
            self.assertEqual(
                authority.process_start_time(123),
                "Wed Sep 2 10:11:12 2026",
            )

    def test_session_start_revokes_mismatch_and_preserves_exact_identity(self):
        claim = self.claim()
        self.assertFalse(
            authority.revoke_mismatched_pane_claim(
                self.tmux,
                self.pane,
                claim.identity,
            )
        )
        self.assertEqual(
            authority.read_pane_claim(self.tmux, self.pane),
            claim,
        )

        mismatches = (
            authority.PaneIdentity(
                "codex",
                claim.session_id,
                claim.owner_pid,
                claim.owner_start,
            ),
            authority.PaneIdentity(
                claim.harness,
                "new-session",
                claim.owner_pid,
                claim.owner_start,
            ),
            authority.PaneIdentity(
                claim.harness,
                claim.session_id,
                9876,
                claim.owner_start,
            ),
            authority.PaneIdentity(
                claim.harness,
                claim.session_id,
                claim.owner_pid,
                "new-start",
            ),
        )
        for mismatch in mismatches:
            with self.subTest(mismatch=mismatch):
                authority.claim_pane_turn(
                    self.tmux,
                    self.pane,
                    claim.harness,
                    claim.session_id,
                    self.owner,
                    token=claim.turn_authority_token,
                )
                self.assertTrue(
                    authority.revoke_mismatched_pane_claim(
                        self.tmux,
                        self.pane,
                        mismatch,
                    )
                )
                self.assertIsNone(
                    authority.read_pane_claim(self.tmux, self.pane)
                )

    def test_session_end_revokes_owned_claim_only(self):
        claim = self.claim()
        different = authority.PaneIdentity(
            claim.harness,
            "newer-session",
            claim.owner_pid,
            claim.owner_start,
        )
        self.assertFalse(
            authority.revoke_owned_pane_claim(
                self.tmux,
                self.pane,
                different,
            )
        )
        self.assertEqual(
            authority.read_pane_claim(self.tmux, self.pane),
            claim,
        )
        self.assertTrue(
            authority.revoke_owned_pane_claim(
                self.tmux,
                self.pane,
                claim.identity,
            )
        )
        self.assertIsNone(authority.read_pane_claim(self.tmux, self.pane))

    def test_conditional_revocation_cannot_delete_concurrent_restake(self):
        self.claim()
        read_complete = threading.Event()
        allow_revoke = threading.Event()
        original_read = authority._read_claim_unlocked

        def delayed_read(tmux_server, tmux_pane):
            claim = original_read(tmux_server, tmux_pane)
            if threading.current_thread().name == "revoker":
                read_complete.set()
                allow_revoke.wait(timeout=2)
            return claim

        mismatched = authority.PaneIdentity(
            "codex",
            "session-b",
            9876,
            "new-owner",
        )
        with mock.patch.object(
            authority,
            "_read_claim_unlocked",
            side_effect=delayed_read,
        ):
            revoker = threading.Thread(
                name="revoker",
                target=authority.revoke_mismatched_pane_claim,
                args=(self.tmux, self.pane, mismatched),
            )
            restaker = threading.Thread(
                name="restaker",
                target=authority.claim_pane_turn,
                args=(
                    self.tmux,
                    self.pane,
                    "codex",
                    "session-b",
                    authority.OwnerIdentity(9876, "new-owner"),
                    "token-b",
                ),
            )
            revoker.start()
            self.assertTrue(read_complete.wait(timeout=2))
            restaker.start()
            time.sleep(0.05)
            self.assertTrue(restaker.is_alive())
            allow_revoke.set()
            revoker.join(timeout=2)
            restaker.join(timeout=2)

        current = authority.read_pane_claim(self.tmux, self.pane)
        self.assertIsNotNone(current)
        self.assertEqual(current.harness, "codex")
        self.assertEqual(current.turn_authority_token, "token-b")

    def test_expected_claim_serialization_preserves_coordinates_and_claim(self):
        claim = self.claim()

        serialized = authority.serialize_expected_claim(claim)

        self.assertEqual(
            authority.deserialize_expected_claim(serialized),
            claim,
        )
        self.assertIsNone(authority.deserialize_expected_claim("{broken"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
