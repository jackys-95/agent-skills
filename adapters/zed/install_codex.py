#!/usr/bin/env python3
"""Install the Zed adapter hooks for Codex CLI."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shlex
import shutil
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
HOOKS_SOURCE = pathlib.Path(__file__).parent / "hooks"
CORE_SOURCE = pathlib.Path(__file__).parent.parent / "core"
CODEX_AGENTS_SOURCE = pathlib.Path(__file__).parent / "AGENTS.md"
PHASE_TURNS_SOURCE = pathlib.Path(__file__).parent / "phase-turns.md"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from install_common import install_tagged_blocks  # noqa: E402


RUNTIME_FILES = (
    HOOKS_SOURCE / "_codex_patch.py",
    HOOKS_SOURCE / "_zed_common.py",
    HOOKS_SOURCE / "reset_codex_zed_turn.py",
    HOOKS_SOURCE / "pre_apply_patch_zed_snapshot.py",
    HOOKS_SOURCE / "post_apply_patch_zed_touch.py",
    HOOKS_SOURCE / "stop_flush_codex_zed_diffs.py",
    HOOKS_SOURCE / "revert_codex_zed_snapshot.py",
    CORE_SOURCE / "manifest.py",
    CORE_SOURCE / "snapshot_revert.py",
)


def hook_specs(install_dir):
    def command(name):
        return f"python3 {shlex.quote(str(install_dir / name))}"

    return (
        {
            "event": "UserPromptSubmit",
            "matcher": None,
            "command": command("reset_codex_zed_turn.py"),
            "statusMessage": "Reset Zed turn review",
        },
        {
            "event": "PreToolUse",
            "matcher": "^apply_patch$",
            "command": command("pre_apply_patch_zed_snapshot.py"),
            "statusMessage": "Snapshot files for Zed review",
        },
        {
            "event": "PostToolUse",
            "matcher": "^apply_patch$",
            "command": command("post_apply_patch_zed_touch.py"),
            "statusMessage": "Confirm files for Zed review",
        },
        {
            "event": "Stop",
            "matcher": None,
            "command": command("stop_flush_codex_zed_diffs.py"),
            "statusMessage": "Open Zed turn review",
        },
    )


def load_config(path):
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot read {path}: {exc}")
    if not isinstance(data, dict):
        raise SystemExit(f"Cannot update {path}: top-level JSON must be an object")
    return data


def install_hook(config, spec):
    groups = config.setdefault("hooks", {}).setdefault(spec["event"], [])
    matcher = spec["matcher"]
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
        "timeout": 30,
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


def save_config(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp{os.getpid()}")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def install_runtime(install_dir, dry_run):
    for source in RUNTIME_FILES:
        target = install_dir / source.name
        print(f"Install ZedCodex runtime: {source} -> {target}")
        if dry_run:
            continue
        install_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        target.chmod(0o755)


def build_parser():
    default_home = pathlib.Path(
        os.environ.get("CODEX_HOME", pathlib.Path.home() / ".codex")
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--codex-home",
        default=str(default_home),
        help="Codex home directory. Defaults to $CODEX_HOME or ~/.codex.",
    )
    parser.add_argument(
        "--agents-target",
        default=str(default_home / "AGENTS.md"),
        help="Codex global AGENTS.md target.",
    )
    parser.add_argument(
        "--skip-agents",
        action="store_true",
        help="Do not install the ZedCodex AGENTS.md guidance.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned changes without writing files.",
    )
    return parser


def main():
    args = build_parser().parse_args()
    codex_home = pathlib.Path(args.codex_home).expanduser().resolve()
    install_dir = codex_home / "hooks" / "zedcodex"
    config_path = codex_home / "hooks.json"
    agents_target = pathlib.Path(args.agents_target).expanduser().resolve()

    install_runtime(install_dir, args.dry_run)
    config = load_config(config_path)
    for spec in hook_specs(install_dir):
        install_hook(config, spec)
    print(f"Install ZedCodex hook config: {config_path}")
    if not args.dry_run:
        save_config(config_path, config)

    if not args.skip_agents:
        install_tagged_blocks(
            CODEX_AGENTS_SOURCE,
            agents_target,
            args.dry_run,
            "ZedCodex AGENTS.md",
            tags={"zed-codex-adapter"},
        )
        install_tagged_blocks(
            PHASE_TURNS_SOURCE,
            agents_target,
            args.dry_run,
            "Zed phase-turn AGENTS.md",
            tags={"phase-turns"},
        )

    print(
        "\nNext steps:\n"
        "1. In Zed's terminal environment, set CODEX_ZED_HOOK=1.\n"
        "2. Start a new Codex CLI session and run /hooks.\n"
        "3. Review and trust the four new ZedCodex hooks.\n"
        "Codex stores trust against each hook definition; changed definitions "
        "must be reviewed again."
    )
    if not shutil.which("zed"):
        print("\nWarning: `zed` is not on PATH; turn-end diff review cannot open.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
