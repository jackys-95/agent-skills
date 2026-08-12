#!/usr/bin/env python3
"""PostToolUse hook: mark a memory-bank / knowledge-base collection dirty.

DETECTION ONLY — never reindexes. Opening a reindex here would run mid-turn, before
the Zed diff review window closes, and could index a memory-bank edit the user is
about to revert. So this hook just drops a per-collection dirty marker; the
lifecycle hooks (UserPromptSubmit / SessionEnd / SessionStart) do the actual reindex
once the turn has settled. See docs/task-memory-bank-reindex-hooks.md.

Fires on every Edit|Write, so the hot path is cheap: parse ~1 KB of qmd index.yml
and prefix-match. A path under no tracked collection root is a fast no-op (the common
case for ordinary code edits).
"""
import json
import sys

from reindex_state import mark_path_dirty


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    file_path = event.get("tool_input", {}).get("file_path", "")
    if not file_path:
        sys.exit(0)

    mark_path_dirty(file_path)


if __name__ == "__main__":
    main()
