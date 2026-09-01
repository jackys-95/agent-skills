#!/usr/bin/env python3
"""Characterization tests for the shared Zed/tmux injection runtime."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ZED_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ZED_DIR / "hooks"))
sys.path.insert(0, str(ZED_DIR.parent / "core"))

import tmux_edit_injection as tmux_injection


class WatchCommandTests(unittest.TestCase):
    def test_default_watch_timeout_remains_120_seconds(self):
        self.assertEqual(tmux_injection.WATCH_TIMEOUT, 120)

    def test_darwin_uses_one_shot_fswatch(self):
        self.assertEqual(
            tmux_injection.watch_command("/tmp/example", platform="darwin"),
            ["fswatch", "-1", "/tmp/example"],
        )

    def test_linux_uses_modify_and_close_write_events(self):
        self.assertEqual(
            tmux_injection.watch_command("/tmp/example", platform="linux"),
            [
                "inotifywait",
                "-e",
                "modify",
                "-e",
                "close_write",
                "/tmp/example",
            ],
        )

    def test_unsupported_platform_has_no_watcher(self):
        self.assertIsNone(
            tmux_injection.watch_command("/tmp/example", platform="win32")
        )


class WatcherSupersessionTokenTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.file_path = str(Path(self.tmp.name) / "example.txt")
        Path(self.file_path).write_text("before", encoding="utf-8")
        self.namespace = "test_tmux_injection"
        self.token_path = Path(
            tmux_injection.watcher_supersession_token_path(
                self.namespace, self.file_path
            )
        )

    def tearDown(self):
        self.token_path.unlink(missing_ok=True)
        self.tmp.cleanup()

    def test_rotating_token_supersedes_prior_watcher(self):
        first = tmux_injection.rotate_watcher_supersession_token(
            self.namespace, self.file_path, token="first"
        )
        self.assertTrue(
            tmux_injection.is_current_watcher_supersession_token(
                self.namespace, self.file_path, first
            )
        )

        second = tmux_injection.rotate_watcher_supersession_token(
            self.namespace, self.file_path, token="second"
        )

        self.assertFalse(
            tmux_injection.is_current_watcher_supersession_token(
                self.namespace, self.file_path, first
            )
        )
        self.assertTrue(
            tmux_injection.is_current_watcher_supersession_token(
                self.namespace, self.file_path, second
            )
        )

    def test_missing_token_fails_closed(self):
        self.assertFalse(
            tmux_injection.is_current_watcher_supersession_token(
                self.namespace, self.file_path, "missing"
            )
        )

    def test_cc_namespace_preserves_existing_token_path(self):
        path = tmux_injection.watcher_supersession_token_path(
            "cc", self.file_path
        )

        self.assertTrue(path.startswith("/tmp/cc_gen_"))


class ChangeDetectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "example.txt"
        self.path.write_text("before\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_unchanged_watcher_event_keeps_waiting(self):
        calls = 0

        def watcher_run(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                self.path.write_text("after\n", encoding="utf-8")
            return subprocess.CompletedProcess(args[0], 0)

        with mock.patch.object(
            tmux_injection.subprocess, "run", side_effect=watcher_run
        ):
            change = tmux_injection.wait_for_change(
                str(self.path), platform="darwin"
            )

        self.assertEqual(change, ("before\n", "after\n"))
        self.assertEqual(calls, 2)

    def test_watcher_timeout_returns_no_change(self):
        with mock.patch.object(
            tmux_injection.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(["fswatch"], 120),
        ):
            change = tmux_injection.wait_for_change(
                str(self.path), platform="darwin"
            )

        self.assertIsNone(change)

    def test_deadline_is_absolute_from_watcher_start(self):
        def change_file(*args, **kwargs):
            self.path.write_text("after\n", encoding="utf-8")

        with mock.patch.object(
            tmux_injection.time, "time", side_effect=[10.0, 40.0]
        ), mock.patch.object(
            tmux_injection.subprocess, "run", side_effect=change_file
        ) as run:
            tmux_injection.wait_for_change(
                str(self.path), timeout=120, platform="darwin"
            )

        self.assertEqual(run.call_args.kwargs["timeout"], 90.0)

    def test_unsupported_platform_returns_without_reading_file(self):
        missing = str(Path(self.tmp.name) / "missing.txt")
        self.assertIsNone(
            tmux_injection.wait_for_change(missing, platform="win32")
        )


class MessageAndTransportTests(unittest.TestCase):
    def test_message_bytes_match_existing_injector(self):
        message = tmux_injection.build_message(
            "/workspace/note.txt", "old\n", "new\n"
        )

        self.assertEqual(
            message,
            "[Zed edit] note.txt was saved with changes:\n"
            "--- a/note.txt\n"
            "+++ b/note.txt\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n",
        )

    def test_transport_uses_literal_send_then_enter(self):
        with mock.patch.object(tmux_injection.subprocess, "run") as run:
            tmux_injection.send_message("%7", "saved diff")

        self.assertEqual(
            run.call_args_list,
            [
                mock.call(
                    ["tmux", "send-keys", "-t", "%7", "-l", "saved diff"]
                ),
                mock.call(["tmux", "send-keys", "-t", "%7", "Enter"]),
            ],
        )


class PipelineTests(unittest.TestCase):
    def test_guard_denial_prevents_transport(self):
        with mock.patch.object(
            tmux_injection,
            "wait_for_change",
            return_value=("before\n", "after\n"),
        ), mock.patch.object(tmux_injection, "send_message") as send:
            injected = tmux_injection.watch_and_inject(
                "/workspace/note.txt",
                "%7",
                should_inject=lambda: False,
            )

        self.assertFalse(injected)
        send.assert_not_called()

    def test_current_watcher_reaches_transport(self):
        with mock.patch.object(
            tmux_injection,
            "wait_for_change",
            return_value=("before\n", "after\n"),
        ), mock.patch.object(tmux_injection, "send_message") as send:
            injected = tmux_injection.watch_and_inject(
                "/workspace/note.txt",
                "%7",
                should_inject=lambda: True,
            )

        self.assertTrue(injected)
        send.assert_called_once_with(
            "%7",
            tmux_injection.build_message(
                "/workspace/note.txt", "before\n", "after\n"
            ),
        )


class ExecutableEntryPointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "example.txt")
        Path(self.path).write_text("content", encoding="utf-8")
        self.namespace = "test_tmux_wrapper"
        self.token_path = Path(
            tmux_injection.watcher_supersession_token_path(
                self.namespace, self.path
            )
        )

    def tearDown(self):
        self.token_path.unlink(missing_ok=True)
        self.tmp.cleanup()

    def test_main_builds_supersession_guard_from_cli_arguments(self):
        token = tmux_injection.rotate_watcher_supersession_token(
            self.namespace, self.path, token="current"
        )
        with mock.patch.object(
            tmux_injection, "watch_and_inject"
        ) as watch:
            tmux_injection.main(
                [
                    self.path,
                    "/tmp/base",
                    "%7",
                    self.namespace,
                    token,
                ]
            )

        self.assertEqual(watch.call_args.args, (self.path, "%7"))
        guard = watch.call_args.kwargs["should_inject"]
        self.assertTrue(guard())

        tmux_injection.rotate_watcher_supersession_token(
            self.namespace, self.path, token="newer"
        )
        self.assertFalse(guard())


class WatcherLaunchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.paths = [
            str(Path(self.tmp.name) / "one.txt"),
            str(Path(self.tmp.name) / "two.txt"),
        ]
        for path in self.paths:
            Path(path).write_text("content", encoding="utf-8")
        self.namespace = "test_tmux_launch"
        self.token_paths = [
            Path(
                tmux_injection.watcher_supersession_token_path(
                    self.namespace, path
                )
            )
            for path in self.paths
        ]

    def tearDown(self):
        for path in self.token_paths:
            path.unlink(missing_ok=True)
        self.tmp.cleanup()

    def test_launches_one_child_per_edit_and_preserves_base(self):
        edits = [
            (self.paths[0], "/tmp/base-one"),
            (self.paths[1], "new"),
        ]
        with mock.patch.object(
            tmux_injection.time, "time", side_effect=[100.0, 101.0]
        ), mock.patch.object(tmux_injection.subprocess, "Popen") as popen:
            tmux_injection.launch_watchers(
                edits,
                "%7",
                namespace=self.namespace,
            )

        self.assertEqual(popen.call_count, 2)
        for index, call in enumerate(popen.call_args_list):
            command = call.args[0]
            self.assertEqual(
                command[:2],
                ["python3", str(Path(tmux_injection.__file__).resolve())],
            )
            self.assertEqual(command[2], self.paths[index])
            self.assertEqual(command[3], edits[index][1])
            self.assertEqual(command[4:6], ["%7", self.namespace])
            self.assertEqual(
                command[6], self.token_paths[index].read_text(encoding="utf-8")
            )
            self.assertEqual(call.kwargs["stdout"], subprocess.DEVNULL)
            self.assertEqual(call.kwargs["stderr"], subprocess.DEVNULL)


if __name__ == "__main__":
    unittest.main(verbosity=2)
