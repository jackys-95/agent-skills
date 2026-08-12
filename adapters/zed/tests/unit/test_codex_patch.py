#!/usr/bin/env python3
"""Tests for Codex apply_patch path extraction."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[2] / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

from _codex_patch import canonical_path, parse_paths, paths_from_event  # noqa: E402


class TestCodexPatchPaths(unittest.TestCase):
    def test_extracts_all_headers_in_order_and_deduplicates(self):
        cwd = "/tmp/codex-patch-root"
        command = """\
*** Begin Patch
*** Add File: new file.txt
+new
*** Update File: existing.txt
@@
+changed
*** Delete File: delete.txt
*** Update File: move.txt
*** Move to: moved/move.txt
@@
 move
*** Update File: existing.txt
@@
+again
*** End Patch
"""

        self.assertEqual(
            parse_paths(command, cwd),
            [
                canonical_path("new file.txt", cwd),
                canonical_path("existing.txt", cwd),
                canonical_path("delete.txt", cwd),
                canonical_path("move.txt", cwd),
                canonical_path("moved/move.txt", cwd),
            ],
        )

    def test_preserves_quotes_and_unicode_without_shell_unquoting(self):
        cwd = "/tmp/codex-patch-root"
        unicode_name = "na\u00efve-\u6587\u4ef6.txt"
        command = (
            "*** Begin Patch\n"
            "*** Add File: single'quote.txt\n"
            "+one\n"
            '*** Add File: double"quote.txt\n'
            "+two\n"
            f"*** Add File: {unicode_name}\n"
            "+three\n"
            "*** End Patch\n"
        )

        self.assertEqual(
            parse_paths(command, cwd),
            [
                canonical_path("single'quote.txt", cwd),
                canonical_path('double"quote.txt', cwd),
                canonical_path(unicode_name, cwd),
            ],
        )

    def test_preserves_raw_quote_and_tilde_characters(self):
        cwd = "/tmp/codex-patch-root"
        command = (
            "*** Begin Patch\n"
            '*** Update File: "/tmp/quoted path.txt"\n'
            "*** Update File: ~/literal-tilde.txt\n"
            "*** End Patch\n"
        )

        self.assertEqual(
            parse_paths(command, cwd),
            [
                canonical_path('"/tmp/quoted path.txt"', cwd),
                canonical_path("~/literal-tilde.txt", cwd),
            ],
        )

    def test_requires_headers_at_column_zero(self):
        command = (
            "*** Begin Patch\n"
            " *** Update File: context-line.txt\n"
            "\t*** Delete File: indented.txt\n"
            "*** End Patch\n"
        )

        self.assertEqual(parse_paths(command, "/tmp"), [])

    def test_relative_paths_resolve_against_hook_cwd(self):
        with tempfile.TemporaryDirectory() as root:
            cwd = os.path.join(root, "subdir")
            event = {
                "cwd": cwd,
                "tool_input": {
                    "command": (
                        "*** Begin Patch\n"
                        "*** Update File: relative.txt\n"
                        "@@\n"
                        "+line\n"
                        "*** End of File\n"
                        "*** End Patch\n"
                    )
                },
            }

            self.assertEqual(
                paths_from_event(event),
                [canonical_path("relative.txt", cwd)],
            )

    def test_absolute_paths_remain_absolute(self):
        self.assertEqual(
            parse_paths(
                "*** Begin Patch\n*** Add File: /tmp/absolute.txt\n+x\n*** End Patch\n",
                "/ignored",
            ),
            [canonical_path("/tmp/absolute.txt")],
        )

    def test_parent_traversal_is_not_restricted_to_hook_cwd(self):
        cwd = "/tmp/workspace/subdir"
        self.assertEqual(
            parse_paths(
                "*** Begin Patch\n"
                "*** Update File: ../../outside.txt\n"
                "*** End Patch\n",
                cwd,
            ),
            [canonical_path("../../outside.txt", cwd)],
        )

    def test_canonicalizes_symlinked_parent_directory(self):
        with tempfile.TemporaryDirectory() as root:
            physical_root = Path(os.path.realpath(root))
            physical = physical_root / "physical"
            logical = physical_root / "logical"
            physical.mkdir()
            logical.symlink_to(physical, target_is_directory=True)

            self.assertEqual(
                parse_paths(
                    "*** Begin Patch\n"
                    "*** Update File: target.txt\n"
                    "@@\n"
                    "+line\n"
                    "*** End Patch\n",
                    str(logical),
                ),
                [str(physical / "target.txt")],
            )

    def test_ignores_body_text_and_invalid_inputs(self):
        command = """\
*** Begin Patch
*** Update File: real.txt
@@
-old
+*** Add File: not-a-header.txt
 context
*** End Patch
"""
        self.assertEqual(
            parse_paths(command, "/tmp"), [canonical_path("/tmp/real.txt")]
        )
        self.assertEqual(parse_paths(None, "/tmp"), [])
        self.assertEqual(paths_from_event({"tool_input": "not-an-object"}), [])


if __name__ == "__main__":
    unittest.main()
