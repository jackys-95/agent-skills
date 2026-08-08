#!/usr/bin/env python3
"""Harness-agnostic per-turn manifest: {path -> turn-start base}, keyed by (namespace,
session). Detection (how each harness populates this) stays per-harness; this module is
the shared seam. See EPIC-0003 designs/adapter-taxonomy.md §10 for the full contract.

Deployed as a flat file beside its caller hooks, importing snapshot_revert by name from
the same directory — keep both this and snapshot_revert.py dependency-free (stdlib only).
"""
from __future__ import annotations

import json
import os

import snapshot_revert as sr

NEW = sr.NEW


def _empty(namespace, session_id):
    return {
        "namespace": namespace,
        "session_id": session_id,
        "turn_id": None,
        "cwd": None,
        "roots": [],
        "entries": {},
    }


def _load(namespace, session_id):
    path = sr.manifest_path(namespace, session_id)
    if os.path.isfile(path):
        try:
            with open(path) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError, ValueError):
            pass
    return _empty(namespace, session_id)


def _save(namespace, session_id, data):
    with open(sr.manifest_path(namespace, session_id), "w") as f:
        json.dump(data, f)


def seed_if_new(namespace, session_id, path):
    """Idempotent: if `path` has no entry yet this turn, capture its base (snapshot, or
    "new" if it doesn't exist yet) and add an entry. No-ops if an entry already exists —
    keeps the FIRST base captured this turn, so N edits to the same file in one turn
    still diff/revert against the turn-start state.

    Returns the base that was just captured, or None if this was a no-op (an entry
    already existed) — callers use this to decide whether to print a "queued" message."""
    data = _load(namespace, session_id)
    key = sr.path_hash(path)
    if key in data["entries"]:
        return None
    base = sr.snapshot(namespace, session_id, path)
    data["entries"][key] = {"path": path, "base": base, "root": None}
    _save(namespace, session_id, data)
    return base


def mark_touched(namespace, session_id, path):
    """Ensure `path` is queued in this turn's manifest. A superset of seed_if_new
    (calls it, ignoring the return) — safe to call unconditionally even when
    seed_if_new already ran for `path`. Kept as a distinct call (rather than folded
    into seed_if_new) because a harness may confirm a touch after a tool completes
    independently of capturing the turn-start base before the tool ran — see
    TASK-0022 designs/core-api-plan.md "Non-goals" for why this split is preserved."""
    seed_if_new(namespace, session_id, path)


def bulk_seed(namespace, session_id, roots, cwd=None):
    """Seed a base for every file currently under `roots`. For harnesses without
    per-edit detection — whose tool-call hooks report only a command, not a file path —
    this turn-start bulk copy is the only opportunity to capture pre-edit content, since
    there is no per-edit hook to snapshot lazily from. `roots` is caller-bounded
    configuration, not filesystem-wide, which is what keeps this tractable; skips `.git`
    as the one universal exclusion. Not used by the CC×Zed adapter (no per-edit
    detection gap there) — exists so a future bulk-seeding harness has a real function
    to call, per §10.
    """
    data = _load(namespace, session_id)
    data["cwd"] = cwd
    data["roots"] = list(roots)
    _save(namespace, session_id, data)
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d != ".git"]
            for name in filenames:
                seed_if_new(namespace, session_id, os.path.join(dirpath, name))


def close_turn(namespace, session_id):
    """Return [(path, base), ...] for every entry, then delete the manifest (the
    per-turn queue only). Missing manifest -> []. Called at turn end (Stop).

    Deliberately does NOT touch snapshot bodies or their pointers (see
    snapshot_revert.pointer_path): the diff the user reverts from opens only after
    this runs, and a "r <file>" reply is itself a new turn's UserPromptSubmit — the
    data revert() needs must outlive this call and the next clear_turn call, not just
    survive until the manifest is read once for rendering."""
    path = sr.manifest_path(namespace, session_id)
    if not os.path.isfile(path):
        return []
    data = _load(namespace, session_id)
    edits = [(entry["path"], entry["base"]) for entry in data["entries"].values()]
    try:
        os.remove(path)
    except OSError:
        pass
    return edits


def clear_turn(namespace, session_id):
    """Delete the manifest (the per-turn queue only) without returning anything — the
    turn-start reset for harnesses with incremental per-edit detection, so a
    resumed/steered session starts fresh even if the previous Stop never fired.

    Does NOT touch snapshot bodies or pointers — see close_turn's docstring; the same
    revert-must-outlive-the-turn-boundary reasoning applies here."""
    try:
        os.remove(sr.manifest_path(namespace, session_id))
    except OSError:
        pass
