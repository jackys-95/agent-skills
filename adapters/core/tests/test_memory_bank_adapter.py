#!/usr/bin/env python3
"""Tests for adapter-composed task-memory-bank command marking."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

CORE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
CANONICAL = REPO_ROOT / "skills" / "task-memory-bank" / "scripts" / "memory_bank.py"

sys.path.insert(0, str(CORE_DIR))
import memory_bank_adapter as adapter  # noqa: E402


class MemoryBankAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.bank = self.root / "bank"
        self.project = self.bank / "projects" / "demo"
        self.project.mkdir(parents=True)
        config = self.bank / ".memory-bank" / "collections.yaml"
        config.parent.mkdir(parents=True)
        config.write_text(
            "collections:\n"
            "  mb-demo:\n"
            f"    path: {self.project}\n"
            "    mode: recursive\n"
            "    kind: project\n"
            "    project: demo\n"
            "    repos: []\n"
            "    context: demo\n",
            encoding="utf-8",
        )
        qmd_index = self.root / "config" / "qmd" / "index.yml"
        qmd_index.parent.mkdir(parents=True)
        qmd_index.write_text(
            "collections:\n"
            "  mb-demo:\n"
            f"    path: {self.project}\n",
            encoding="utf-8",
        )
        self.markers = self.root / "markers"
        self.env = mock.patch.dict(
            os.environ,
            {
                "XDG_CONFIG_HOME": str(self.root / "config"),
                "TMB_REINDEX_MARKER_DIR": str(self.markers),
            },
        )
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()
        self._tmp.cleanup()

    def marker(self) -> Path:
        return self.markers / "tmb_qmd_dirty_mb-demo"

    def new_work_args(self) -> list[str]:
        return [
            "new-work",
            "--memory-root",
            str(self.bank),
            "--project",
            "demo",
            "--type",
            "task",
            "--title",
            "Adapter test",
            "--repo",
            str(self.root / "repo"),
        ]

    def test_successful_project_write_marks_collection(self) -> None:
        self.assertEqual(adapter.main(self.new_work_args(), CANONICAL), 0)

        self.assertEqual(self.marker().read_text(encoding="utf-8"), "mb-demo")

    def test_failed_command_does_not_mark(self) -> None:
        missing_bank = self.root / "missing-bank"
        args = self.new_work_args()
        args[2] = str(missing_bank)

        with self.assertRaises(SystemExit):
            adapter.main(args, CANONICAL)

        self.assertFalse(self.markers.exists())

    def test_standalone_canonical_write_creates_no_adapter_marker(self) -> None:
        canonical = adapter.load_canonical(CANONICAL)
        args = canonical.build_parser().parse_args(self.new_work_args())

        args.func(args)

        self.assertFalse(self.markers.exists())

    def test_work_path_write_marks_containing_collection(self) -> None:
        work = self.project / "work" / "tasks" / "example-work-item"
        work.mkdir(parents=True)

        self.assertEqual(
            adapter.main(
                [
                    "append-history",
                    "--work",
                    str(work),
                    "--summary",
                    "Implemented the adapter.",
                ],
                CANONICAL,
            ),
            0,
        )

        self.assertEqual(self.marker().read_text(encoding="utf-8"), "mb-demo")

    def test_read_only_migration_check_does_not_mark(self) -> None:
        self.assertEqual(
            adapter.main(
                ["migrate-collections", "--memory-root", str(self.bank), "--check"],
                CANONICAL,
            ),
            0,
        )

        self.assertFalse(self.markers.exists())

    def test_changed_migration_marks_project_collection(self) -> None:
        config = self.bank / ".memory-bank" / "collections.yaml"
        config.write_text(
            "collections:\n"
            "  mb-demo:\n"
            f"    path: {self.project}\n"
            "    kind: project\n"
            "    project: demo\n"
            "    repo: /old/repo\n"
            "    context: demo\n",
            encoding="utf-8",
        )

        self.assertEqual(
            adapter.main(
                ["migrate-collections", "--memory-root", str(self.bank)],
                CANONICAL,
            ),
            0,
        )

        self.assertEqual(self.marker().read_text(encoding="utf-8"), "mb-demo")


if __name__ == "__main__":
    unittest.main()
