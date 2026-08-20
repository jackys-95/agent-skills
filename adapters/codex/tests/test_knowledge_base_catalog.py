#!/usr/bin/env python3
"""Tests for knowledge-base registry parsing and catalog indexes."""

from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import knowledge_base_catalog as catalog  # noqa: E402


def dedent(text: str) -> str:
    return textwrap.dedent(text).lstrip("\n")


class TestKnowledgeBaseCatalog(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.registry_path = self.tmp / "registry.yaml"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_registry(self, text: str) -> None:
        self.registry_path.write_text(dedent(text), encoding="utf-8")

    def test_load_builds_name_and_domain_role_indexes(self) -> None:
        self.write_registry(
            """\
            collections:
              demo-knowledge-secondary:
                contains: knowledge
                domain: demo
              demo-learning:
                contains: learning
                domain: demo
              demo-knowledge-primary:
                contains: "knowledge" # reviewed material
                domain: 'demo'
              shared-knowledge:
                contains: knowledge
            """
        )

        registry = catalog.load_knowledge_base_registry(self.registry_path)

        self.assertEqual(
            set(registry.by_name),
            {
                "demo-knowledge-secondary",
                "demo-learning",
                "demo-knowledge-primary",
                "shared-knowledge",
            },
        )
        self.assertEqual(
            tuple(
                entry.name
                for entry in registry.by_domain_and_role[
                    ("demo", "knowledge")
                ]
            ),
            ("demo-knowledge-primary", "demo-knowledge-secondary"),
        )
        self.assertEqual(
            registry.by_name["shared-knowledge"].domain,
            "default",
        )
        self.assertFalse(
            registry.by_name["shared-knowledge"].has_explicit_domain
        )

    def test_empty_map_and_allowed_missing_file_produce_empty_indexes(self) -> None:
        self.write_registry("collections: {}\n")

        empty_map = catalog.load_knowledge_base_registry(self.registry_path)
        missing = catalog.load_knowledge_base_registry(
            self.tmp / "missing.yaml",
            allow_missing=True,
        )

        for registry in (empty_map, missing):
            self.assertEqual(registry.by_name, {})
            self.assertEqual(registry.by_domain_and_role, {})

    def test_rejects_duplicate_collection_and_field_names(self) -> None:
        cases = {
            "collection": (
                """\
                collections:
                  demo:
                    contains: knowledge
                  demo:
                    contains: learning
                """,
                "Duplicate collection 'demo'",
            ),
            "field": (
                """\
                collections:
                  demo:
                    contains: knowledge
                    contains: learning
                """,
                "Duplicate field 'contains'",
            ),
        }
        for name, (text, expected) in cases.items():
            with self.subTest(name=name):
                self.write_registry(text)

                with self.assertRaises(catalog.KnowledgeBaseCatalogError) as raised:
                    catalog.load_knowledge_base_registry(self.registry_path)

                self.assertIn(expected, str(raised.exception))

    def test_rejects_tabs_and_unsupported_nesting(self) -> None:
        cases = {
            "tab indentation": (
                "collections:\n\tdemo:\n    contains: knowledge\n",
                "indentation must use spaces",
            ),
            "nested field": (
                """\
                collections:
                  demo:
                      contains: knowledge
                """,
                "Unsupported registry structure",
            ),
        }
        for name, (text, expected) in cases.items():
            with self.subTest(name=name):
                self.write_registry(text)

                with self.assertRaises(catalog.KnowledgeBaseCatalogError) as raised:
                    catalog.load_knowledge_base_registry(self.registry_path)

                self.assertIn(expected, str(raised.exception))

    def test_rejects_a_missing_collections_root(self) -> None:
        self.write_registry(
            """\
            metadata:
              owner: query-kb
            """
        )

        with self.assertRaises(catalog.KnowledgeBaseCatalogError) as raised:
            catalog.load_knowledge_base_registry(self.registry_path)

        self.assertIn(
            "missing a top-level collections map",
            str(raised.exception),
        )


if __name__ == "__main__":
    unittest.main()
