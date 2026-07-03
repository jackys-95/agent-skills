#!/usr/bin/env python3
"""Install task-memory-bank Claude Code skill wrappers."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Adapter-neutral hook-registration helpers (same scripts/ dir).
from hook_install import install_hook, load_settings, save_settings

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    tomllib = None


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


def load_manifest(path: Path) -> dict:
    if tomllib is None:
        raise SystemExit("Python 3.11+ is required to read wrappers.toml")
    with path.open("rb") as handle:
        return tomllib.load(handle)


def copy_skill(skill_type: str, source: Path, target: Path, dry_run: bool) -> None:
    print(f"Install {skill_type} skill: {source} -> {target}")
    if dry_run:
        return
    try:
        shutil.copytree(source, target, dirs_exist_ok=True, copy_function=shutil.copy)
    except FileNotFoundError:
        raise SystemExit(f"Missing {skill_type} skill source: {source}")


def render(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered.rstrip() + "\n"


def install_canonical_skills(
    manifest: dict,
    template: str,
    target_root: Path,
    dry_run: bool,
) -> None:
    canonical_name = manifest["canonical_skill"]
    canonical_source = REPO_ROOT / manifest["canonical_skill_source"]
    copy_skill("canonical", canonical_source, target_root / canonical_name, dry_run)

    canonical_skill_path = f"{canonical_name}/SKILL.md"
    for wrapper in manifest["wrappers"]:
        install_wrapper(wrapper, template, target_root, canonical_skill_path, dry_run)


def install_wrapper(
    wrapper: dict[str, str],
    template: str,
    target_root: Path,
    canonical_skill_path: str,
    dry_run: bool,
) -> None:
    name = wrapper["name"]
    target = target_root / name / "SKILL.md"
    values = {
        "name": name,
        "description": wrapper["description"],
        "argument_hint": wrapper["argument_hint"],
        "workflow": wrapper["workflow"],
        "body": wrapper["body"],
        "canonical_skill_path": canonical_skill_path,
    }
    content = render(template, values)
    print(f"Install wrapper: {target}")
    if dry_run:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def install_claude_md(source: Path, target: Path, dry_run: bool) -> None:
    """Upsert tagged blocks from source into target, preserving surrounding content."""
    source_text = source.read_text(encoding="utf-8")
    block_re = re.compile(r"(<!-- (\S+) -->.*?<!-- \2 -->)", re.DOTALL)
    blocks = block_re.findall(source_text)
    if not blocks:
        return

    target_text = target.read_text(encoding="utf-8") if target.exists() else ""
    for block_content, tag in blocks:
        existing = re.compile(
            r"<!-- " + re.escape(tag) + r" -->.*?<!-- " + re.escape(tag) + r" -->",
            re.DOTALL,
        )
        if existing.search(target_text):
            target_text = existing.sub(block_content, target_text)
        else:
            target_text = target_text.rstrip("\n") + "\n\n" + block_content + "\n"

    print(f"Install CLAUDE.md blocks: {target}")
    if dry_run:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(target_text, encoding="utf-8")


def install_qmd_skill(dry_run: bool) -> None:
    qmd = shutil.which("qmd")
    if not qmd:
        pm = "bun" if shutil.which("bun") else "npm"
        print(f"qmd not found — installing via {pm}...")
        if not dry_run:
            subprocess.run([pm, "install", "-g", "@tobilu/qmd"], check=True)
    cmd = ["qmd", "skill", "install", "--global", "--yes"]
    print(f"Install qmd skill: {' '.join(cmd)}")
    if not dry_run:
        # `qmd skill install` exits non-zero when the skill already exists (idempotent
        # re-run). That is not a failure worth aborting the whole install for — and
        # aborting here would skip everything after (e.g. the reindex hooks). Report
        # the outcome instead of raising.
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print("  (qmd skill already installed or install skipped — continuing)")


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

    install_canonical_skills(manifest, template, target_root, args.dry_run)
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
