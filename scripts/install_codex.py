#!/usr/bin/env python3
"""Install agent-skills into Codex's local skills directory."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

# Re-export subsystem APIs so existing install_codex imports remain valid.
from codex_install_errors import InstallError
from codex_reindex_install import (
    REINDEX_CORE,
    REINDEX_HOOK_ENTRYPOINTS,
    REINDEX_HOOK_SOURCES,
    ReindexHookState,
    _is_managed_reindex_command,
    _iter_hook_handlers,
    _load_reindex_hook_config,
    _reindex_runtime_is_current,
    inspect_reindex_hook_state,
    install_reindex_hooks,
    reindex_hook_specs,
    resolve_hook_consent,
    should_compose_reindex_adapter,
)
from codex_qmd_mcp import (
    QMD_MCP_ARGS,
    QMD_MCP_COMMAND,
    QMD_MCP_READ_TOOLS,
    QmdMcpPlan,
    _atomic_write,
    _parse_codex_config,
    _validate_tool_list,
    apply_qmd_mcp_config,
    prepare_qmd_mcp_config,
    validate_qmd_mcp_server,
)
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
KNOWLEDGE_SKILL_GUIDANCE = ADAPTER_DIR / "knowledge-files.md"
PERMISSION_SKILLS = ("memory-init-project", "memory-doctor", "knowledge-files")
EXIT_CONFIG = 2


def install_agents_md(source: Path, target: Path, dry_run: bool) -> None:
    install_tagged_blocks(source, target, dry_run, "AGENTS.md")


def install_knowledge_skill_guidance(target_root: Path, dry_run: bool) -> None:
    install_tagged_blocks(
        KNOWLEDGE_SKILL_GUIDANCE,
        target_root / "knowledge-files" / "SKILL.md",
        dry_run,
        "knowledge-files skill guidance",
    )


def install_permission_helpers(target_root: Path, dry_run: bool) -> list[Path]:
    targets = [
        target_root / skill / "scripts" / PERMISSION_HELPER.name
        for skill in PERMISSION_SKILLS
    ]
    for target in targets:
        print(f"Install Codex permission helper: {PERMISSION_HELPER} -> {target}")
        if dry_run:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PERMISSION_HELPER, target)
    return targets


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        metavar="SKILLS_DIR",
        default=str(DEFAULT_TARGET),
        help=(
            "Directory where Codex skills are installed; reindex hooks reference "
            "the task-memory-bank script here. Defaults to ~/.agents/skills."
        ),
    )
    parser.add_argument(
        "--skip-qmd",
        action="store_true",
        help="Do not install/check qmd or configure its Codex MCP server.",
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
        metavar="CODEX_HOME",
        default=str(DEFAULT_CODEX_HOME),
        help=(
            "Directory containing Codex config.toml, hooks.json, and managed hook "
            "runtime. Defaults to $CODEX_HOME or ~/.codex."
        ),
    )
    hook_group = parser.add_mutually_exclusive_group()
    hook_group.add_argument(
        "--enable-hooks",
        action="store_true",
        help="Install host-side Codex qmd reindex hooks after explicit consent.",
    )
    hook_group.add_argument(
        "--skip-hooks",
        action="store_true",
        help="Do not install or update Codex qmd reindex hooks; preserve existing state.",
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
    try:
        hook_state = inspect_reindex_hook_state(target_root, codex_home)
        install_hooks = resolve_hook_consent(args, hook_state)
        compose_reindex_adapter = should_compose_reindex_adapter(
            hook_state,
            install_hooks,
            codex_home / "hooks.json",
        )
        qmd_mcp_plan = (
            None
            if args.skip_qmd
            else prepare_qmd_mcp_config(codex_home / "config.toml")
        )
    except InstallError as exc:
        print(f"Cannot install Codex adapter: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    if not args.skip_qmd:
        install_qmd_skill(args.dry_run)
        try:
            assert qmd_mcp_plan is not None
            apply_qmd_mcp_config(qmd_mcp_plan, args.dry_run)
        except InstallError as exc:
            print(f"Cannot install Codex adapter: {exc}", file=sys.stderr)
            return EXIT_CONFIG

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
    if compose_reindex_adapter:
        install_memory_bank_adapter(REPO_ROOT, target_root, args.dry_run)
    install_plain_skills(REPO_ROOT, manifest, target_root, args.dry_run)
    install_knowledge_skill_guidance(target_root, args.dry_run)
    permission_helpers = install_permission_helpers(target_root, args.dry_run)
    if not args.skip_agents:
        install_agents_md(ADAPTER_DIR / "AGENTS.md", agents_target, args.dry_run)
    if install_hooks:
        install_reindex_hooks(target_root, codex_home, args.dry_run)

    print("Codex permission helpers:")
    for helper in permission_helpers:
        print(f"  {helper}")
    print("Memory wrappers automatically check selected bank roots.")
    print(
        "The installed knowledge-files skill automatically checks selected "
        "knowledge or learning collections before each write; use path-bound "
        "`add-roots --collection <name> --expected-root <name> "
        "<approved-path>` only after explicit approval for persistent setup."
    )
    if args.skip_agents:
        print(
            "`--skip-agents` left global Codex AGENTS.md guidance unchanged; "
            "the skill-local knowledge permission preflight was still installed."
        )
    if not args.skip_qmd:
        print(
            "Start a new Codex session and use /mcp to verify qmd exposes "
            "query, get, and multi_get."
        )
    if install_hooks:
        print(
            "Start a new Codex session and use /hooks to review and trust the "
            "installed reindex hooks."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
