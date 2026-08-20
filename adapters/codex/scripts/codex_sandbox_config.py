"""Analyze and update persistent Codex sandbox access configuration."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    tomllib = None


_PROBE_KEY = "__agent_skills_table_probe__"


class CodexSandboxConfigError(ValueError):
    """Codex sandbox config cannot be checked or changed without guessing."""


@dataclasses.dataclass(frozen=True)
class CodexSandboxConfigState:
    """Configured and missing paths under one supported Codex config model."""

    model: str
    configured_paths: tuple[str, ...]
    missing_paths: tuple[str, ...]
    profile_name: str | None = None


def normalize_path(value: str | Path) -> str:
    raw = os.fspath(value)
    if not raw.strip():
        raise CodexSandboxConfigError(
            "Path values must not be empty or whitespace-only"
        )
    return str(Path(raw).expanduser().resolve(strict=False))


def default_config_path(
    environ: dict[str, str] | os._Environ[str] = os.environ,
) -> Path:
    user_home = Path(environ.get("HOME", Path.home()))
    codex_home = Path(environ.get("CODEX_HOME", user_home / ".codex"))
    return Path(normalize_path(codex_home)) / "config.toml"


def required_sandbox_paths(
    memory_path: str | Path | None = None,
    knowledge_paths: list[str] | None = None,
    environ: dict[str, str] | os._Environ[str] = os.environ,
    *,
    include_qmd_state: bool | None = None,
) -> tuple[str, ...]:
    """Return exact paths needed for one Codex sandbox operation.

    Memory operations include qmd state by default. Existing knowledge
    operations omit it; pre-registration callers opt in explicitly.
    """
    user_home = Path(environ.get("HOME", Path.home()))
    cache_home = Path(environ.get("XDG_CACHE_HOME", user_home / ".cache"))
    config_home = Path(environ.get("XDG_CONFIG_HOME", user_home / ".config"))
    if include_qmd_state is None:
        include_qmd_state = memory_path is not None
    candidates: list[str | Path] = []
    if memory_path is not None:
        candidates.append(memory_path)
    candidates.extend(knowledge_paths or [])
    if include_qmd_state:
        candidates.extend((cache_home / "qmd", config_home / "qmd"))
    paths: list[str] = []
    for candidate in candidates:
        normalized = normalize_path(candidate)
        if normalized not in paths:
            paths.append(normalized)
    return tuple(paths)


def _parse_toml(text: str, path: Path) -> dict:
    if tomllib is None:
        raise CodexSandboxConfigError(
            "Python 3.11+ is required to parse Codex config.toml"
        )
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise CodexSandboxConfigError(
            f"Malformed Codex config {path}: {exc}"
        ) from exc


def _normalized_enabled_paths(values: dict) -> tuple[str, ...]:
    paths: list[str] = []
    for value, enabled in values.items():
        if not isinstance(value, str) or not isinstance(enabled, bool):
            raise CodexSandboxConfigError(
                "Permission-profile workspace_roots must map paths to booleans"
            )
        if enabled:
            normalized = normalize_path(value)
            if normalized not in paths:
                paths.append(normalized)
    return tuple(paths)


def _missing_required_paths(
    configured: tuple[str, ...],
    required: tuple[str, ...],
) -> tuple[str, ...]:
    """Return required paths not covered by a configured ancestor."""
    configured_paths = tuple(Path(path) for path in configured)
    return tuple(
        path
        for path in required
        if not any(Path(path).is_relative_to(grant) for grant in configured_paths)
    )


def analyze_sandbox_config(
    data: dict,
    required: tuple[str, ...],
) -> CodexSandboxConfigState:
    """Validate one Codex config model and calculate missing sandbox paths."""
    if "profile" in data:
        raise CodexSandboxConfigError(
            "A selected external config profile may override permission settings; "
            "run this helper against that profile file explicitly"
        )
    has_profiles = "default_permissions" in data or "permissions" in data
    has_legacy = "sandbox_mode" in data or "sandbox_workspace_write" in data
    if has_profiles and has_legacy:
        raise CodexSandboxConfigError(
            "Codex config mixes permission profiles with legacy sandbox settings; "
            "choose one model before adding sandbox paths"
        )

    if has_profiles:
        selected = data.get("default_permissions")
        permissions = data.get("permissions")
        if not isinstance(selected, str):
            raise CodexSandboxConfigError(
                "Permission-profile config requires a string "
                "default_permissions value"
            )
        if selected.startswith(":"):
            raise CodexSandboxConfigError(
                f"Built-in permission profile {selected!r} cannot be extended "
                "in place; select a custom profile first"
            )
        if not isinstance(permissions, dict):
            raise CodexSandboxConfigError(
                "Permission-profile config requires default_permissions and "
                "[permissions]"
            )
        profile = permissions.get(selected)
        if not isinstance(profile, dict):
            raise CodexSandboxConfigError(
                f"Selected permission profile {selected!r} is not defined in "
                "this config"
            )
        workspace_roots = profile.get("workspace_roots", {})
        if not isinstance(workspace_roots, dict):
            raise CodexSandboxConfigError(
                f"permissions.{selected}.workspace_roots must be a TOML table"
            )
        configured = _normalized_enabled_paths(workspace_roots)
        missing = _missing_required_paths(configured, required)
        return CodexSandboxConfigState(
            "profile",
            configured,
            missing,
            selected,
        )

    sandbox_mode = data.get("sandbox_mode")
    if sandbox_mode not in (None, "workspace-write"):
        raise CodexSandboxConfigError(
            f"sandbox_mode is {sandbox_mode!r}; select workspace-write or use "
            "launch-scoped --add-dir grants"
        )
    sandbox = data.get("sandbox_workspace_write", {})
    if not isinstance(sandbox, dict):
        raise CodexSandboxConfigError(
            "sandbox_workspace_write must be a TOML table"
        )
    writable_roots = sandbox.get("writable_roots", [])
    if not isinstance(writable_roots, list) or not all(
        isinstance(path, str) for path in writable_roots
    ):
        raise CodexSandboxConfigError(
            "sandbox_workspace_write.writable_roots must be an array of paths"
        )
    configured_list: list[str] = []
    for path in writable_roots:
        normalized = normalize_path(path)
        if normalized not in configured_list:
            configured_list.append(normalized)
    configured = tuple(configured_list)
    missing = _missing_required_paths(configured, required)
    return CodexSandboxConfigState("legacy", configured, missing)


def load_sandbox_config_state(
    path: Path,
    required: tuple[str, ...],
) -> tuple[str, dict, CodexSandboxConfigState]:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    data = _parse_toml(text, path)
    return text, data, analyze_sandbox_config(data, required)


def _find_probe_path(
    value: object,
    path: tuple[str, ...] = (),
) -> tuple[str, ...] | None:
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
    """Locate TOML table headers and parse their exact dotted or quoted paths."""
    headers: list[tuple[tuple[str, ...], int, int]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        # A candidate table header starts with optional whitespace and one `[`.
        # Matches: "[sandbox_workspace_write]" and '  [permissions."main"]'
        # Does not match: "[[servers]]" or 'sandbox_mode = "workspace-write"'
        if re.match(r"^\s*\[(?!\[)", line):
            try:
                parsed = tomllib.loads(
                    f"{line.rstrip()}\n{_PROBE_KEY} = true\n"
                )
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
    """Find one complete TOML array while ignoring brackets in strings/comments."""
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
    raise CodexSandboxConfigError(
        "Could not locate the complete writable_roots array"
    )


def _comment_start(line: str) -> int | None:
    """Return the first TOML comment marker outside basic/literal strings."""
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
    text: str,
    span: tuple[int, int],
    key: str,
) -> int | None:
    start, end = span
    # Find an assignment to the exact key at the beginning of a table line.
    # Matches: "writable_roots = [" and "  writable_roots=["
    # Does not match: "# writable_roots = [" or "other_writable_roots = ["
    match = re.search(
        rf"(?m)^[ \t]*{re.escape(key)}[ \t]*=",
        text[start:end],
    )
    if not match:
        return None
    return start + match.end()


def _merge_legacy_paths(text: str, paths: tuple[str, ...]) -> str:
    target = ("sandbox_workspace_write",)
    span = _table_span(text, target)
    rendered = "\n".join(f"  {_toml_quote(path)}," for path in paths)
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
        addition = separator + ", ".join(_toml_quote(path) for path in paths)
        return text[:close_index] + addition + text[close_index:]

    close_line_start = text.rfind("\n", open_index, close_index) + 1
    if text[close_line_start:close_index].strip():
        raise CodexSandboxConfigError(
            "Unsupported writable_roots formatting; put the closing ] on its "
            "own line"
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
    closing_line = text[close_line_start:]
    indent_length = len(closing_line) - len(closing_line.lstrip(" \t"))
    closing_indent = closing_line[:indent_length]
    element_indent = closing_indent + "  "
    addition = "".join(
        f"{element_indent}{_toml_quote(path)},\n" for path in paths
    )
    return text[:close_line_start] + addition + text[close_line_start:]


def _insert_top_level_workspace_mode(text: str) -> str:
    headers = _table_headers(text)
    position = headers[0][1] if headers else len(text)
    before = text[:position].rstrip()
    after = text[position:]
    separator = "\n" if before else ""
    trailing = "\n\n" if after else "\n"
    return (
        f'{before}{separator}sandbox_mode = "workspace-write"'
        f"{trailing}{after}"
    )


def _profile_header(profile_name: str) -> str:
    return f"permissions.{_toml_quote(profile_name)}.workspace_roots"


def _merge_profile_paths(
    text: str,
    profile_name: str,
    paths: tuple[str, ...],
) -> str:
    target = ("permissions", profile_name, "workspace_roots")
    span = _table_span(text, target)
    body = "\n".join(f"{_toml_quote(path)} = true" for path in paths)
    if span is None:
        return _append_table(text, _profile_header(profile_name), body)

    start, end = span
    section = text[start:end]
    remaining: list[str] = []
    for path in paths:
        quoted = re.escape(_toml_quote(path))
        # Match one exact quoted path assigned false, preserving whitespace and
        # an optional comment around the value replacement.
        # Matches: '"/tmp/knowledge" = false # enable after review'
        # Does not match: '"/tmp/knowledge" = true' or '"~/knowledge" = false'
        match = re.search(
            rf"(?m)^([ \t]*{quoted}[ \t]*=[ \t]*)(false)"
            rf"([ \t]*(?:#.*)?)$",
            section,
        )
        if match:
            section = (
                section[: match.start(2)]
                + "true"
                + section[match.end(2) :]
            )
        else:
            remaining.append(path)
    text = text[:start] + section + text[end:]
    if not remaining:
        return text
    span = _table_span(text, target)
    body = "\n".join(f"{_toml_quote(path)} = true" for path in remaining)
    return _insert_in_table(text, span, body)


def render_sandbox_config_additions(
    text: str,
    data: dict,
    state: CodexSandboxConfigState,
) -> str:
    """Render missing sandbox paths while preserving unrelated TOML text."""
    if not state.missing_paths:
        return text
    if state.model == "profile":
        updated = _merge_profile_paths(
            text,
            state.profile_name or "",
            state.missing_paths,
        )
    else:
        updated = _merge_legacy_paths(text, state.missing_paths)
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
    """Back up an existing config and atomically replace it with settled text."""
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


def add_sandbox_paths_to_config(
    path: Path,
    required: tuple[str, ...],
) -> tuple[bool, Path | None]:
    """Add exact sandbox paths after validating input and rendered config."""
    text, data, state = load_sandbox_config_state(path, required)
    if not state.missing_paths:
        return False, None
    updated = render_sandbox_config_additions(text, data, state)
    parsed = _parse_toml(updated, path)
    verified = analyze_sandbox_config(parsed, required)
    if verified.missing_paths:
        raise CodexSandboxConfigError(
            "Generated config did not contain every requested sandbox path"
        )
    backup = _atomic_write(path, updated)
    return True, backup
