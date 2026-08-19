"""Validate, plan, and atomically install Codex qmd MCP configuration."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from codex_install_errors import InstallError

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    tomllib = None


QMD_MCP_COMMAND = "qmd"
QMD_MCP_ARGS = ("mcp",)
QMD_MCP_READ_TOOLS = frozenset({"query", "get", "multi_get"})


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
