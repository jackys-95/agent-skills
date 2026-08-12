#!/usr/bin/env python3
"""Check or backfill Codex writable roots for memory workflows."""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    tomllib = None


EXIT_MISSING = 1
EXIT_UNSUPPORTED = 2
_PROBE_KEY = "__agent_skills_table_probe__"


class ConfigError(ValueError):
    """The config cannot be checked or changed without guessing."""


@dataclasses.dataclass(frozen=True)
class ConfigState:
    model: str
    configured_roots: tuple[str, ...]
    missing_roots: tuple[str, ...]
    profile_name: str | None = None


def normalize_path(value: str | Path) -> str:
    return str(Path(value).expanduser().resolve(strict=False))


def default_config_path(environ: dict[str, str] | os._Environ[str] = os.environ) -> Path:
    user_home = Path(environ.get("HOME", Path.home()))
    codex_home = Path(environ.get("CODEX_HOME", user_home / ".codex"))
    return Path(normalize_path(codex_home)) / "config.toml"


def required_roots(
    memory_root: str | Path,
    knowledge_roots: list[str] | None = None,
    environ: dict[str, str] | os._Environ[str] = os.environ,
) -> tuple[str, ...]:
    user_home = Path(environ.get("HOME", Path.home()))
    cache_home = Path(environ.get("XDG_CACHE_HOME", user_home / ".cache"))
    config_home = Path(environ.get("XDG_CONFIG_HOME", user_home / ".config"))
    candidates = [
        memory_root,
        *(knowledge_roots or []),
        cache_home / "qmd",
        config_home / "qmd",
    ]
    roots: list[str] = []
    for candidate in candidates:
        normalized = normalize_path(candidate)
        if normalized not in roots:
            roots.append(normalized)
    return tuple(roots)


def _parse_toml(text: str, path: Path) -> dict:
    if tomllib is None:
        raise ConfigError("Python 3.11+ is required to parse Codex config.toml")
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Malformed Codex config {path}: {exc}") from exc


def _normalized_enabled_roots(values: dict) -> tuple[str, ...]:
    roots: list[str] = []
    for value, enabled in values.items():
        if not isinstance(value, str) or not isinstance(enabled, bool):
            raise ConfigError("Permission-profile workspace_roots must map paths to booleans")
        if enabled:
            normalized = normalize_path(value)
            if normalized not in roots:
                roots.append(normalized)
    return tuple(roots)


def analyze_config(data: dict, required: tuple[str, ...]) -> ConfigState:
    if "profile" in data:
        raise ConfigError(
            "A selected external config profile may override permission settings; "
            "run this helper against that profile file explicitly"
        )
    has_profiles = "default_permissions" in data or "permissions" in data
    has_legacy = "sandbox_mode" in data or "sandbox_workspace_write" in data
    if has_profiles and has_legacy:
        raise ConfigError(
            "Codex config mixes permission profiles with legacy sandbox settings; "
            "choose one model before backfilling roots"
        )

    if has_profiles:
        selected = data.get("default_permissions")
        permissions = data.get("permissions")
        if not isinstance(selected, str):
            raise ConfigError(
                "Permission-profile config requires a string default_permissions value"
            )
        if selected.startswith(":"):
            raise ConfigError(
                f"Built-in permission profile {selected!r} cannot be extended in place; "
                "select a custom profile first"
            )
        if not isinstance(permissions, dict):
            raise ConfigError(
                "Permission-profile config requires default_permissions and [permissions]"
            )
        profile = permissions.get(selected)
        if not isinstance(profile, dict):
            raise ConfigError(
                f"Selected permission profile {selected!r} is not defined in this config"
            )
        workspace_roots = profile.get("workspace_roots", {})
        if not isinstance(workspace_roots, dict):
            raise ConfigError(
                f"permissions.{selected}.workspace_roots must be a TOML table"
            )
        configured = _normalized_enabled_roots(workspace_roots)
        missing = tuple(root for root in required if root not in configured)
        return ConfigState("profile", configured, missing, selected)

    sandbox_mode = data.get("sandbox_mode")
    if sandbox_mode not in (None, "workspace-write"):
        raise ConfigError(
            f"sandbox_mode is {sandbox_mode!r}; select workspace-write or use "
            "launch-scoped --add-dir grants"
        )
    sandbox = data.get("sandbox_workspace_write", {})
    if not isinstance(sandbox, dict):
        raise ConfigError("sandbox_workspace_write must be a TOML table")
    writable_roots = sandbox.get("writable_roots", [])
    if not isinstance(writable_roots, list) or not all(
        isinstance(root, str) for root in writable_roots
    ):
        raise ConfigError("sandbox_workspace_write.writable_roots must be an array of paths")
    configured_list: list[str] = []
    for root in writable_roots:
        normalized = normalize_path(root)
        if normalized not in configured_list:
            configured_list.append(normalized)
    configured = tuple(configured_list)
    missing = tuple(root for root in required if root not in configured)
    return ConfigState("legacy", configured, missing)


def load_state(path: Path, required: tuple[str, ...]) -> tuple[str, dict, ConfigState]:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    data = _parse_toml(text, path)
    return text, data, analyze_config(data, required)


def _find_probe_path(value: object, path: tuple[str, ...] = ()) -> tuple[str, ...] | None:
    if not isinstance(value, dict):
        return None
    if value.get(_PROBE_KEY) is True:
        return path
    for key, child in value.items():
        found = _find_probe_path(child, (*path, key))
        if found is not None:
            return found
    return None


def _table_headers(text: str) -> list[tuple[tuple[str, ...], int, int]]:
    headers: list[tuple[tuple[str, ...], int, int]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        if re.match(r"^\s*\[(?!\[)", line):
            try:
                parsed = tomllib.loads(f"{line.rstrip()}\n{_PROBE_KEY} = true\n")
            except tomllib.TOMLDecodeError:
                parsed = {}
            path = _find_probe_path(parsed)
            if path is not None:
                headers.append((path, offset, offset + len(line)))
        offset += len(line)
    return headers


def _table_span(text: str, target: tuple[str, ...]) -> tuple[int, int] | None:
    headers = _table_headers(text)
    for index, (path, start, content_start) in enumerate(headers):
        if path == target:
            end = headers[index + 1][1] if index + 1 < len(headers) else len(text)
            return content_start, end
    return None


def _toml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _append_table(text: str, header: str, body: str) -> str:
    base = text.rstrip()
    separator = "\n\n" if base else ""
    return f"{base}{separator}[{header}]\n{body.rstrip()}\n"


def _insert_in_table(text: str, span: tuple[int, int], body: str) -> str:
    _, end = span
    prefix = "" if not text[:end] or text[:end].endswith("\n") else "\n"
    suffix = "\n" if end < len(text) else ""
    return text[:end] + prefix + body.rstrip() + "\n" + suffix + text[end:]


def _find_array_bounds(text: str, start: int) -> tuple[int, int]:
    open_index = -1
    depth = 0
    state = "normal"
    escaped = False
    index = start
    while index < len(text):
        chunk = text[index : index + 3]
        char = text[index]
        if state == "comment":
            if char == "\n":
                state = "normal"
        elif state == "basic":
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                state = "normal"
        elif state == "literal":
            if char == "'":
                state = "normal"
        elif state == "multibasic":
            if chunk == '"""':
                state = "normal"
                index += 2
            elif char == "\\":
                escaped = not escaped
            else:
                escaped = False
        elif state == "multiliteral":
            if chunk == "'''":
                state = "normal"
                index += 2
        else:
            if chunk == '"""':
                state = "multibasic"
                index += 2
            elif chunk == "'''":
                state = "multiliteral"
                index += 2
            elif char == '"':
                state = "basic"
            elif char == "'":
                state = "literal"
            elif char == "#":
                state = "comment"
            elif char == "[":
                if open_index < 0:
                    open_index = index
                depth += 1
            elif char == "]" and open_index >= 0:
                depth -= 1
                if depth == 0:
                    return open_index, index
        index += 1
    raise ConfigError("Could not locate the complete writable_roots array")


def _comment_start(line: str) -> int | None:
    state = "normal"
    escaped = False
    for index, char in enumerate(line):
        if state == "basic":
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                state = "normal"
        elif state == "literal":
            if char == "'":
                state = "normal"
        elif char == '"':
            state = "basic"
        elif char == "'":
            state = "literal"
        elif char == "#":
            return index
    return None


def _assignment_value_start(
    text: str, span: tuple[int, int], key: str
) -> int | None:
    start, end = span
    match = re.search(
        rf"(?m)^[ \t]*{re.escape(key)}[ \t]*=",
        text[start:end],
    )
    if not match:
        return None
    return start + match.end()


def _merge_legacy_roots(text: str, roots: tuple[str, ...]) -> str:
    target = ("sandbox_workspace_write",)
    span = _table_span(text, target)
    rendered = "\n".join(f"  {_toml_quote(root)}," for root in roots)
    if span is None:
        return _append_table(
            text,
            "sandbox_workspace_write",
            f"writable_roots = [\n{rendered}\n]",
        )

    value_start = _assignment_value_start(text, span, "writable_roots")
    if value_start is None:
        return _insert_in_table(
            text,
            span,
            f"writable_roots = [\n{rendered}\n]",
        )

    open_index, close_index = _find_array_bounds(text, value_start)
    if "\n" not in text[open_index:close_index]:
        existing = text[open_index + 1 : close_index].strip()
        separator = ", " if existing else ""
        addition = separator + ", ".join(_toml_quote(root) for root in roots)
        return text[:close_index] + addition + text[close_index:]

    close_line_start = text.rfind("\n", open_index, close_index) + 1
    if text[close_line_start:close_index].strip():
        raise ConfigError(
            "Unsupported writable_roots formatting; put the closing ] on its own line"
        )
    previous_line_end = close_line_start - 1
    previous_line_start = text.rfind("\n", open_index, previous_line_end) + 1
    previous_line = text[previous_line_start:previous_line_end]
    comment_start = _comment_start(previous_line)
    value_part = (
        previous_line
        if comment_start is None
        else previous_line[:comment_start]
    )
    value_end = previous_line_start + len(value_part.rstrip())
    if value_end > open_index and text[value_end - 1] != ",":
        text = text[:value_end] + "," + text[value_end:]
        close_line_start += 1
    element_indent = re.match(r"[ \t]*", text[close_line_start:]).group(0) + "  "
    addition = "".join(f"{element_indent}{_toml_quote(root)},\n" for root in roots)
    return text[:close_line_start] + addition + text[close_line_start:]


def _insert_top_level_workspace_mode(text: str) -> str:
    headers = _table_headers(text)
    position = headers[0][1] if headers else len(text)
    before = text[:position].rstrip()
    after = text[position:]
    separator = "\n" if before else ""
    trailing = "\n\n" if after else "\n"
    return f"{before}{separator}sandbox_mode = \"workspace-write\"{trailing}{after}"


def _profile_header(profile_name: str) -> str:
    return f"permissions.{_toml_quote(profile_name)}.workspace_roots"


def _merge_profile_roots(
    text: str, profile_name: str, roots: tuple[str, ...]
) -> str:
    target = ("permissions", profile_name, "workspace_roots")
    span = _table_span(text, target)
    body = "\n".join(f"{_toml_quote(root)} = true" for root in roots)
    if span is None:
        return _append_table(text, _profile_header(profile_name), body)

    # An exact false entry can be safely enabled in place. Semantically equivalent
    # aliases (for example ~/x versus /home/u/x) are retained and an absolute key is
    # added instead.
    start, end = span
    section = text[start:end]
    remaining: list[str] = []
    for root in roots:
        quoted = re.escape(_toml_quote(root))
        match = re.search(
            rf"(?m)^([ \t]*{quoted}[ \t]*=[ \t]*)(false)([ \t]*(?:#.*)?)$",
            section,
        )
        if match:
            section = section[: match.start(2)] + "true" + section[match.end(2) :]
        else:
            remaining.append(root)
    text = text[:start] + section + text[end:]
    if not remaining:
        return text
    span = _table_span(text, target)
    body = "\n".join(f"{_toml_quote(root)} = true" for root in remaining)
    return _insert_in_table(text, span, body)


def render_backfill(
    text: str,
    data: dict,
    state: ConfigState,
) -> str:
    if not state.missing_roots:
        return text
    if state.model == "profile":
        updated = _merge_profile_roots(
            text, state.profile_name or "", state.missing_roots
        )
    else:
        updated = _merge_legacy_roots(text, state.missing_roots)
        if "sandbox_mode" not in data:
            updated = _insert_top_level_workspace_mode(updated)
    return updated


def _backup_path(path: Path) -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = path.with_name(f"{path.name}.bak-{stamp}")
    suffix = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.bak-{stamp}-{suffix}")
        suffix += 1
    return candidate


def _atomic_write(path: Path, text: str) -> Path | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    mode = None
    if path.exists():
        backup = _backup_path(path)
        shutil.copy2(path, backup)
        mode = path.stat().st_mode
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
    return backup


def backfill_config(path: Path, required: tuple[str, ...]) -> tuple[bool, Path | None]:
    text, data, state = load_state(path, required)
    if not state.missing_roots:
        return False, None
    updated = render_backfill(text, data, state)
    parsed = _parse_toml(updated, path)
    verified = analyze_config(parsed, required)
    if verified.missing_roots:
        raise ConfigError(
            "Generated config did not contain every requested writable root"
        )
    backup = _atomic_write(path, updated)
    return True, backup


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("check", "backfill"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--memory-root", required=True)
        subparser.add_argument("--knowledge-root", action="append", default=[])
        subparser.add_argument(
            "--config",
            help="Codex config path. Defaults to $CODEX_HOME/config.toml.",
        )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    config_path = (
        Path(normalize_path(args.config)) if args.config else default_config_path()
    )
    roots = required_roots(args.memory_root, args.knowledge_root)
    print("Required writable roots:")
    for root in roots:
        print(f"  {root}")
    print(f"Codex config: {config_path}")

    try:
        _, _, state = load_state(config_path, roots)
        if args.command == "check":
            if state.missing_roots:
                print("Missing writable roots:")
                for root in state.missing_roots:
                    print(f"  {root}")
                return EXIT_MISSING
            print("Configured roots include every requested path.")
            print("Use /status in the active Codex session to verify effective roots.")
            return 0

        changed, backup = backfill_config(config_path, roots)
        if not changed:
            print("No config change needed.")
        else:
            print("Backfilled Codex writable roots.")
            if backup:
                print(f"Backup: {backup}")
            print("Restart Codex, then use /status to verify effective roots.")
        return 0
    except ConfigError as exc:
        print(f"Cannot update permissions: {exc}", file=sys.stderr)
        return EXIT_UNSUPPORTED


if __name__ == "__main__":
    sys.exit(main())
