#!/usr/bin/env python3
"""Mark qmd collections changed by a successful Codex apply_patch call."""

from __future__ import annotations

import json
import sys

from _codex_patch import paths_from_event
from reindex_state import mark_path_dirty


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(event, dict):
        return 0

    for path in paths_from_event(event):
        mark_path_dirty(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
