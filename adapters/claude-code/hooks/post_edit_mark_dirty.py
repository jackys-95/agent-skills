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

from _reindex_common import collection_for_path, marker_path


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    file_path = event.get("tool_input", {}).get("file_path", "")
    if not file_path:
        sys.exit(0)

    collection = collection_for_path(file_path)
    if not collection:
        sys.exit(0)  # edit is outside every tracked collection — nothing to reindex

    # Marker contents = the collection name, so the lifecycle hooks enumerate dirty
    # collections from the markers alone. Idempotent: re-marking is a cheap rewrite.
    with open(marker_path(collection), "w") as f:
        f.write(collection)


if __name__ == "__main__":
    main()
