#!/usr/bin/env python3
"""Snapshot/revert primitives: pure file-copy semantics, no turn/manifest bookkeeping.

Self-contained (stdlib only, no sibling-module imports) so it's independently testable
and deployable. manifest.py builds the turn-scoped manifest on top of this. Deployed as
a flat file beside its callers (hook scripts import it by name), so keep it
dependency-free (see #51 for the full contract).
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sys

NEW = "new"


def path_hash(path):
    """Stable short hash of a path — keys snapshot filenames and manifest entries."""
    return hashlib.sha256(path.encode()).hexdigest()[:16]


def sanitize_session(session_id):
    """Reduce a hook event's session id to a filesystem-safe token.

    Falls back to "nosession" when the event carries no id, which degrades gracefully
    to single-session behavior.
    """
    safe = "".join(c for c in (session_id or "") if c.isalnum() or c in "-_")
    return safe or "nosession"


def manifest_path(namespace, session_id):
    return f"/tmp/{namespace}_manifest_{sanitize_session(session_id)}.json"


def snapshot_dir(namespace, session_id):
    return f"/tmp/{namespace}_snap_{sanitize_session(session_id)}"


def pointer_path(namespace, path):
    """File holding the latest base for `path` — written by snapshot(), read by
    revert(). Keyed ONLY by path (no session/turn) so it survives turn boundaries: the
    diff the user reverts from opens (in Zed) only after Stop has already run and the
    turn's manifest may already be cleared, and a "r <file>" reply is itself a new
    turn's UserPromptSubmit — the pointer must outlive both. This is the same
    process-wide, indefinitely-persisting-until-overwritten lifetime the pre-extraction
    `pointer_path` had; not scoping it to the turn manifest is deliberate, not an
    oversight."""
    return f"/tmp/{namespace}_ptr_{path_hash(path)}"


def snapshot(namespace, session_id, path):
    """Copy `path`'s current content into this session's snapshot dir and durably
    record it as `path`'s pointer (see pointer_path). Returns the literal "new" (not a
    path) if `path` doesn't exist — there is no pre-edit content to capture, and
    reverting a "new" base means delete."""
    if not os.path.isfile(path):
        base = NEW
    else:
        directory = snapshot_dir(namespace, session_id)
        os.makedirs(directory, exist_ok=True)
        base = os.path.join(directory, path_hash(path))
        shutil.copyfile(path, base)
    with open(pointer_path(namespace, path), "w") as f:
        f.write(base)
    return base


def revert(namespace, path):
    """Restore `path` to the base recorded in its pointer file. Takes no session_id —
    pointer lookups are process-wide by path hash, not session/turn-scoped (mirrors the
    pre-extraction behavior), so a caller replying to a stale "[Zed] ... reply r <file>"
    line need not know which session or turn wrote it, and the pointer survives even
    though the turn manifest that produced it is long since cleared.

    Returns True on success, False (after printing an error to stderr) if `path` has no
    pointer or its recorded snapshot is missing."""
    ptr = pointer_path(namespace, path)
    if not os.path.isfile(ptr):
        print(f"No snapshot found for {path}", file=sys.stderr)
        return False
    with open(ptr) as f:
        base = f.read().strip()
    if base == NEW:
        if os.path.isfile(path):
            os.remove(path)
        print(f"Reverted {path} — deleted (was created this turn)")
        return True
    if not os.path.isfile(base):
        print(f"Snapshot file missing: {base}", file=sys.stderr)
        return False
    shutil.copyfile(base, path)
    print(f"Reverted {path} to {base}")
    return True
