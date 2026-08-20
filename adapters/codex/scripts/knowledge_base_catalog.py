"""Resolve knowledge-base registry metadata against qmd collection paths."""

from __future__ import annotations

import dataclasses
import enum
import json
import os
import re
import subprocess
from pathlib import Path


# A collection header is exactly two spaces, a qmd-safe name, and a colon;
# an inline comment is optional.
# Matches: "  example-knowledge:" and "  demo.learning: # local collection"
# Does not match: "example-knowledge:" or "    contains: knowledge"
_KNOWLEDGE_BASE_REGISTRY_COLLECTION_RE = re.compile(
    r"^  ([A-Za-z0-9_.-]+):\s*(?:#.*)?$"
)

# A collection field is exactly four spaces, a simple key, a colon, and any
# scalar text. Scalar validation and comment removal happen separately.
# Matches: "    contains: knowledge" and "    domain: 'demo' # program"
# Does not match: "  demo-knowledge:" or "      nested: value"
_KNOWLEDGE_BASE_REGISTRY_FIELD_RE = re.compile(
    r"^    ([A-Za-z0-9_.-]+):\s*(.*?)\s*$"
)

# The registry root must be an unindented `collections` map. The map may start
# a block or use the explicit empty-map form, with an optional inline comment.
# Matches: "collections:" and "collections: {} # no collections yet"
# Does not match: "  collections:" or "collections: []"
_KNOWLEDGE_BASE_REGISTRY_ROOT_RE = re.compile(
    r"^collections:\s*(\{\})?\s*(?:#.*)?$"
)

# `qmd collection show` renders one path line. Capture a path whose first and
# last characters are non-whitespace, allowing spaces inside the path while
# excluding the command's alignment whitespace.
# Matches: "  Path:     /Users/me/knowledge" and "Path: ~/My Notes"
# Does not match: "  Pattern: **/*.md", "  Path:", or "  Path:    "
_QMD_SHOW_PATH_RE = re.compile(r"^\s*Path:\s*(\S(?:.*\S)?)\s*$")


class KnowledgeBaseCatalogError(ValueError):
    """The knowledge-base catalog cannot be resolved without guessing."""


@dataclasses.dataclass(frozen=True)
class KnowledgeBaseRegistryEntry:
    """Role and domain metadata owned by the knowledge-base registry."""

    name: str
    role: str
    domain: str
    has_explicit_domain: bool


@dataclasses.dataclass(frozen=True)
class KnowledgeBaseRegistry:
    """Knowledge-base entries indexed by collection name, domain, and role."""

    by_name: dict[str, KnowledgeBaseRegistryEntry]
    by_domain_and_role: dict[
        tuple[str, str],
        tuple[KnowledgeBaseRegistryEntry, ...],
    ]


@dataclasses.dataclass(frozen=True)
class ResolvedKnowledgeBaseCollection:
    """A knowledge-base entry joined to its qmd-owned collection path."""

    name: str
    role: str
    domain: str
    collection_path: str


@dataclasses.dataclass(frozen=True)
class KnowledgeLearningPair:
    """One unambiguous same-domain pair selected for Codex sandbox access."""

    domain: str
    knowledge: ResolvedKnowledgeBaseCollection
    learning: ResolvedKnowledgeBaseCollection


@dataclasses.dataclass(frozen=True)
class NewCollectionPlan:
    """A proposed registry entry and its sole opposite-role candidate, if any."""

    planned: ResolvedKnowledgeBaseCollection
    same_domain_counterpart: ResolvedKnowledgeBaseCollection | None
    counterpart_note: str

    @property
    def collections(self) -> tuple[ResolvedKnowledgeBaseCollection, ...]:
        if self.same_domain_counterpart is None:
            return (self.planned,)
        if self.planned.role == "knowledge":
            return (self.planned, self.same_domain_counterpart)
        return (self.same_domain_counterpart, self.planned)


class _RegistryState(enum.Enum):
    OUTSIDE_COLLECTIONS = enum.auto()
    IN_COLLECTIONS = enum.auto()
    IN_ENTRY = enum.auto()


def normalize_collection_path(value: str | Path) -> str:
    raw = os.fspath(value)
    if not raw.strip():
        raise KnowledgeBaseCatalogError(
            "Path values must not be empty or whitespace-only"
        )
    return str(Path(raw).expanduser().resolve(strict=False))


def default_knowledge_base_registry_path(
    environ: dict[str, str] | os._Environ[str] = os.environ,
) -> Path:
    user_home = Path(environ.get("HOME", Path.home()))
    config_home = Path(environ.get("XDG_CONFIG_HOME", user_home / ".config"))
    return Path(normalize_collection_path(config_home)) / "qmd" / "registry.yaml"


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


def _parse_knowledge_base_registry_scalar(
    value: str,
    path: Path,
    line_number: int,
) -> str:
    value = _strip_yaml_comment(value).strip()
    if not value:
        return ""
    if value.startswith('"'):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise KnowledgeBaseCatalogError(
                f"Unsupported registry scalar at {path}:{line_number}: {value}"
            ) from exc
        if not isinstance(parsed, str):
            raise KnowledgeBaseCatalogError(
                f"Registry scalar at {path}:{line_number} must be a string"
            )
        return parsed
    if value.startswith("'"):
        if len(value) < 2 or not value.endswith("'"):
            raise KnowledgeBaseCatalogError(
                f"Unterminated registry scalar at {path}:{line_number}"
            )
        return value[1:-1].replace("''", "'")
    if value[0] in "[{&*!|>@`":
        raise KnowledgeBaseCatalogError(
            f"Unsupported registry scalar at {path}:{line_number}: {value}"
        )
    return value


def _read_knowledge_base_registry_text(
    path: Path,
    *,
    allow_missing: bool,
) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        if allow_missing:
            return None
        raise KnowledgeBaseCatalogError(
            f"Knowledge-base registry not found: {path}"
        ) from exc
    except OSError as exc:
        raise KnowledgeBaseCatalogError(
            f"Cannot read knowledge-base registry {path}: {exc}"
        ) from exc


def _parse_knowledge_base_registry_lines(
    text: str,
    path: Path,
) -> dict[str, dict[str, str]]:
    """Parse the supported YAML subset into raw per-collection fields.

    The state machine starts outside the top-level `collections` map, enters
    that map after its root line, and enters one collection entry after a
    two-space collection header. Only four-space scalar fields are accepted
    inside an entry; unsupported nesting or indentation fails closed.
    """
    collections: dict[str, dict[str, str]] = {}
    current: str | None = None
    state = _RegistryState.OUTSIDE_COLLECTIONS
    found_root = False

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        if "\t" in raw_line[: len(raw_line) - len(raw_line.lstrip())]:
            raise KnowledgeBaseCatalogError(
                f"Registry indentation must use spaces at {path}:{line_number}"
            )
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))

        if indent == 0:
            root_match = _KNOWLEDGE_BASE_REGISTRY_ROOT_RE.match(raw_line)
            if root_match:
                found_root = True
                state = (
                    _RegistryState.IN_COLLECTIONS
                    if root_match.group(1) is None
                    else _RegistryState.OUTSIDE_COLLECTIONS
                )
            else:
                state = _RegistryState.OUTSIDE_COLLECTIONS
            current = None
            continue
        if state is _RegistryState.OUTSIDE_COLLECTIONS:
            continue

        collection_match = _KNOWLEDGE_BASE_REGISTRY_COLLECTION_RE.match(raw_line)
        if collection_match:
            current = collection_match.group(1)
            if current in collections:
                raise KnowledgeBaseCatalogError(
                    f"Duplicate collection {current!r} in registry {path}"
                )
            collections[current] = {}
            state = _RegistryState.IN_ENTRY
            continue

        field_match = _KNOWLEDGE_BASE_REGISTRY_FIELD_RE.match(raw_line)
        if field_match and state is _RegistryState.IN_ENTRY and current is not None:
            key, raw_value = field_match.groups()
            if key in collections[current]:
                raise KnowledgeBaseCatalogError(
                    f"Duplicate field {key!r} for collection {current!r} in {path}"
                )
            collections[current][key] = _parse_knowledge_base_registry_scalar(
                raw_value,
                path,
                line_number,
            )
            continue

        raise KnowledgeBaseCatalogError(
            f"Unsupported registry structure at {path}:{line_number}: {stripped}"
        )

    if not found_root:
        raise KnowledgeBaseCatalogError(
            f"Registry {path} is missing a top-level collections map"
        )
    return collections


def _build_knowledge_base_registry(
    collections: dict[str, dict[str, str]],
) -> KnowledgeBaseRegistry:
    by_name: dict[str, KnowledgeBaseRegistryEntry] = {}
    grouped: dict[tuple[str, str], list[KnowledgeBaseRegistryEntry]] = {}
    for name, fields in collections.items():
        domain = fields.get("domain", "")
        entry = KnowledgeBaseRegistryEntry(
            name=name,
            role=fields.get("contains", ""),
            domain=domain or "default",
            has_explicit_domain=bool(domain),
        )
        by_name[name] = entry
        grouped.setdefault((entry.domain, entry.role), []).append(entry)
    by_domain_and_role = {
        key: tuple(sorted(entries, key=lambda entry: entry.name))
        for key, entries in grouped.items()
    }
    return KnowledgeBaseRegistry(by_name, by_domain_and_role)


def load_knowledge_base_registry(
    path: Path,
    *,
    allow_missing: bool = False,
) -> KnowledgeBaseRegistry:
    """Load the knowledge-base registry's controlled YAML subset."""
    text = _read_knowledge_base_registry_text(path, allow_missing=allow_missing)
    if text is None:
        return KnowledgeBaseRegistry({}, {})
    return _build_knowledge_base_registry(
        _parse_knowledge_base_registry_lines(text, path)
    )


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
        raise KnowledgeBaseCatalogError(
            f"qmd is unavailable while resolving collection {collection!r}: {exc}"
        ) from exc


def _qmd_path_from_show(
    collection: str,
    result: subprocess.CompletedProcess[str],
) -> str:
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        suffix = f": {detail}" if detail else ""
        raise KnowledgeBaseCatalogError(
            f"qmd cannot resolve collection {collection!r}{suffix}"
        )

    paths = []
    for line in result.stdout.splitlines():
        match = _QMD_SHOW_PATH_RE.match(line)
        if match:
            paths.append(normalize_collection_path(match.group(1)))
    if len(paths) != 1:
        raise KnowledgeBaseCatalogError(
            f"qmd collection show {collection!r} returned {len(paths)} Path fields"
        )
    return paths[0]


def _qmd_collection_path(
    collection: str,
    environ: dict[str, str] | os._Environ[str],
) -> str:
    return _qmd_path_from_show(
        collection,
        _run_qmd_collection_show(collection, environ),
    )


def _require_qmd_collection_absent(
    collection: str,
    environ: dict[str, str] | os._Environ[str],
) -> None:
    result = _run_qmd_collection_show(collection, environ)
    if result.returncode == 0:
        collection_path = _qmd_path_from_show(collection, result)
        raise KnowledgeBaseCatalogError(
            f"Collection {collection!r} is already registered with qmd at "
            f"{collection_path!r}; use check --collection for an existing collection"
        )
    detail = result.stderr.strip() or result.stdout.strip()
    if "collection not found" not in detail.lower():
        suffix = f": {detail}" if detail else ""
        raise KnowledgeBaseCatalogError(
            f"qmd cannot confirm that collection {collection!r} is unregistered"
            f"{suffix}"
        )


def _require_knowledge_base_registry_entry(
    name: str,
    registry: KnowledgeBaseRegistry,
    registry_path: Path,
) -> KnowledgeBaseRegistryEntry:
    entry = registry.by_name.get(name)
    if entry is None:
        raise KnowledgeBaseCatalogError(
            f"Collection {name!r} is not classified in {registry_path}"
        )
    if entry.role not in ("knowledge", "learning"):
        rendered = entry.role or "<missing>"
        raise KnowledgeBaseCatalogError(
            f"Collection {name!r} contains {rendered!r}; "
            "it must be knowledge or learning"
        )
    return entry


def _same_domain_opposite_role_candidates(
    registry: KnowledgeBaseRegistry,
    role: str,
    domain: str,
) -> tuple[KnowledgeBaseRegistryEntry, ...]:
    opposite_role = "learning" if role == "knowledge" else "knowledge"
    return tuple(
        entry
        for entry in registry.by_domain_and_role.get(
            (domain, opposite_role),
            (),
        )
        if entry.has_explicit_domain
    )


def _resolve_knowledge_base_entries(
    entries: list[KnowledgeBaseRegistryEntry],
    environ: dict[str, str] | os._Environ[str],
) -> tuple[ResolvedKnowledgeBaseCollection, ...]:
    return tuple(
        ResolvedKnowledgeBaseCollection(
            name=entry.name,
            role=entry.role,
            domain=entry.domain,
            collection_path=_qmd_collection_path(entry.name, environ),
        )
        for entry in entries
    )


def resolve_knowledge_base_collections(
    collection_names: list[str],
    registry_path: Path | None = None,
    environ: dict[str, str] | os._Environ[str] = os.environ,
) -> tuple[ResolvedKnowledgeBaseCollection, ...]:
    if not collection_names:
        return ()
    path = registry_path or default_knowledge_base_registry_path(environ)
    registry = load_knowledge_base_registry(path)
    entries: list[KnowledgeBaseRegistryEntry] = []
    seen: set[str] = set()
    for name in collection_names:
        if name in seen:
            continue
        seen.add(name)
        entries.append(
            _require_knowledge_base_registry_entry(name, registry, path)
        )
    return _resolve_knowledge_base_entries(entries, environ)


def resolve_knowledge_learning_pair(
    collection_name: str,
    registry_path: Path | None = None,
    environ: dict[str, str] | os._Environ[str] = os.environ,
) -> KnowledgeLearningPair:
    """Resolve one collection and its sole explicit-domain opposite-role entry.

    Resolution starts with a knowledge-base registry lookup, requires the selected
    entry to have an explicit domain, and rejects zero or multiple opposite-role
    candidates. The two names are then joined to qmd-owned paths and must resolve
    to distinct directories.
    """
    path = registry_path or default_knowledge_base_registry_path(environ)
    registry = load_knowledge_base_registry(path)
    selected = _require_knowledge_base_registry_entry(
        collection_name,
        registry,
        path,
    )
    if not selected.has_explicit_domain:
        raise KnowledgeBaseCatalogError(
            f"Collection {collection_name!r} does not have an explicit domain in {path}"
        )

    counterpart_role = (
        "learning" if selected.role == "knowledge" else "knowledge"
    )
    counterpart_candidates = _same_domain_opposite_role_candidates(
        registry,
        selected.role,
        selected.domain,
    )
    if not counterpart_candidates:
        raise KnowledgeBaseCatalogError(
            f"Collection {collection_name!r} has no {counterpart_role} "
            f"counterpart in domain {selected.domain!r}"
        )
    if len(counterpart_candidates) > 1:
        names = ", ".join(entry.name for entry in counterpart_candidates)
        raise KnowledgeBaseCatalogError(
            f"Collection {collection_name!r} has multiple {counterpart_role} "
            f"counterparts in domain {selected.domain!r}: {names}"
        )

    entries = {
        selected.role: selected,
        counterpart_role: counterpart_candidates[0],
    }
    knowledge, learning = _resolve_knowledge_base_entries(
        [entries["knowledge"], entries["learning"]],
        environ,
    )
    if knowledge.collection_path == learning.collection_path:
        raise KnowledgeBaseCatalogError(
            f"Knowledge collection {knowledge.name!r} and learning collection "
            f"{learning.name!r} must resolve to distinct qmd paths"
        )
    return KnowledgeLearningPair(
        domain=selected.domain,
        knowledge=knowledge,
        learning=learning,
    )


def plan_new_collection(
    collection_name: str,
    approved_collection_path: str | Path,
    role: str,
    domain: str,
    registry_path: Path | None = None,
    environ: dict[str, str] | os._Environ[str] = os.environ,
) -> NewCollectionPlan:
    """Validate a proposed knowledge-base collection before registration."""
    if (
        _KNOWLEDGE_BASE_REGISTRY_COLLECTION_RE.fullmatch(
            f"  {collection_name}:"
        )
        is None
    ):
        raise KnowledgeBaseCatalogError(
            f"Unsupported qmd collection name: {collection_name!r}"
        )
    if role not in ("knowledge", "learning"):
        raise KnowledgeBaseCatalogError(
            "A planned collection must contain knowledge or learning"
        )
    domain = domain.strip()
    if not domain:
        raise KnowledgeBaseCatalogError(
            "A planned collection requires a non-empty domain"
        )

    path = registry_path or default_knowledge_base_registry_path(environ)
    registry = load_knowledge_base_registry(path, allow_missing=True)
    if collection_name in registry.by_name:
        raise KnowledgeBaseCatalogError(
            f"Collection {collection_name!r} is already classified in {path}; "
            "use check --collection or repair one-sided registration"
        )
    _require_qmd_collection_absent(collection_name, environ)

    planned = ResolvedKnowledgeBaseCollection(
        name=collection_name,
        role=role,
        domain=domain,
        collection_path=normalize_collection_path(approved_collection_path),
    )
    counterpart_role = "learning" if role == "knowledge" else "knowledge"
    counterpart_candidates = _same_domain_opposite_role_candidates(
        registry,
        role,
        domain,
    )
    if not counterpart_candidates:
        return NewCollectionPlan(
            planned,
            None,
            f"no {counterpart_role} counterpart in domain {domain!r}",
        )
    if len(counterpart_candidates) > 1:
        names = ", ".join(entry.name for entry in counterpart_candidates)
        return NewCollectionPlan(
            planned,
            None,
            f"multiple {counterpart_role} counterparts in domain {domain!r}: "
            f"{names}",
        )

    same_domain_counterpart = _resolve_knowledge_base_entries(
        [counterpart_candidates[0]],
        environ,
    )[0]
    if same_domain_counterpart.collection_path == planned.collection_path:
        raise KnowledgeBaseCatalogError(
            f"Planned {role} collection {collection_name!r} and "
            f"{counterpart_role} collection {same_domain_counterpart.name!r} "
            "must use distinct qmd paths"
        )
    return NewCollectionPlan(
        planned,
        same_domain_counterpart,
        f"paired with {same_domain_counterpart.name!r} in domain {domain!r}",
    )
