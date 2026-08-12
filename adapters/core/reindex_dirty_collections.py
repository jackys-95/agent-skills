#!/usr/bin/env python3
"""Flush dirty qmd collections after adapter-observed edits have settled."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from reindex_state import clear_marker, dirty_collections, mark_collection_dirty


def run_reindex(memory_bank: Path, collections: list[str]) -> int:
    command = [sys.executable, str(memory_bank), "reindex"]
    for collection in collections:
        command.extend(["--collection", collection])
    result = subprocess.run(
        command,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        for collection in collections:
            mark_collection_dirty(collection)
    return result.returncode


def launch_reindex(memory_bank: Path, collections: list[str]) -> int:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--memory-bank",
        str(memory_bank),
        "--run",
        *collections,
    ]
    try:
        subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except OSError:
        for collection in collections:
            mark_collection_dirty(collection)
        return 0
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--memory-bank", type=Path, required=True)
    parser.add_argument("--run", nargs="*", metavar="COLLECTION")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.run is not None:
        return run_reindex(args.memory_bank, args.run)

    collections = sorted(set(dirty_collections()))
    if not collections or not args.memory_bank.is_file():
        return 0
    for collection in collections:
        clear_marker(collection)
    return launch_reindex(args.memory_bank, collections)


if __name__ == "__main__":
    raise SystemExit(main())
