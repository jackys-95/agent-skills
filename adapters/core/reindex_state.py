#!/usr/bin/env python3
"""Dirty-collection state shared by adapter lifecycle hooks."""

from __future__ import annotations

import glob
import os
import re
import tempfile
from pathlib import Path


MARKER_STEM = "tmb_qmd_dirty_"


def qmd_index_path() -> Path:
    config_home = Path(
        os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
    ).expanduser()
    return config_home / "qmd" / "index.yml"


def marker_dir() -> Path:
    return Path(
        os.environ.get("TMB_REINDEX_MARKER_DIR", tempfile.gettempdir())
    ).expanduser()


def sanitize(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)


def marker_path(collection: str) -> Path:
    return marker_dir() / f"{MARKER_STEM}{sanitize(collection)}"


def marker_glob() -> str:
    return str(marker_dir() / f"{MARKER_STEM}*")


def load_collections() -> dict[str, str]:
    """Parse qmd's flat collection map into collection-name to absolute path."""
    try:
        text = qmd_index_path().read_text(encoding="utf-8")
    except OSError:
        return {}

    result: dict[str, str] = {}
    in_collections = False
    current: str | None = None
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        stripped = raw.strip()

        if indent == 0:
            in_collections = stripped.rstrip() == "collections:"
            current = None
            continue
        if not in_collections:
            continue
        if indent == 2 and stripped.endswith(":"):
            current = stripped[:-1].strip().strip('"').strip("'")
            continue
        if current and indent >= 4:
            match = re.match(r"path:\s*(.+)$", stripped)
            if match:
                path = match.group(1).strip().strip('"').strip("'")
                result[current] = os.path.realpath(os.path.expanduser(path))
    return result


def collection_for_path(
    file_path: str | os.PathLike[str],
    collections: dict[str, str] | None = None,
) -> str | None:
    if collections is None:
        collections = load_collections()
    target = os.path.realpath(os.path.expanduser(os.fspath(file_path)))
    best: str | None = None
    best_len = -1
    for name, root in collections.items():
        if target == root or target.startswith(root.rstrip(os.sep) + os.sep):
            if len(root) > best_len:
                best, best_len = name, len(root)
    return best


def mark_collection_dirty(collection: str) -> None:
    path = marker_path(collection)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(collection, encoding="utf-8")


def mark_path_dirty(file_path: str | os.PathLike[str]) -> str | None:
    collection = collection_for_path(file_path)
    if collection:
        mark_collection_dirty(collection)
    return collection


def dirty_collections() -> list[str]:
    names = []
    for raw_path in glob.glob(marker_glob()):
        try:
            name = Path(raw_path).read_text(encoding="utf-8").strip()
        except OSError:
            name = ""
        if name:
            names.append(name)
    return names


def clear_marker(collection: str) -> None:
    try:
        marker_path(collection).unlink()
    except OSError:
        pass
