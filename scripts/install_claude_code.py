#!/usr/bin/env python3
"""Install task-memory-bank Claude Code skill wrappers."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    tomllib = None


REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTER_DIR = REPO_ROOT / "adapters" / "claude-code"
DEFAULT_TARGET = Path.home() / ".claude" / "skills"


def load_manifest(path: Path) -> dict:
    if tomllib is None:
        raise SystemExit("Python 3.11+ is required to read wrappers.toml")
    with path.open("rb") as handle:
        return tomllib.load(handle)


def render(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered.rstrip() + "\n"


def copy_canonical_skill(source: Path, target: Path, dry_run: bool) -> None:
    print(f"Install canonical skill: {source} -> {target}")
    if dry_run:
        return
    if not source.exists():
        raise SystemExit(f"Missing canonical skill source: {source}")
    shutil.copytree(source, target, dirs_exist_ok=True)


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

    canonical_name = manifest["canonical_skill"]
    canonical_source = REPO_ROOT / manifest["canonical_skill_source"]
    copy_canonical_skill(canonical_source, target_root / canonical_name, args.dry_run)

    canonical_skill_path = f"{canonical_name}/SKILL.md"
    for wrapper in manifest["wrappers"]:
        install_wrapper(wrapper, template, target_root, canonical_skill_path, args.dry_run)

    return 0


if __name__ == "__main__":
    sys.exit(main())
