#!/usr/bin/env python3
"""Check or add Codex writable roots for memory and knowledge workflows."""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
import re
import shlex
import shutil
import subprocess
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

# A collection header is exactly two spaces, a qmd-safe name, and a colon;
# an inline comment is optional.
# Matches: "  example-knowledge:" and "  demo.learning: # local collection"
# Does not match: "example-knowledge:" or "    contains: knowledge"
_REGISTRY_COLLECTION_RE = re.compile(
    r"^  ([A-Za-z0-9_.-]+):\s*(?:#.*)?$"
)

# A collection field is exactly four spaces, a simple key, a colon, and any
# scalar text. Scalar validation and comment removal happen separately.
# Matches: "    contains: knowledge" and "    domain: 'demo' # program"
# Does not match: "  demo-knowledge:" or "      nested: value"
_REGISTRY_FIELD_RE = re.compile(
    r"^    ([A-Za-z0-9_.-]+):\s*(.*?)\s*$"
)

# The registry root must be an unindented `collections` map. The map may start
# a block or use the explicit empty-map form, with an optional inline comment.
# Matches: "collections:" and "collections: {} # no collections yet"
# Does not match: "  collections:" or "collections: []"
_REGISTRY_ROOT_RE = re.compile(
    r"^collections:\s*(\{\})?\s*(?:#.*)?$"
)

# `qmd collection show` renders one path line. Capture a path whose first and
# last characters are non-whitespace, allowing spaces inside the path while
# excluding the command's alignment whitespace.
# Matches: "  Path:     /Users/me/knowledge" and "Path: ~/My Notes"
# Does not match: "  Pattern: **/*.md", "  Path:", or "  Path:    "
_QMD_SHOW_PATH_RE = re.compile(r"^\s*Path:\s*(\S(?:.*\S)?)\s*$")


class ConfigError(ValueError):
    """The config cannot be checked or changed without guessing."""


@dataclasses.dataclass(frozen=True)
class ConfigState:
    model: str
    configured_roots: tuple[str, ...]
    missing_roots: tuple[str, ...]
    profile_name: str | None = None


@dataclasses.dataclass(frozen=True)
class RegistryCollection:
    name: str
    contains: str
    domain: str
    has_explicit_domain: bool


@dataclasses.dataclass(frozen=True)
class ResolvedCollection:
    name: str
    contains: str
    domain: str
    root: str


@dataclasses.dataclass(frozen=True)
class CollectionPair:
    domain: str
    knowledge: ResolvedCollection
    learning: ResolvedCollection


@dataclasses.dataclass(frozen=True)
class NewCollectionPlan:
    planned: ResolvedCollection
    counterpart: ResolvedCollection | None
    pairing_note: str

    @property
    def collections(self) -> tuple[ResolvedCollection, ...]:
        collections = [self.planned]
        if self.counterpart is not None:
            collections.append(self.counterpart)
        return tuple(
            sorted(
                collections,
                key=lambda collection: (
                    collection.contains != "knowledge",
                    collection.name,
                ),
            )
        )


def normalize_path(value: str | Path) -> str:
    raw = os.fspath(value)
    if not raw.strip():
        raise ConfigError("Path values must not be empty or whitespace-only")
    return str(Path(raw).expanduser().resolve(strict=False))


def default_config_path(environ: dict[str, str] | os._Environ[str] = os.environ) -> Path:
    user_home = Path(environ.get("HOME", Path.home()))
    codex_home = Path(environ.get("CODEX_HOME", user_home / ".codex"))
    return Path(normalize_path(codex_home)) / "config.toml"


def default_registry_path(
    environ: dict[str, str] | os._Environ[str] = os.environ,
) -> Path:
    user_home = Path(environ.get("HOME", Path.home()))
    config_home = Path(environ.get("XDG_CONFIG_HOME", user_home / ".config"))
    return Path(normalize_path(config_home)) / "qmd" / "registry.yaml"


def _strip_yaml_comment(value: str) -> str:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(value):
        if quote == '"':
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif quote == "'":
            if char == quote:
                quote = None
        elif char in ("'", '"'):
            quote = char
        elif char == "#" and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
    return value.rstrip()


def _parse_registry_scalar(value: str, path: Path, line_number: int) -> str:
    value = _strip_yaml_comment(value).strip()
    if not value:
        return ""
    if value.startswith('"'):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ConfigError(
                f"Unsupported registry scalar at {path}:{line_number}: {value}"
            ) from exc
        if not isinstance(parsed, str):
            raise ConfigError(
                f"Registry scalar at {path}:{line_number} must be a string"
            )
        return parsed
    if value.startswith("'"):
        if len(value) < 2 or not value.endswith("'"):
            raise ConfigError(
                f"Unterminated registry scalar at {path}:{line_number}"
            )
        return value[1:-1].replace("''", "'")
    if value[0] in "[{&*!|>@`":
        raise ConfigError(
            f"Unsupported registry scalar at {path}:{line_number}: {value}"
        )
    return value


def load_collection_registry(
    path: Path,
    *,
    allow_missing: bool = False,
) -> dict[str, RegistryCollection]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        if allow_missing:
            return {}
        raise ConfigError(f"Knowledge collection registry not found: {path}") from exc
    except OSError as exc:
        raise ConfigError(
            f"Cannot read knowledge collection registry {path}: {exc}"
        ) from exc

    collections: dict[str, dict[str, str]] = {}
    current: str | None = None
    in_collections = False
    found_root = False
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        if "\t" in raw_line[: len(raw_line) - len(raw_line.lstrip())]:
            raise ConfigError(
                f"Registry indentation must use spaces at {path}:{line_number}"
            )
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))

        if indent == 0:
            root_match = _REGISTRY_ROOT_RE.match(raw_line)
            if root_match:
                found_root = True
                in_collections = root_match.group(1) is None
                current = None
            else:
                in_collections = False
                current = None
            continue
        if not in_collections:
            continue

        collection_match = _REGISTRY_COLLECTION_RE.match(raw_line)
        if collection_match:
            current = collection_match.group(1)
            if current in collections:
                raise ConfigError(
                    f"Duplicate collection {current!r} in registry {path}"
                )
            collections[current] = {}
            continue

        field_match = _REGISTRY_FIELD_RE.match(raw_line)
        if field_match and current is not None:
            key, raw_value = field_match.groups()
            if key in collections[current]:
                raise ConfigError(
                    f"Duplicate field {key!r} for collection {current!r} in {path}"
                )
            collections[current][key] = _parse_registry_scalar(
                raw_value,
                path,
                line_number,
            )
            continue

        raise ConfigError(
            f"Unsupported registry structure at {path}:{line_number}: {stripped}"
        )

    if not found_root:
        raise ConfigError(f"Registry {path} is missing a top-level collections map")

    parsed: dict[str, RegistryCollection] = {}
    for name, fields in collections.items():
        domain = fields.get("domain", "")
        parsed[name] = RegistryCollection(
            name=name,
            contains=fields.get("contains", ""),
            domain=domain or "default",
            has_explicit_domain=bool(domain),
        )
    return parsed


def _run_qmd_collection_show(
    collection: str,
    environ: dict[str, str] | os._Environ[str],
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["qmd", "collection", "show", collection],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=dict(environ),
        )
    except (FileNotFoundError, OSError) as exc:
        raise ConfigError(
            f"qmd is unavailable while resolving collection {collection!r}: {exc}"
        ) from exc


def _qmd_path_from_show(
    collection: str,
    result: subprocess.CompletedProcess[str],
) -> str:
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        suffix = f": {detail}" if detail else ""
        raise ConfigError(f"qmd cannot resolve collection {collection!r}{suffix}")

    paths = []
    for line in result.stdout.splitlines():
        match = _QMD_SHOW_PATH_RE.match(line)
        if match:
            paths.append(normalize_path(match.group(1)))
    if len(paths) != 1:
        raise ConfigError(
            f"qmd collection show {collection!r} returned {len(paths)} Path fields"
        )
    return paths[0]


def _qmd_collection_root(
    collection: str,
    environ: dict[str, str] | os._Environ[str],
) -> str:
    return _qmd_path_from_show(
        collection,
        _run_qmd_collection_show(collection, environ),
    )


def _qmd_unregistered_collection(
    collection: str,
    environ: dict[str, str] | os._Environ[str],
) -> None:
    result = _run_qmd_collection_show(collection, environ)
    if result.returncode == 0:
        root = _qmd_path_from_show(collection, result)
        raise ConfigError(
            f"Collection {collection!r} is already registered with qmd at {root!r}; "
            "use check --collection for an existing collection"
        )
    detail = result.stderr.strip() or result.stdout.strip()
    if "collection not found" not in detail.lower():
        suffix = f": {detail}" if detail else ""
        raise ConfigError(
            f"qmd cannot confirm that collection {collection!r} is unregistered"
            f"{suffix}"
        )


def _knowledge_registry_entry(
    name: str,
    registry: dict[str, RegistryCollection],
    registry_path: Path,
) -> RegistryCollection:
    entry = registry.get(name)
    if entry is None:
        raise ConfigError(
            f"Collection {name!r} is not classified in {registry_path}"
        )
    if entry.contains not in ("knowledge", "learning"):
        rendered = entry.contains or "<missing>"
        raise ConfigError(
            f"Collection {name!r} contains {rendered!r}; "
            "it must be knowledge or learning"
        )
    return entry


def _resolve_registry_collections(
    entries: list[RegistryCollection],
    environ: dict[str, str] | os._Environ[str],
) -> tuple[ResolvedCollection, ...]:
    return tuple(
        ResolvedCollection(
            name=entry.name,
            contains=entry.contains,
            domain=entry.domain,
            root=_qmd_collection_root(entry.name, environ),
        )
        for entry in entries
    )


def resolve_knowledge_collections(
    collection_names: list[str],
    registry_path: Path | None = None,
    environ: dict[str, str] | os._Environ[str] = os.environ,
) -> tuple[ResolvedCollection, ...]:
    if not collection_names:
        return ()
    path = registry_path or default_registry_path(environ)
    registry = load_collection_registry(path)
    entries: list[RegistryCollection] = []
    seen: set[str] = set()
    for name in collection_names:
        if name in seen:
            continue
        seen.add(name)
        entries.append(_knowledge_registry_entry(name, registry, path))
    return _resolve_registry_collections(entries, environ)


def resolve_knowledge_learning_pair(
    collection_name: str,
    registry_path: Path | None = None,
    environ: dict[str, str] | os._Environ[str] = os.environ,
) -> CollectionPair:
    path = registry_path or default_registry_path(environ)
    registry = load_collection_registry(path)
    selected = _knowledge_registry_entry(collection_name, registry, path)
    if not selected.has_explicit_domain:
        raise ConfigError(
            f"Collection {collection_name!r} does not have an explicit domain in {path}"
        )

    counterpart_type = (
        "learning" if selected.contains == "knowledge" else "knowledge"
    )
    counterparts = sorted(
        (
            entry
            for entry in registry.values()
            if entry.contains == counterpart_type
            and entry.has_explicit_domain
            and entry.domain == selected.domain
        ),
        key=lambda entry: entry.name,
    )
    if not counterparts:
        raise ConfigError(
            f"Collection {collection_name!r} has no {counterpart_type} "
            f"counterpart in domain {selected.domain!r}"
        )
    if len(counterparts) > 1:
        names = ", ".join(entry.name for entry in counterparts)
        raise ConfigError(
            f"Collection {collection_name!r} has multiple {counterpart_type} "
            f"counterparts in domain {selected.domain!r}: {names}"
        )

    entries = {
        selected.contains: selected,
        counterpart_type: counterparts[0],
    }
    knowledge, learning = _resolve_registry_collections(
        [entries["knowledge"], entries["learning"]],
        environ,
    )
    if knowledge.root == learning.root:
        raise ConfigError(
            f"Knowledge collection {knowledge.name!r} and learning collection "
            f"{learning.name!r} must resolve to distinct qmd roots"
        )
    return CollectionPair(
        domain=selected.domain,
        knowledge=knowledge,
        learning=learning,
    )


def plan_new_collection(
    collection_name: str,
    expected_root: str | Path,
    contains: str,
    domain: str,
    registry_path: Path | None = None,
    environ: dict[str, str] | os._Environ[str] = os.environ,
) -> NewCollectionPlan:
    if _REGISTRY_COLLECTION_RE.fullmatch(f"  {collection_name}:") is None:
        raise ConfigError(f"Unsupported qmd collection name: {collection_name!r}")
    if contains not in ("knowledge", "learning"):
        raise ConfigError("A planned collection must contain knowledge or learning")
    domain = domain.strip()
    if not domain:
        raise ConfigError("A planned collection requires a non-empty domain")

    path = registry_path or default_registry_path(environ)
    registry = load_collection_registry(path, allow_missing=True)
    if collection_name in registry:
        raise ConfigError(
            f"Collection {collection_name!r} is already classified in {path}; "
            "use check --collection or repair one-sided registration"
        )
    _qmd_unregistered_collection(collection_name, environ)

    planned = ResolvedCollection(
        name=collection_name,
        contains=contains,
        domain=domain,
        root=normalize_path(expected_root),
    )
    counterpart_type = "learning" if contains == "knowledge" else "knowledge"
    counterparts = sorted(
        (
            entry
            for entry in registry.values()
            if entry.contains == counterpart_type
            and entry.has_explicit_domain
            and entry.domain == domain
        ),
        key=lambda entry: entry.name,
    )
    if not counterparts:
        return NewCollectionPlan(
            planned,
            None,
            f"no {counterpart_type} counterpart in domain {domain!r}",
        )
    if len(counterparts) > 1:
        names = ", ".join(entry.name for entry in counterparts)
        return NewCollectionPlan(
            planned,
            None,
            f"multiple {counterpart_type} counterparts in domain {domain!r}: {names}",
        )

    counterpart = _resolve_registry_collections([counterparts[0]], environ)[0]
    if counterpart.root == planned.root:
        raise ConfigError(
            f"Planned {contains} collection {collection_name!r} and "
            f"{counterpart_type} collection {counterpart.name!r} must use "
            "distinct qmd roots"
        )
    return NewCollectionPlan(
        planned,
        counterpart,
        f"paired with {counterpart.name!r} in domain {domain!r}",
    )


def _expected_collection_roots(
    collection_names: list[str],
    bindings: list[list[str]],
    command: str = "add-roots",
) -> dict[str, str]:
    requested = list(dict.fromkeys(collection_names))
    expected: dict[str, str] = {}
    for name, root in bindings:
        if name in expected:
            raise ConfigError(
                f"Duplicate --expected-root binding for collection {name!r}"
            )
        expected[name] = normalize_path(root)

    missing = [name for name in requested if name not in expected]
    if missing:
        rendered = ", ".join(repr(name) for name in missing)
        raise ConfigError(
            f"{command} requires one --expected-root COLLECTION PATH binding "
            f"for every --collection; missing: {rendered}"
        )

    unexpected = [name for name in expected if name not in requested]
    if unexpected:
        rendered = ", ".join(repr(name) for name in unexpected)
        raise ConfigError(
            "--expected-root supplied for unrequested collection(s): "
            f"{rendered}"
        )
    return expected


def _validate_expected_collection_roots(
    collections: tuple[ResolvedCollection, ...],
    expected: dict[str, str],
) -> None:
    for collection in collections:
        approved_root = expected[collection.name]
        if collection.root != approved_root:
            raise ConfigError(
                f"Collection {collection.name!r} now resolves to "
                f"{collection.root!r}, but approval was for "
                f"{approved_root!r}. Run the permission preflight again and "
                "obtain fresh approval before retrying."
            )


def _path_bound_add_roots_command(
    collections: tuple[ResolvedCollection, ...],
) -> str:
    arguments = ["add-roots"]
    for collection in collections:
        arguments.extend(
            [
                "--collection",
                collection.name,
                "--expected-root",
                collection.name,
                collection.root,
            ]
        )
    return shlex.join(arguments)


def _planned_add_roots_command(
    plan: NewCollectionPlan,
    config_path: Path,
) -> str:
    arguments = [
        "add-roots",
        "--planned-collection",
        plan.planned.name,
        "--contains",
        plan.planned.contains,
        "--domain",
        plan.planned.domain,
    ]
    for collection in plan.collections:
        if collection.name != plan.planned.name:
            arguments.extend(["--collection", collection.name])
        arguments.extend(
            [
                "--expected-root",
                collection.name,
                collection.root,
            ]
        )
    arguments.extend(["--config", str(config_path)])
    return shlex.join(arguments)


def _session_add_dir_command(roots: tuple[str, ...]) -> str:
    arguments = ["codex"]
    for root in roots:
        arguments.extend(["--add-dir", root])
    return shlex.join(arguments)


def required_roots(
    memory_root: str | Path | None = None,
    knowledge_roots: list[str] | None = None,
    environ: dict[str, str] | os._Environ[str] = os.environ,
    *,
    include_qmd_state: bool | None = None,
) -> tuple[str, ...]:
    """Return exact roots for one permission operation.

    Memory operations include qmd state by default. Existing knowledge
    operations omit it; pre-registration callers opt in explicitly.
    """
    user_home = Path(environ.get("HOME", Path.home()))
    cache_home = Path(environ.get("XDG_CACHE_HOME", user_home / ".cache"))
    config_home = Path(environ.get("XDG_CONFIG_HOME", user_home / ".config"))
    if include_qmd_state is None:
        include_qmd_state = memory_root is not None
    candidates: list[str | Path] = []
    if memory_root is not None:
        candidates.append(memory_root)
    candidates.extend(knowledge_roots or [])
    if include_qmd_state:
        candidates.extend((cache_home / "qmd", config_home / "qmd"))
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


def _missing_required_roots(
    configured: tuple[str, ...],
    required: tuple[str, ...],
) -> tuple[str, ...]:
    """Return exact required roots not covered by a configured ancestor."""
    configured_paths = tuple(Path(root) for root in configured)
    return tuple(
        root
        for root in required
        if not any(Path(root).is_relative_to(grant) for grant in configured_paths)
    )


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
            "choose one model before adding roots"
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
        missing = _missing_required_roots(configured, required)
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
    missing = _missing_required_roots(configured, required)
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


def render_root_additions(
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


def add_roots_to_config(
    path: Path, required: tuple[str, ...]
) -> tuple[bool, Path | None]:
    text, data, state = load_state(path, required)
    if not state.missing_roots:
        return False, None
    updated = render_root_additions(text, data, state)
    parsed = _parse_toml(updated, path)
    verified = analyze_config(parsed, required)
    if verified.missing_roots:
        raise ConfigError(
            "Generated config did not contain every requested writable root"
        )
    backup = _atomic_write(path, updated)
    return True, backup


def _print_resolved_collection(
    collection: ResolvedCollection,
    prefix: str = "  ",
) -> None:
    print(
        f"{prefix}{collection.name} "
        f"({collection.contains}, {collection.domain}): "
        f"{collection.root}"
    )


def _new_collection_plan_from_args(
    args: argparse.Namespace,
    expected_roots: dict[str, str],
) -> NewCollectionPlan:
    return plan_new_collection(
        args.planned_collection,
        expected_roots[args.planned_collection],
        args.contains,
        args.domain,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("check", "add-roots"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--memory-root")
        subparser.add_argument("--knowledge-root", action="append", default=[])
        subparser.add_argument("--collection", action="append", default=[])
        subparser.add_argument(
            "--expected-root",
            action="append",
            nargs=2,
            default=[],
            metavar=("COLLECTION", "PATH"),
            help=(
                "Approved collection/root binding. Required once for each "
                "--collection when adding roots; optional for a bound check."
            ),
        )
        if command == "add-roots":
            subparser.add_argument("--planned-collection")
            subparser.add_argument(
                "--contains",
                choices=("knowledge", "learning"),
            )
            subparser.add_argument("--domain")
        subparser.add_argument(
            "--config",
            help="Codex config path. Defaults to $CODEX_HOME/config.toml.",
        )
    plan_parser = subparsers.add_parser(
        "plan-new-collection",
        help=(
            "Check permissions for an exact collection root before qmd or registry "
            "registration."
        ),
    )
    plan_parser.add_argument("--collection", required=True)
    plan_parser.add_argument(
        "--expected-root",
        required=True,
        nargs=2,
        metavar=("COLLECTION", "PATH"),
    )
    plan_parser.add_argument(
        "--contains",
        required=True,
        choices=("knowledge", "learning"),
    )
    plan_parser.add_argument("--domain", required=True)
    plan_parser.add_argument(
        "--config",
        help="Codex config path. Defaults to $CODEX_HOME/config.toml.",
    )
    pair_parser = subparsers.add_parser(
        "resolve-knowledge-learning-pair",
        help="Resolve one same-domain knowledge/learning pair without changing config.",
    )
    pair_parser.add_argument("--collection", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "plan-new-collection":
        try:
            config_path = (
                Path(normalize_path(args.config))
                if args.config is not None
                else default_config_path()
            )
            expected_roots = _expected_collection_roots(
                [args.collection],
                [args.expected_root],
                command="plan-new-collection",
            )
            plan = plan_new_collection(
                args.collection,
                expected_roots[args.collection],
                args.contains,
                args.domain,
            )
            print("Planned new collection:")
            _print_resolved_collection(plan.planned)
            if plan.counterpart is not None:
                print("Resolved existing counterpart:")
                _print_resolved_collection(plan.counterpart)
            else:
                print(f"No deterministic counterpart: {plan.pairing_note}.")

            registration_roots = required_roots(
                knowledge_roots=[plan.planned.root],
                include_qmd_state=True,
            )
            print("Roots required before registration:")
            for root in registration_roots:
                print(f"  {root}")
            print(f"Codex config: {config_path}")
            _, _, state = load_state(config_path, registration_roots)
            if not state.missing_roots:
                print("Persistent config covers every pre-registration root.")
                print(
                    "Use /status to verify effective roots before registering "
                    "the collection."
                )
                return 0

            print("Missing pre-registration roots:")
            for root in state.missing_roots:
                print(f"  {root}")
            print("Session-only restart:")
            print(f"  {_session_add_dir_command(state.missing_roots)}")
            print("Persistent setup after explicit approval:")
            print(f"  {_planned_add_roots_command(plan, config_path)}")
            return EXIT_MISSING
        except ConfigError as exc:
            print(f"Cannot plan new collection permissions: {exc}", file=sys.stderr)
            return EXIT_UNSUPPORTED

    if args.command == "resolve-knowledge-learning-pair":
        try:
            pair = resolve_knowledge_learning_pair(args.collection)
            print("Resolved knowledge/learning pair:")
            for collection in (pair.knowledge, pair.learning):
                print(
                    f"  {collection.name} "
                    f"({collection.contains}, {collection.domain}): "
                    f"{collection.root}"
                )
            print("Persistent setup after explicit approval:")
            print(f"  {_path_bound_add_roots_command((pair.knowledge, pair.learning))}")
            return 0
        except ConfigError as exc:
            print(f"Cannot resolve permission pair: {exc}", file=sys.stderr)
            return EXIT_UNSUPPORTED

    planned_collection = getattr(args, "planned_collection", None)
    if (
        args.memory_root is None
        and not args.knowledge_root
        and not args.collection
        and planned_collection is None
    ):
        if args.command == "check":
            parser.error(
                "at least one of --memory-root, --knowledge-root, "
                "or --collection is required"
            )
        parser.error(
            "at least one of --memory-root, --knowledge-root, --collection, "
            "or --planned-collection is required"
        )

    try:
        config_path = (
            Path(normalize_path(args.config))
            if args.config is not None
            else default_config_path()
        )
        if args.memory_root is not None:
            normalize_path(args.memory_root)
        for root in args.knowledge_root:
            normalize_path(root)

        if planned_collection is not None:
            if args.memory_root is not None or args.knowledge_root:
                raise ConfigError(
                    "--planned-collection cannot be combined with direct memory "
                    "or knowledge roots"
                )
            if args.contains is None or args.domain is None:
                raise ConfigError(
                    "--planned-collection requires --contains and --domain"
                )
        elif args.command == "add-roots" and (
            args.contains is not None or args.domain is not None
        ):
            raise ConfigError(
                "--contains and --domain require --planned-collection"
            )

        requested_collections = [
            *([planned_collection] if planned_collection is not None else []),
            *args.collection,
        ]
        expected_roots = {}
        if args.command == "add-roots" or args.expected_root:
            expected_roots = _expected_collection_roots(
                requested_collections,
                args.expected_root,
                command=args.command,
            )

        if planned_collection is not None:
            plan = _new_collection_plan_from_args(args, expected_roots)
            expected_counterparts = [
                collection.name
                for collection in plan.collections
                if collection.name != planned_collection
            ]
            supplied_counterparts = list(dict.fromkeys(args.collection))
            if supplied_counterparts != expected_counterparts:
                rendered = ", ".join(expected_counterparts) or "<none>"
                raise ConfigError(
                    "Registered --collection arguments do not match the current "
                    f"deterministic counterpart plan; expected: {rendered}"
                )
            resolved = plan.collections
            print("Validated planned new collection:")
            _print_resolved_collection(plan.planned)
            if plan.counterpart is not None:
                print("Validated existing counterpart:")
                _print_resolved_collection(plan.counterpart)
            else:
                print(f"No deterministic counterpart: {plan.pairing_note}.")
        else:
            resolved = resolve_knowledge_collections(args.collection)
        if resolved:
            if planned_collection is None:
                print("Resolved knowledge collections:")
                for collection in resolved:
                    _print_resolved_collection(collection)
        knowledge_roots = [
            *args.knowledge_root,
            *(collection.root for collection in resolved),
        ]
        roots = required_roots(
            args.memory_root,
            knowledge_roots,
            include_qmd_state=(
                args.memory_root is not None or planned_collection is not None
            ),
        )
        print("Required writable roots:")
        for root in roots:
            print(f"  {root}")
        print(f"Codex config: {config_path}")

        if args.command == "check":
            if expected_roots:
                _validate_expected_collection_roots(resolved, expected_roots)
            _, _, state = load_state(config_path, roots)
            if state.missing_roots:
                print("Missing writable roots:")
                for root in state.missing_roots:
                    print(f"  {root}")
                return EXIT_MISSING
            print("Configured roots include every requested path.")
            print("Use /status in the active Codex session to verify effective roots.")
            return 0

        _validate_expected_collection_roots(resolved, expected_roots)
        changed, backup = add_roots_to_config(config_path, roots)
        if not changed:
            print("No config change needed.")
        else:
            print("Added Codex writable roots.")
            if backup:
                print(f"Backup: {backup}")
            print("Restart Codex, then use /status to verify effective roots.")
        return 0
    except ConfigError as exc:
        print(f"Cannot update permissions: {exc}", file=sys.stderr)
        return EXIT_UNSUPPORTED


if __name__ == "__main__":
    sys.exit(main())
