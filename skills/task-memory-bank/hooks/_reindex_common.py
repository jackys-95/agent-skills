#!/usr/bin/env python3
"""Shared helpers for the task-memory-bank reindex hooks.

The hooks are deployed as flat files into ~/.claude/hooks/, so this module sits
beside them and is imported by name (the running script's own directory is on
sys.path). Keep it dependency-free (stdlib only).

Design: see docs/task-memory-bank-reindex-hooks.md. A PostToolUse hook DETECTS a
memory-bank/KB write and drops a per-collection "dirty" marker; the lifecycle hooks
(UserPromptSubmit / SessionEnd / SessionStart) reindex each dirty collection AFTER
the Zed diff review window for the turn has closed, so reindex never captures an
about-to-be-reverted edit.
"""
import glob
import os
import re

# qmd's collection registry: the single source of truth for every collection's
# filesystem path (tmb projects AND knowledge-base collections), human-readable YAML.
QMD_INDEX = os.path.expanduser("~/.config/qmd/index.yml")

MARKER_PREFIX = "/tmp/cc_tmb_dirty_"


def sanitize(name):
    """Filesystem-safe token for a collection name (marker filename component)."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)


def marker_path(collection):
    return MARKER_PREFIX + sanitize(collection)


def marker_glob():
    return MARKER_PREFIX + "*"


def load_collections():
    """Parse qmd's index.yml into {collection_name: abs_path}.

    Deliberately a tiny hand-rolled parser rather than a YAML dep: index.yml is a
    flat `collections:` map where each collection has an indented `path:` line. We
    only need name→path, so we scan for the two-space-indented collection keys and
    their `path:` children. Returns {} if the file is absent or unreadable.
    """
    try:
        with open(QMD_INDEX) as f:
            text = f.read()
    except OSError:
        return {}

    result = {}
    in_collections = False
    current = None
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

        # A collection name is a 2-space-indented `name:` key with no inline value.
        if indent == 2 and stripped.endswith(":"):
            current = stripped[:-1].strip().strip('"').strip("'")
            continue
        # Its `path:` is nested deeper.
        if current and indent >= 4:
            m = re.match(r"path:\s*(.+)$", stripped)
            if m:
                path = m.group(1).strip().strip('"').strip("'")
                result[current] = os.path.abspath(os.path.expanduser(path))
    return result


def collection_for_path(file_path, collections=None):
    """Return the collection whose registered path is the longest prefix of file_path.

    None if the edited file is under no tracked collection root (the common case for
    ordinary code edits — a fast no-op for the PostToolUse hook).
    """
    if collections is None:
        collections = load_collections()
    target = os.path.abspath(os.path.expanduser(file_path))
    best = None
    best_len = -1
    for name, root in collections.items():
        # Prefix match on path boundaries: under root, or equal to root.
        if target == root or target.startswith(root.rstrip("/") + "/"):
            if len(root) > best_len:
                best, best_len = name, len(root)
    return best


def dirty_collections():
    """Collection names with a pending dirty marker."""
    names = []
    for path in glob.glob(marker_glob()):
        try:
            name = open(path).read().strip()
        except OSError:
            name = ""
        if name:
            names.append(name)
    return names


def clear_marker(collection):
    try:
        os.remove(marker_path(collection))
    except OSError:
        pass
