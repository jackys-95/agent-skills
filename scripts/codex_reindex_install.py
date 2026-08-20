"""Inspect and install Codex qmd reindex hooks."""

from __future__ import annotations

import argparse
import shlex
import shutil
import sys
from enum import Enum
from pathlib import Path

from codex_hook_install import (
    DEFAULT_HOOK_TIMEOUT,
    install_hook,
    load_config,
    save_config,
)
from codex_install_errors import InstallError


_REPO_ROOT = Path(__file__).resolve().parents[1]
_ADAPTER_DIR = _REPO_ROOT / "adapters" / "codex"
REINDEX_CORE = _REPO_ROOT / "adapters" / "core"
REINDEX_HOOK_SOURCES = (
    REINDEX_CORE / "_codex_patch.py",
    _ADAPTER_DIR / "hooks" / "post_apply_patch_mark_dirty.py",
    REINDEX_CORE / "reindex_dirty_collections.py",
    REINDEX_CORE / "reindex_state.py",
)
REINDEX_HOOK_ENTRYPOINTS = frozenset(
    {"post_apply_patch_mark_dirty.py", "reindex_dirty_collections.py"}
)


class ReindexHookState(Enum):
    ABSENT = "absent"
    PARTIAL = "partial"
    COMPLETE = "complete"
    CONFLICTING = "conflicting"


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


def reindex_hook_specs(install_dir: Path, target_root: Path) -> tuple[dict, ...]:
    def command(name: str, *args: str) -> str:
        parts = ["python3", str(install_dir / name), *args]
        return " ".join(shlex.quote(part) for part in parts)

    memory_bank = target_root / "task-memory-bank" / "scripts" / "memory_bank.py"
    flush = ("--memory-bank", str(memory_bank))
    return (
        {
            "event": "PostToolUse",
            # Tool matcher: matches only "apply_patch"; does not match
            # "functions.apply_patch" or "apply_patch_file".
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
            # Session matcher: matches exactly "startup", "resume", or "clear";
            # it does not match "compact" or "startup-extra".
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
