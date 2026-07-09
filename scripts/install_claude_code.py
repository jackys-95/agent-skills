#!/usr/bin/env python3
"""Install task-memory-bank Claude Code skill wrappers."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# Adapter-neutral hook-registration helpers (same scripts/ dir).
from hook_install import install_hook, load_settings, save_settings
from install_common import (
    install_canonical_skills,
    install_plain_skills,
    install_qmd_skill,
    install_tagged_blocks,
    load_manifest,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTER_DIR = REPO_ROOT / "adapters" / "claude-code"
DEFAULT_TARGET = Path.home() / ".claude" / "skills"
CLAUDE_HOOKS_DIR = Path.home() / ".claude" / "hooks"

# task-memory-bank reindex hooks. A PostToolUse detector marks a memory-bank/KB
# collection dirty on Edit|Write; three turn-boundary events flush the reindex once
# the diff review window has closed. _reindex_common.py is the shared module (copied
# beside the hooks, not registered). See docs/task-memory-bank-reindex-hooks.md.
REINDEX_HOOKS_SRC = ADAPTER_DIR / "hooks"
REINDEX_HOOKS = [
    {"event": "PostToolUse", "matcher": "Edit|Write", "script": "post_edit_mark_dirty.py"},
    {"event": "UserPromptSubmit", "matcher": None, "script": "reindex_dirty_collections.py"},
    {"event": "SessionEnd", "matcher": None, "script": "reindex_dirty_collections.py"},
    {"event": "SessionStart", "matcher": None, "script": "reindex_dirty_collections.py"},
]
REINDEX_SUPPORT = ["_reindex_common.py"]


def install_claude_md(source: Path, target: Path, dry_run: bool) -> None:
    install_tagged_blocks(source, target, dry_run, "CLAUDE.md")


def install_reindex_hooks(dry_run: bool) -> None:
    """Copy the reindex hook scripts to ~/.claude/hooks and register the events.

    Independent of the Zed adapter: shares only the neutral hook_install helpers, so
    a CC-only user installs these without any Zed code. Idempotent.
    """
    print(f"Install reindex hooks: {REINDEX_HOOKS_SRC} -> {CLAUDE_HOOKS_DIR}")
    if dry_run:
        for hook in REINDEX_HOOKS:
            print(f"  register {hook['event']} -> {hook['script']}")
        return

    CLAUDE_HOOKS_DIR.mkdir(parents=True, exist_ok=True)
    for name in REINDEX_SUPPORT + [h["script"] for h in REINDEX_HOOKS]:
        src = REINDEX_HOOKS_SRC / name
        dest = CLAUDE_HOOKS_DIR / name
        shutil.copy2(src, dest)
        dest.chmod(0o755)

    settings = load_settings()
    for hook in REINDEX_HOOKS:
        dest = CLAUDE_HOOKS_DIR / hook["script"]
        install_hook(settings, hook["event"], dest, hook["matcher"])
    save_settings(settings)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        default=str(DEFAULT_TARGET),
        help="Claude Code skills directory. Defaults to ~/.claude/skills.",
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
    )
    install_plain_skills(REPO_ROOT, manifest, target_root, args.dry_run)
    install_qmd_skill(args.dry_run)
    install_reindex_hooks(args.dry_run)
    install_claude_md(
        ADAPTER_DIR / "CLAUDE.md",
        target_root.parent / "CLAUDE.md",
        args.dry_run,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
