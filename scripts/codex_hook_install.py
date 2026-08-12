#!/usr/bin/env python3
"""Idempotent helpers for installing Codex command hooks."""

from __future__ import annotations

import json
import os
from pathlib import Path


def load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot read {path}: {exc}")
    if not isinstance(data, dict):
        raise SystemExit(f"Cannot update {path}: top-level JSON must be an object")
    return data


def install_hook(config: dict, spec: dict) -> None:
    groups = config.setdefault("hooks", {}).setdefault(spec["event"], [])
    matcher = spec.get("matcher")
    group = next((item for item in groups if item.get("matcher") == matcher), None)
    if group is None:
        group = {"hooks": []}
        if matcher is not None:
            group["matcher"] = matcher
        groups.append(group)

    handlers = group.setdefault("hooks", [])
    handler = next(
        (item for item in handlers if item.get("command") == spec["command"]),
        None,
    )
    desired = {
        "type": "command",
        "command": spec["command"],
        "timeout": spec.get("timeout", 30),
        "statusMessage": spec["statusMessage"],
    }
    if "additionalContextLimit" in spec:
        desired["additionalContextLimit"] = spec["additionalContextLimit"]
    if handler is None:
        handlers.append(desired)
    else:
        handler.update(desired)
        if "additionalContextLimit" not in desired:
            handler.pop("additionalContextLimit", None)


def save_config(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp{os.getpid()}")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
