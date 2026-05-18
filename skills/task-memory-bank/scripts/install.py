#!/usr/bin/env python3
"""Install task-memory-bank skill variants for agent harnesses."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


SKIP_NAMES = {
    ".DS_Store",
    "__pycache__",
}
SKIP_DIRS = {
    "adapters",
}


def expand(path: str) -> Path:
    return Path(path).expanduser().resolve()


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def should_skip(path: Path) -> bool:
    return path.name in SKIP_NAMES or path.suffix == ".pyc"


def copy_skill_tree(source: Path, target: Path, clean: bool) -> None:
    if clean and target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    for path in source.rglob("*"):
        rel = path.relative_to(source)
        if any(part in SKIP_DIRS for part in rel.parts[:-1]):
            continue
        if path.is_dir() and path.name in SKIP_DIRS:
            continue
        if any(should_skip(part) for part in path.parents) or should_skip(path):
            continue
        dest = target / rel
        if path.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)


def write_composed_skill(target: Path, appendix: Path) -> None:
    base = skill_root() / "SKILL.md"
    base_text = base.read_text(encoding="utf-8").rstrip()
    appendix_text = appendix.read_text(encoding="utf-8").rstrip()
    (target / "SKILL.md").write_text(
        base_text + "\n\n---\n\n" + appendix_text + "\n",
        encoding="utf-8",
    )


def install_codex_app(args: argparse.Namespace) -> None:
    source = skill_root()
    target = expand(args.target)
    copy_skill_tree(source, target, clean=args.clean)
    write_composed_skill(target, source / "adapters" / "codex-app.md")
    print(f"Installed Codex app task-memory-bank skill: {target}")
    print("Composed SKILL.md from base skill plus adapters/codex-app.md")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("codex-app", help="Install the Codex app skill variant")
    p.add_argument(
        "--target",
        default="~/.agents/skills/task-memory-bank",
        help="Skill install target",
    )
    p.add_argument(
        "--clean",
        action="store_true",
        help="Remove the target directory before installing",
    )
    p.set_defaults(func=install_codex_app)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
