#!/usr/bin/env python3
"""Install agent-skills into Codex's local skills directory."""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import sys
from pathlib import Path

from codex_hook_install import install_hook, load_config, save_config
from install_common import (
    install_canonical_skills,
    install_memory_bank_adapter,
    install_plain_skills,
    install_qmd_skill,
    install_tagged_blocks,
    load_manifest,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTER_DIR = REPO_ROOT / "adapters" / "codex"
DEFAULT_TARGET = Path.home() / ".agents" / "skills"
DEFAULT_AGENTS_TARGET = Path.home() / ".codex" / "AGENTS.md"
DEFAULT_CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
PERMISSION_HELPER = ADAPTER_DIR / "scripts" / "codex_memory_permissions.py"
PERMISSION_WRAPPERS = ("memory-init-project", "memory-doctor")
REINDEX_CORE = REPO_ROOT / "adapters" / "core"
REINDEX_HOOK_SOURCES = (
    REINDEX_CORE / "_codex_patch.py",
    ADAPTER_DIR / "hooks" / "post_apply_patch_mark_dirty.py",
    REINDEX_CORE / "reindex_dirty_collections.py",
    REINDEX_CORE / "reindex_state.py",
)


def install_agents_md(source: Path, target: Path, dry_run: bool) -> None:
    install_tagged_blocks(source, target, dry_run, "AGENTS.md")


def install_permission_helpers(target_root: Path, dry_run: bool) -> list[Path]:
    targets = [
        target_root / wrapper / "scripts" / PERMISSION_HELPER.name
        for wrapper in PERMISSION_WRAPPERS
    ]
    for target in targets:
        print(f"Install Codex permission helper: {PERMISSION_HELPER} -> {target}")
        if dry_run:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PERMISSION_HELPER, target)
    return targets


def reindex_hook_specs(install_dir: Path, target_root: Path) -> tuple[dict, ...]:
    def command(name: str, *args: str) -> str:
        parts = ["python3", str(install_dir / name), *args]
        return " ".join(shlex.quote(part) for part in parts)

    memory_bank = target_root / "task-memory-bank" / "scripts" / "memory_bank.py"
    flush = ("--memory-bank", str(memory_bank))
    return (
        {
            "event": "PostToolUse",
            "matcher": "^apply_patch$",
            "command": command("post_apply_patch_mark_dirty.py"),
            "statusMessage": "Track qmd collection changes",
        },
        {
            "event": "UserPromptSubmit",
            "matcher": None,
            "command": command("reindex_dirty_collections.py", *flush),
            "statusMessage": "Reindex changed qmd collections",
        },
        {
            "event": "SessionStart",
            "matcher": "^(startup|resume|clear)$",
            "command": command("reindex_dirty_collections.py", *flush),
            "statusMessage": "Reindex pending qmd collections",
        },
        {
            "event": "SessionEnd",
            "matcher": None,
            "command": command("reindex_dirty_collections.py", *flush),
            "timeout": 3,
            "statusMessage": "Reindex changed qmd collections",
        },
    )


def install_reindex_hooks(
    target_root: Path,
    codex_home: Path,
    dry_run: bool,
) -> None:
    install_dir = codex_home / "hooks" / "agent-skills"
    config_path = codex_home / "hooks.json"
    for source in REINDEX_HOOK_SOURCES:
        target = install_dir / source.name
        print(f"Install Codex reindex runtime: {source} -> {target}")
        if dry_run:
            continue
        install_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        target.chmod(0o755)

    print(f"Install Codex reindex hook config: {config_path}")
    if dry_run:
        return
    config = load_config(config_path)
    for spec in reindex_hook_specs(install_dir, target_root):
        install_hook(config, spec)
    save_config(config_path, config)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        default=str(DEFAULT_TARGET),
        help="Codex skills directory. Defaults to ~/.agents/skills.",
    )
    parser.add_argument(
        "--skip-qmd",
        action="store_true",
        help="Do not install/check the qmd CLI skill dependency.",
    )
    parser.add_argument(
        "--agents-target",
        default=str(DEFAULT_AGENTS_TARGET),
        help="Codex AGENTS.md target. Defaults to ~/.codex/AGENTS.md.",
    )
    parser.add_argument(
        "--skip-agents",
        action="store_true",
        help="Do not install Codex AGENTS.md guidance.",
    )
    parser.add_argument(
        "--codex-home",
        default=str(DEFAULT_CODEX_HOME),
        help="Codex home directory for hooks. Defaults to $CODEX_HOME or ~/.codex.",
    )
    parser.add_argument(
        "--skip-hooks",
        action="store_true",
        help="Do not install Codex qmd reindex hooks.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned installs without writing files.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    target_root = Path(args.target).expanduser().resolve()
    agents_target = Path(args.agents_target).expanduser().resolve()
    codex_home = Path(args.codex_home).expanduser().resolve()
    manifest = load_manifest(ADAPTER_DIR / "wrappers.toml")
    template = (ADAPTER_DIR / "templates" / "wrapper.SKILL.md.tmpl").read_text(
        encoding="utf-8"
    )

    install_canonical_skills(
        REPO_ROOT,
        manifest,
        template,
        target_root,
        args.dry_run,
        wrapper_label="wrapper skill",
    )
    if not args.skip_hooks:
        install_memory_bank_adapter(REPO_ROOT, target_root, args.dry_run)
    install_plain_skills(REPO_ROOT, manifest, target_root, args.dry_run)
    permission_helpers = install_permission_helpers(target_root, args.dry_run)
    if not args.skip_qmd:
        install_qmd_skill(args.dry_run)
    if not args.skip_agents:
        install_agents_md(ADAPTER_DIR / "AGENTS.md", agents_target, args.dry_run)
    if not args.skip_hooks:
        install_reindex_hooks(target_root, codex_home, args.dry_run)

    print("Codex permission helpers:")
    for helper in permission_helpers:
        print(f"  {helper}")
    print(
        "For each external memory or knowledge root, run the installed helper "
        "with `check` once during setup; use explicit `backfill` only when "
        "persistent config repair is wanted."
    )
    if not args.skip_hooks:
        print(
            "Start a new Codex session and use /hooks to review and trust the "
            "installed reindex hooks."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
