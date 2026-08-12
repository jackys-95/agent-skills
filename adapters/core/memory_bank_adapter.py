#!/usr/bin/env python3
"""Adapter-owned facade for canonical task-memory-bank script commands."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from reindex_state import mark_collection_dirty, mark_path_dirty


CANONICAL_FILENAME = "_memory_bank.py"
PROJECT_WRITE_COMMANDS = {"init-project", "new-work", "regen-index"}
WORK_PATH_WRITE_COMMANDS = {"branch-work", "append-history"}


def load_canonical(path: Path) -> ModuleType:
    if not path.is_file():
        raise SystemExit(f"Canonical memory-bank script not found: {path}")
    spec = importlib.util.spec_from_file_location("_canonical_memory_bank", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Unable to load canonical memory-bank script: {path}")
    module = importlib.util.module_from_spec(spec)
    script_dir = str(path.parent)
    sys.path.insert(0, script_dir)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(script_dir)
    return module


def mark_successful_command(
    args: argparse.Namespace,
    canonical: ModuleType,
    result: object,
) -> None:
    command = args.command
    if command in PROJECT_WRITE_COMMANDS:
        project = canonical.slugify(args.project)
        mark_collection_dirty(canonical.collection_name(project))
    elif command in WORK_PATH_WRITE_COMMANDS:
        mark_path_dirty(args.work)
    elif command == "migrate-collections" and result is True:
        root = canonical.expand(args.root)
        collections = canonical.parse_collections(
            root / ".memory-bank" / "collections.yaml"
        )
        for name, fields in collections.items():
            if fields.get("kind") == "project":
                mark_collection_dirty(name)


def main(
    argv: list[str] | None = None,
    canonical_path: Path | None = None,
) -> int:
    script = canonical_path or Path(__file__).with_name(CANONICAL_FILENAME)
    canonical = load_canonical(script)
    args = canonical.build_parser().parse_args(argv)
    result = args.func(args)
    mark_successful_command(args, canonical, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
