#!/usr/bin/env python3
"""Unit tests for resolve_project_cwd: which cwd the flush hooks hand to `zed`."""

import os
import pathlib
import sys
import tempfile
import unittest

HOOKS_CORE = pathlib.Path(__file__).resolve().parents[2] / "hooks" / "core"
sys.path.insert(0, str(HOOKS_CORE))

from _zed_common import resolve_project_cwd  # noqa: E402


class ResolveProjectCwdTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = os.path.realpath(self._tmp.name)
        self.sub = os.path.join(self.project, "pkg", "sub")
        os.makedirs(self.sub)

    def test_prefers_claude_project_dir(self):
        env = {"CLAUDE_PROJECT_DIR": self.project}
        self.assertEqual(
            resolve_project_cwd({"cwd": self.sub}, env=env), self.project
        )

    def test_uses_event_cwd_without_project_dir(self):
        self.assertEqual(resolve_project_cwd({"cwd": self.sub}, env={}), self.sub)

    def test_subdirectory_is_acceptable(self):
        env = {"CLAUDE_PROJECT_DIR": self.sub}
        self.assertEqual(resolve_project_cwd({}, env=env), self.sub)

    def test_home_directory_is_rejected(self):
        home = os.path.expanduser("~")
        orig = os.getcwd()
        try:
            os.chdir(os.sep)
            self.assertIsNone(
                resolve_project_cwd(
                    {"cwd": home}, env={"CLAUDE_PROJECT_DIR": home}
                )
            )
        finally:
            os.chdir(orig)

    def test_filesystem_root_is_rejected(self):
        orig = os.getcwd()
        try:
            os.chdir(os.sep)
            self.assertIsNone(resolve_project_cwd({"cwd": os.sep}, env={}))
        finally:
            os.chdir(orig)

    def test_missing_or_relative_candidates_fall_through(self):
        env = {"CLAUDE_PROJECT_DIR": "relative/dir"}
        missing = os.path.join(self.project, "gone")
        self.assertEqual(
            resolve_project_cwd({"cwd": missing}, env=env), os.getcwd()
        )

    def test_unsafe_project_dir_falls_through_to_event_cwd(self):
        env = {"CLAUDE_PROJECT_DIR": os.path.expanduser("~")}
        self.assertEqual(resolve_project_cwd({"cwd": self.sub}, env=env), self.sub)


if __name__ == "__main__":
    unittest.main()
