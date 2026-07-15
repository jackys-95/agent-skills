#!/usr/bin/env python3
"""Unit tests for collections.yaml schema, parser, surgical writers, and migration.

Run: python3 test_collections_yaml.py

Stdlib only (unittest + tempfile). No network, no qmd. The load-bearing tests are
the comment-preservation ones: writes must leave untouched lines byte-for-byte.
The unit under test is the collections_yaml module (extracted from memory_bank).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import collections_yaml as mb


def _tmp(text: str) -> Path:
    d = Path(tempfile.mkdtemp())
    p = d / "collections.yaml"
    p.write_text(text, encoding="utf-8")
    return p


class ParserTests(unittest.TestCase):
    def test_missing_file_returns_empty(self):
        self.assertEqual(mb.parse_collections(Path("/no/such/file.yaml")), {})

    def test_empty_file(self):
        p = _tmp("collections:\n")
        self.assertEqual(mb.parse_collections(p), {})

    def test_repos_list_n_entries(self):
        p = _tmp(
            "collections:\n"
            "  mb-x:\n"
            "    kind: project\n"
            "    repos:\n"
            "      - /a\n"
            "      - /b\n"
        )
        data = mb.parse_collections(p)
        self.assertEqual(data["mb-x"]["repos"], ["/a", "/b"])

    def test_repos_empty_list(self):
        p = _tmp("collections:\n  mb-x:\n    repos: []\n    kind: project\n")
        self.assertEqual(mb.parse_collections(p)["mb-x"]["repos"], [])

    def test_repos_single_entry(self):
        p = _tmp("collections:\n  mb-x:\n    repos:\n      - /only\n")
        self.assertEqual(mb.parse_collections(p)["mb-x"]["repos"], ["/only"])

    def test_legacy_scalar_repo_reads_as_one_element_list(self):
        p = _tmp("collections:\n  mb-x:\n    repo: /legacy\n    kind: project\n")
        data = mb.parse_collections(p)
        self.assertEqual(data["mb-x"]["repos"], ["/legacy"])
        self.assertEqual(data["mb-x"]["repo"], "/legacy")

    def test_legacy_empty_scalar_repo(self):
        p = _tmp("collections:\n  mb-x:\n    repo:\n    kind: project\n")
        data = mb.parse_collections(p)
        self.assertEqual(data["mb-x"]["repos"], [])

    def test_inline_comment_stripped_from_scalar(self):
        p = _tmp("collections:\n  mb-x:\n    context: proj  # a note\n")
        self.assertEqual(mb.parse_collections(p)["mb-x"]["context"], "proj")

    def test_inline_comment_stripped_from_list_item(self):
        p = _tmp("collections:\n  mb-x:\n    repos:\n      - /a  # main repo\n")
        self.assertEqual(mb.parse_collections(p)["mb-x"]["repos"], ["/a"])

    def test_quoted_hash_is_literal(self):
        p = _tmp('collections:\n  mb-x:\n    context: "a # b"\n')
        self.assertEqual(mb.parse_collections(p)["mb-x"]["context"], "a # b")

    def test_full_line_and_blank_ignored(self):
        p = _tmp(
            "collections:\n"
            "  # a comment\n"
            "\n"
            "  mb-x:\n"
            "    kind: project\n"
        )
        self.assertEqual(list(mb.parse_collections(p)), ["mb-x"])

    def test_multiple_collections(self):
        p = _tmp(
            "collections:\n"
            "  mb-a:\n    kind: project\n    repos:\n      - /a\n"
            "\n"
            "  mb-b:\n    kind: project\n    repos:\n      - /b\n"
        )
        data = mb.parse_collections(p)
        self.assertEqual(set(data), {"mb-a", "mb-b"})
        self.assertEqual(data["mb-b"]["repos"], ["/b"])

    def test_list_terminates_on_next_key(self):
        p = _tmp(
            "collections:\n  mb-x:\n    repos:\n      - /a\n    context: proj\n"
        )
        data = mb.parse_collections(p)
        self.assertEqual(data["mb-x"]["repos"], ["/a"])
        self.assertEqual(data["mb-x"]["context"], "proj")


class CommentPreservationTests(unittest.TestCase):
    """The load-bearing tests: writes must not disturb untouched lines."""

    COMMENTED = (
        "collections:\n"
        "  # routing source of truth; repos: is association, not ownership\n"
        "  mb-a:\n"
        "    path: /p/a\n"
        "    kind: project\n"
        "    project: a\n"
        "    repos:\n"
        "      - /repo/a  # primary\n"
        "    context: a\n"
        "\n"
        "  mb-b:\n"
        "    path: /p/b\n"
        "    kind: project\n"
        "    project: b\n"
        "    repos:\n"
        "      - /repo/b\n"
        "    context: b\n"
    )

    def test_upsert_existing_block_leaves_other_lines_byte_identical(self):
        p = _tmp(self.COMMENTED)
        # Replace mb-a's body (add a repo); mb-b and all comments must be untouched.
        mb.upsert_collection_block(
            p, "mb-a",
            {"path": "/p/a", "kind": "project", "project": "a",
             "repos": ["/repo/a", "/repo/a2"], "context": "a"},
        )
        result = p.read_text(encoding="utf-8")
        # The comment header and the entire mb-b block survive verbatim.
        self.assertIn(
            "  # routing source of truth; repos: is association, not ownership\n",
            result,
        )
        self.assertIn(
            "  mb-b:\n"
            "    path: /p/b\n"
            "    kind: project\n"
            "    project: b\n"
            "    repos:\n"
            "      - /repo/b\n"
            "    context: b\n",
            result,
        )
        self.assertIn("      - /repo/a2\n", result)
        # mb-a still parses with both repos.
        self.assertEqual(mb.parse_collections(p)["mb-a"]["repos"], ["/repo/a", "/repo/a2"])

    def test_append_new_block_preserves_existing(self):
        p = _tmp(self.COMMENTED)
        mb.upsert_collection_block(
            p, "mb-c",
            {"path": "/p/c", "kind": "project", "project": "c", "repos": ["/repo/c"], "context": "c"},
        )
        result = p.read_text(encoding="utf-8")
        self.assertIn(
            "  # routing source of truth; repos: is association, not ownership\n",
            result,
        )
        self.assertIn("      - /repo/a  # primary\n", result)  # inline comment intact
        data = mb.parse_collections(p)
        self.assertEqual(set(data), {"mb-a", "mb-b", "mb-c"})

    def test_inline_repo_comment_survives_untouched_block(self):
        p = _tmp(self.COMMENTED)
        mb.upsert_collection_block(
            p, "mb-b",
            {"path": "/p/b", "kind": "project", "project": "b", "repos": ["/repo/b"], "context": "b"},
        )
        # Editing mb-b must not touch mb-a's inline comment.
        self.assertIn("      - /repo/a  # primary\n", p.read_text(encoding="utf-8"))


class SurgicalWriterTests(unittest.TestCase):
    def test_create_fresh_file(self):
        d = Path(tempfile.mkdtemp())
        p = d / "collections.yaml"
        mb.create_collections_file(
            p, "mb-x",
            {"path": "/p", "mode": "recursive", "kind": "project",
             "project": "x", "repos": ["/r"], "context": "x"},
        )
        text = p.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("collections:\n"))
        self.assertIn("  mb-x:\n", text)
        self.assertIn("    repos:\n      - /r\n", text)

    def test_upsert_creates_when_missing(self):
        d = Path(tempfile.mkdtemp())
        p = d / "collections.yaml"
        mb.upsert_collection_block(p, "mb-x", {"kind": "project", "repos": []})
        self.assertIn("    repos: []\n", p.read_text(encoding="utf-8"))

    def test_repo_scalar_never_emitted(self):
        p = _tmp("collections:\n")
        mb.upsert_collection_block(p, "mb-x", {"repo": "/legacy", "kind": "project"})
        text = p.read_text(encoding="utf-8")
        self.assertNotIn("repo: /legacy", text)  # legacy scalar dropped
        self.assertIn("repos:", text)

    def test_append_repo_primitive(self):
        p = _tmp("collections:\n  mb-x:\n    kind: project\n    repos:\n      - /a\n")
        changed = mb.append_repo(p, "mb-x", "/b")
        self.assertTrue(changed)
        self.assertEqual(mb.parse_collections(p)["mb-x"]["repos"], ["/a", "/b"])

    def test_append_repo_idempotent_when_present(self):
        p = _tmp("collections:\n  mb-x:\n    kind: project\n    repos:\n      - /a\n")
        self.assertFalse(mb.append_repo(p, "mb-x", "/a"))

    def test_append_repo_unknown_block(self):
        p = _tmp("collections:\n  mb-x:\n    kind: project\n    repos:\n      - /a\n")
        self.assertFalse(mb.append_repo(p, "mb-nope", "/b"))

    def test_write_is_idempotent(self):
        p = _tmp("collections:\n")
        fields = {"path": "/p", "kind": "project", "project": "x", "repos": ["/r"], "context": "x"}
        mb.upsert_collection_block(p, "mb-x", fields)
        once = p.read_text(encoding="utf-8")
        mb.upsert_collection_block(p, "mb-x", fields)
        self.assertEqual(once, p.read_text(encoding="utf-8"))


class MigrationTests(unittest.TestCase):
    def test_scalar_repo_to_list(self):
        text = (
            "collections:\n"
            "  mb-x:\n    path: /p\n    kind: project\n    project: x\n    repo: /r\n    context: x\n"
        )
        out = mb.migrate_text(text)
        self.assertIn("    repos:\n      - /r\n", out)
        self.assertNotIn("repo: /r", out)
        self.assertEqual(mb.parse_collections(_tmp(out))["mb-x"]["repos"], ["/r"])

    def test_empty_repo_to_empty_list(self):
        text = "collections:\n  mb-x:\n    kind: project\n    repo:\n    context: x\n"
        out = mb.migrate_text(text)
        self.assertIn("    repos: []\n", out)

    def test_drops_umbrella_global_block(self):
        text = (
            "collections:\n"
            "  task-memory-bank:\n    path: /root\n    mode: recursive\n    kind: global\n"
            "\n"
            "  mb-x:\n    kind: project\n    repo: /r\n    context: x\n"
        )
        out = mb.migrate_text(text)
        self.assertNotIn("task-memory-bank", out)
        self.assertNotIn("kind: global", out)
        self.assertIn("  mb-x:\n", out)

    def test_preserves_comments(self):
        text = (
            "collections:\n"
            "  # keep me\n"
            "  mb-x:\n    kind: project\n    repo: /r  # primary\n    context: x\n"
        )
        out = mb.migrate_text(text)
        self.assertIn("  # keep me\n", out)

    def test_idempotent(self):
        text = "collections:\n  mb-x:\n    kind: project\n    repos:\n      - /r\n    context: x\n"
        once = mb.migrate_text(text)
        twice = mb.migrate_text(once)
        self.assertEqual(once, twice)
        # Already-in-list schema is unchanged.
        self.assertEqual(text.rstrip() + "\n", once)


class RoundTripTests(unittest.TestCase):
    FIXTURES = [
        "collections:\n  mb-x:\n    kind: project\n    repos:\n      - /a\n      - /b\n    context: x\n",
        "collections:\n  mb-x:\n    kind: project\n    repos: []\n    context: x\n",
        'collections:\n  mb-x:\n    kind: project\n    context: "a # b"\n    repos:\n      - /a\n',
    ]

    def test_parse_write_parse_semantic_equality(self):
        for fixture in self.FIXTURES:
            with self.subTest(fixture=fixture):
                p = _tmp(fixture)
                before = mb.parse_collections(p)
                name = next(iter(before))
                mb.upsert_collection_block(p, name, dict(before[name]))
                after = mb.parse_collections(p)
                self.assertEqual(before[name].get("repos"), after[name].get("repos"))
                self.assertEqual(before[name].get("context"), after[name].get("context"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
