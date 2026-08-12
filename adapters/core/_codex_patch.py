#!/usr/bin/env python3
"""Extract file paths from Codex apply_patch hook payloads for adapters."""

from __future__ import annotations

import os


PATH_HEADERS = (
    "*** Add File: ",
    "*** Update File: ",
    "*** Delete File: ",
    "*** Move to: ",
)


def canonical_path(path, cwd=None):
    """Resolve a file path through its physical parent without dereferencing the file."""
    root = cwd or os.getcwd()
    candidate = path if os.path.isabs(path) else os.path.join(root, path)
    absolute = os.path.abspath(candidate)
    parent, name = os.path.split(absolute)
    return os.path.join(os.path.realpath(parent), name)


def parse_paths(command, cwd):
    """Return ordered, unique absolute paths named by an apply_patch command."""
    if not isinstance(command, str):
        return []

    paths = []
    seen = set()
    for line in command.splitlines():
        for prefix in PATH_HEADERS:
            if not line.startswith(prefix):
                continue
            raw_path = line[len(prefix) :]
            if not raw_path:
                break
            path = canonical_path(raw_path, cwd)
            if path not in seen:
                seen.add(path)
                paths.append(path)
            break
    return paths


def paths_from_event(event):
    tool_input = event.get("tool_input", {})
    if not isinstance(tool_input, dict):
        return []
    return parse_paths(tool_input.get("command"), event.get("cwd"))
