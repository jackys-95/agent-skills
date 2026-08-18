#!/usr/bin/env python3
"""Install agent-skills into Codex's local skills directory."""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from codex_hook_install import (
    DEFAULT_HOOK_TIMEOUT,
    install_hook,
    load_config,
    save_config,
)
from install_common import (
    install_canonical_skills,
    install_memory_bank_adapter,
    install_plain_skills,
    install_qmd_skill,
    install_tagged_blocks,
    load_manifest,
)

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    tomllib = None


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
REINDEX_HOOK_ENTRYPOINTS = frozenset(
    {"post_apply_patch_mark_dirty.py", "reindex_dirty_collections.py"}
)
QMD_MCP_COMMAND = "qmd"
QMD_MCP_ARGS = ("mcp",)
QMD_MCP_READ_TOOLS = frozenset({"query", "get", "multi_get"})
EXIT_CONFIG = 2


class InstallError(ValueError):
    """The adapter cannot be installed safely with the supplied configuration."""


class ReindexHookState(Enum):
    ABSENT = "absent"
    PARTIAL = "partial"
    COMPLETE = "complete"
    CONFLICTING = "conflicting"


@dataclass(frozen=True)
class QmdMcpPlan:
    config_path: Path
    original: str
    updated: str

    @property
    def changed(self) -> bool:
        return self.original != self.updated


def _parse_codex_config(text: str, path: Path) -> dict:
    if tomllib is None:
        raise InstallError("Python 3.11+ is required to parse Codex config.toml")
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise InstallError(f"Malformed Codex config {path}: {exc}") from exc


def _validate_tool_list(server: dict, key: str) -> set[str] | None:
    value = server.get(key)
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise InstallError(f"mcp_servers.qmd.{key} must be an array of tool names")
    return set(value)


def validate_qmd_mcp_server(server: object) -> None:
    if not isinstance(server, dict):
        raise InstallError("mcp_servers.qmd must be a TOML table")

    command = server.get("command")
    url = server.get("url")
    if url is not None:
        if command is not None or "args" in server:
            raise InstallError(
                "mcp_servers.qmd mixes STDIO and streamable HTTP settings"
            )
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            raise InstallError("mcp_servers.qmd.url must be an HTTP(S) URL")
    else:
        executable = Path(command).name.lower() if isinstance(command, str) else ""
        if executable not in {"qmd", "qmd.cmd", "qmd.exe"}:
            raise InstallError(
                "mcp_servers.qmd already exists with a different command; "
                'expected command = "qmd"'
            )

        args = server.get("args")
        if args != list(QMD_MCP_ARGS):
            raise InstallError(
                "mcp_servers.qmd already exists with different arguments; "
                'expected args = ["mcp"]'
            )
    enabled = server.get("enabled")
    if enabled is not None and not isinstance(enabled, bool):
        raise InstallError("mcp_servers.qmd.enabled must be a boolean")
    if enabled is False:
        raise InstallError(
            "mcp_servers.qmd is disabled; enable it or use --skip-qmd"
        )

    enabled_tools = _validate_tool_list(server, "enabled_tools")
    if enabled_tools is not None:
        missing = sorted(QMD_MCP_READ_TOOLS - enabled_tools)
        if missing:
            raise InstallError(
                "mcp_servers.qmd.enabled_tools omits required read tools: "
                + ", ".join(missing)
            )
    disabled_tools = _validate_tool_list(server, "disabled_tools")
    blocked = sorted(QMD_MCP_READ_TOOLS & (disabled_tools or set()))
    if blocked:
        raise InstallError(
            "mcp_servers.qmd.disabled_tools blocks required read tools: "
            + ", ".join(blocked)
        )


def prepare_qmd_mcp_config(config_path: Path) -> QmdMcpPlan:
    original = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    data = _parse_codex_config(original, config_path)
    servers = data.get("mcp_servers")
    if servers is not None and not isinstance(servers, dict):
        raise InstallError("mcp_servers must be a TOML table")

    existing = (servers or {}).get("qmd")
    if existing is not None:
        validate_qmd_mcp_server(existing)
        return QmdMcpPlan(config_path, original, original)

    if not original or original.endswith("\n\n"):
        prefix = original
    elif original.endswith("\n"):
        prefix = original + "\n"
    else:
        prefix = original + "\n\n"
    updated = (
        f"{prefix}[mcp_servers.qmd]\n"
        f'command = "{QMD_MCP_COMMAND}"\n'
        'args = ["mcp"]\n'
    )
    updated_data = _parse_codex_config(updated, config_path)
    validate_qmd_mcp_server(updated_data["mcp_servers"]["qmd"])
    return QmdMcpPlan(config_path, original, updated)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode if path.exists() else None
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    temp_path = Path(handle.name)
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def apply_qmd_mcp_config(plan: QmdMcpPlan, dry_run: bool) -> None:
    if not dry_run:
        current = (
            plan.config_path.read_text(encoding="utf-8")
            if plan.config_path.exists()
            else ""
        )
        if current != plan.original:
            plan = prepare_qmd_mcp_config(plan.config_path)
    if not plan.changed:
        print(f"Verified Codex qmd MCP config: {plan.config_path}")
        return
    print(f"Configure Codex qmd MCP: {plan.config_path}")
    if not dry_run:
        _atomic_write(plan.config_path, plan.updated)


def resolve_hook_consent(
    args: argparse.Namespace,
    hook_state: ReindexHookState = ReindexHookState.ABSENT,
    stdin=None,
    stdout=None,
) -> bool:
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    if args.enable_hooks:
        print("Codex qmd reindex hooks: explicitly enabled.", file=stdout)
        return True
    if args.skip_hooks:
        print("Codex qmd reindex hook installation: explicitly skipped.", file=stdout)
        return False
    if args.dry_run:
        print(
            "Codex qmd reindex hooks: no consent supplied; "
            "dry-run plans no hook installation.",
            file=stdout,
        )
        return False
    if not stdin.isatty():
        raise InstallError(
            "Non-interactive installs must choose --enable-hooks or --skip-hooks"
        )

    if hook_state is ReindexHookState.COMPLETE:
        print(
            "\nA complete matching Codex qmd reindex hook installation already "
            "exists. Declining leaves it unchanged.",
            file=stdout,
        )
    elif hook_state is ReindexHookState.PARTIAL:
        print(
            "\nA partial Codex qmd reindex hook installation exists. Accepting "
            "repairs it; declining aborts before installation writes.",
            file=stdout,
        )
    print(
        "\nCodex qmd reindex hooks mark changed collections, then run `qmd update` "
        "and collection-scoped `qmd embed` at settled lifecycle boundaries.",
        file=stdout,
    )
    print(
        "After separate review and trust in /hooks, current Codex builds execute "
        "these commands with your host user permissions, outside the spawned-command "
        "sandbox.",
        file=stdout,
    )
    while True:
        print("Install or update these hooks? [y/N] ", end="", file=stdout, flush=True)
        answer = stdin.readline()
        if answer == "" or answer.strip().lower() in {"", "n", "no"}:
            print("Codex qmd reindex hook installation: declined.", file=stdout)
            return False
        if answer.strip().lower() in {"y", "yes"}:
            print("Codex qmd reindex hooks: accepted.", file=stdout)
            return True
        print("Please answer yes or no.", file=stdout)


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


def _load_reindex_hook_config(config_path: Path) -> dict:
    try:
        return load_config(config_path)
    except SystemExit as exc:
        raise InstallError(str(exc)) from exc


def _iter_hook_handlers(config: dict):
    hooks = config.get("hooks", {})
    if not isinstance(hooks, dict):
        raise InstallError("Codex hooks.json field 'hooks' must be an object")
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            raise InstallError(f"Codex hooks.json event {event!r} must be an array")
        for group in groups:
            if not isinstance(group, dict):
                raise InstallError(
                    f"Codex hooks.json event {event!r} contains a non-object group"
                )
            matcher = group.get("matcher")
            if matcher is not None and not isinstance(matcher, str):
                raise InstallError(
                    f"Codex hooks.json event {event!r} matcher must be a string"
                )
            handlers = group.get("hooks", [])
            if not isinstance(handlers, list):
                raise InstallError(
                    f"Codex hooks.json event {event!r} group hooks must be an array"
                )
            for handler in handlers:
                if not isinstance(handler, dict):
                    raise InstallError(
                        f"Codex hooks.json event {event!r} contains "
                        "a non-object handler"
                    )
                yield event, matcher, handler


def _is_managed_reindex_command(command: object, install_dir: Path) -> bool:
    if not isinstance(command, str):
        return False
    managed_paths = {
        (install_dir / name).resolve() for name in REINDEX_HOOK_ENTRYPOINTS
    }
    try:
        parts = shlex.split(command)
    except ValueError:
        return any(str(path) in command for path in managed_paths)
    for part in parts[1:]:
        candidate = Path(part).expanduser()
        if candidate.name not in REINDEX_HOOK_ENTRYPOINTS:
            continue
        if candidate.resolve() in managed_paths:
            return True
    return False


def _reindex_runtime_is_current(install_dir: Path) -> bool:
    for source in REINDEX_HOOK_SOURCES:
        target = install_dir / source.name
        try:
            if target.read_bytes() != source.read_bytes():
                return False
        except OSError:
            return False
    return True


def inspect_reindex_hook_state(
    target_root: Path,
    codex_home: Path,
) -> ReindexHookState:
    target_root = target_root.expanduser().resolve()
    codex_home = codex_home.expanduser().resolve()
    install_dir = codex_home / "hooks" / "agent-skills"
    config = _load_reindex_hook_config(codex_home / "hooks.json")
    expected = {
        (spec["event"], spec.get("matcher"), spec["command"]): spec.get(
            "timeout", DEFAULT_HOOK_TIMEOUT
        )
        for spec in reindex_hook_specs(install_dir, target_root)
    }
    expected_keys = set(expected)
    found = set()
    managed = []
    for event, matcher, handler in _iter_hook_handlers(config):
        command = handler.get("command")
        if not _is_managed_reindex_command(command, install_dir):
            continue
        key = (event, matcher, command)
        managed.append(key)
        if (
            handler.get("type") == "command"
            and key in expected
            and handler.get("timeout", DEFAULT_HOOK_TIMEOUT) == expected[key]
        ):
            found.add(key)

    if not managed:
        return ReindexHookState.ABSENT
    if len(managed) != len(set(managed)) or any(
        key not in expected_keys for key in managed
    ):
        return ReindexHookState.CONFLICTING
    if found == expected_keys and _reindex_runtime_is_current(install_dir):
        return ReindexHookState.COMPLETE
    return ReindexHookState.PARTIAL


def should_compose_reindex_adapter(
    state: ReindexHookState,
    install_hooks: bool,
    config_path: Path,
) -> bool:
    if state is ReindexHookState.CONFLICTING:
        raise InstallError(
            "Codex qmd reindex hooks contain managed commands that conflict "
            f"with this target; inspect {config_path}"
        )
    if install_hooks:
        if state is ReindexHookState.PARTIAL:
            print("Repair partial Codex qmd reindex hook installation.")
        return True
    if state is ReindexHookState.PARTIAL:
        raise InstallError(
            "Codex qmd reindex hook installation is partial; "
            "rerun with --enable-hooks to repair it"
        )
    if state is ReindexHookState.COMPLETE:
        print(
            "Preserve existing Codex qmd reindex hooks and compose their "
            "memory-bank adapter."
        )
        return True
    print("No existing Codex qmd reindex hooks; use the canonical memory-bank script.")
    return False


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
    permission_helpers = install_permission_helpers(target_root, args.dry_run)
    if not args.skip_agents:
        install_agents_md(ADAPTER_DIR / "AGENTS.md", agents_target, args.dry_run)
    if install_hooks:
        install_reindex_hooks(target_root, codex_home, args.dry_run)

    print("Codex permission helpers:")
    for helper in permission_helpers:
        print(f"  {helper}")
    print(
        "For each external memory or knowledge root, run the installed helper "
        "with `check` once during setup; use explicit `backfill` only when "
        "persistent config repair is wanted."
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
