#!/usr/bin/env python3
"""Install agent-skills into Codex's local skills directory."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from install_common import (
    install_canonical_skills,
    install_plain_skills,
    install_qmd_skill,
    install_tagged_blocks,
    load_manifest,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTER_DIR = REPO_ROOT / "adapters" / "codex"
DEFAULT_TARGET = Path.home() / ".agents" / "skills"
DEFAULT_AGENTS_TARGET = Path.home() / ".codex" / "AGENTS.md"


def install_agents_md(source: Path, target: Path, dry_run: bool) -> None:
    install_tagged_blocks(source, target, dry_run, "AGENTS.md")


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
        "--dry-run",
        action="store_true",
        help="Print planned installs without writing files.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    target_root = Path(args.target).expanduser().resolve()
    agents_target = Path(args.agents_target).expanduser().resolve()
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
    install_plain_skills(REPO_ROOT, manifest, target_root, args.dry_run)
    if not args.skip_qmd:
        install_qmd_skill(args.dry_run)
    if not args.skip_agents:
        install_agents_md(ADAPTER_DIR / "AGENTS.md", agents_target, args.dry_run)

    print("Codex reindex hooks are not installed yet; use $memory-reindex as needed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
