#!/usr/bin/env python3
"""Neutral Claude Code hook-registration helpers.

Shared by independent installers (the Zed adapter, the task-memory-bank reindex
hooks) so none has to import another adapter's code — a CC-only user must be able
to install CC hooks without pulling in the Zed adapter, and vice-versa. Keep this
dependency-free (stdlib only) and free of any adapter-specific assumptions.

The registration is idempotent: re-running never duplicates a hook entry.
"""
from __future__ import annotations

import json
import pathlib
import shlex

# Claude Code global settings — the default target for hook registration.
CLAUDE_SETTINGS = pathlib.Path.home() / ".claude" / "settings.json"


def load_settings(settings_path: pathlib.Path = CLAUDE_SETTINGS) -> dict:
    if settings_path.exists():
        return json.loads(settings_path.read_text())
    return {}


def save_settings(data: dict, settings_path: pathlib.Path = CLAUDE_SETTINGS) -> None:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(data, indent=2) + "\n")


def install_hook(
    settings: dict,
    event: str,
    dest,
    matcher,
    args=(),
    legacy_args=(),
) -> None:
    """Register `python3 <dest>` under `event` in a settings dict (idempotent).

    Turn-boundary events (UserPromptSubmit, Stop, SessionStart, SessionEnd) take no
    tool matcher — pass matcher=None; file-tool events (Pre/PostToolUse) pass e.g.
    "Edit|Write". Reuses an existing entry with the same matcher (None matches the
    matcher-less entry) so re-running never duplicates. `legacy_args` identifies
    prior managed command variants to replace without disturbing unrelated hooks.
    Mutates `settings` in place; the caller persists it with save_settings.
    """
    entries = settings.setdefault("hooks", {}).setdefault(event, [])
    cmd = shlex.join(["python3", str(dest), *[str(arg) for arg in args]])
    legacy_cmds = {
        shlex.join(["python3", str(dest), *[str(arg) for arg in old_args]])
        for old_args in legacy_args
    }
    legacy_cmds.discard(cmd)

    for entry in entries:
        if entry.get("matcher") == matcher:
            cmds = entry.setdefault("hooks", [])
            current = next((hook for hook in cmds if hook.get("command") == cmd), None)
            legacy = [hook for hook in cmds if hook.get("command") in legacy_cmds]
            if current is not None:
                if legacy:
                    legacy_ids = {id(hook) for hook in legacy}
                    entry["hooks"] = [
                        hook for hook in cmds if id(hook) not in legacy_ids
                    ]
                    print(f"Migrated {event} hook.")
                    return
                print(f"{event} hook already installed.")
                return
            if legacy:
                legacy[0]["command"] = cmd
                duplicate_ids = {id(hook) for hook in legacy[1:]}
                entry["hooks"] = [
                    hook for hook in cmds if id(hook) not in duplicate_ids
                ]
                print(f"Migrated {event} hook.")
                return
            cmds.append({"type": "command", "command": cmd})
            print(f"Added {event} hook to existing matcher.")
            return

    entry = {"hooks": [{"type": "command", "command": cmd}]}
    if matcher is not None:
        entry["matcher"] = matcher
    entries.append(entry)
    print(f"Added {event} hook with new matcher.")
