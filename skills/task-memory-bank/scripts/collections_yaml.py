#!/usr/bin/env python3
"""Comment-preserving reader + surgical writers for collections.yaml.

collections.yaml is the source of truth for routing. It is read by memory_bank.py
AND by an LLM agent, so inline comments carry semantic context and MUST survive
every write. We deliberately do NOT use a load->mutate->dump YAML library: neither
PyYAML nor ruamel.yaml is stdlib, taking a third-party dep would force a delivery
mechanism (venv/uv/pip) onto a skill invoked as bare `python3 <path>`, and PyYAML
cannot round-trip comments anyway. Instead we own the file's shape and mutate it
surgically as text, leaving untouched lines byte-for-byte. The write surface is
small and enumerable: (1) author a fresh file, (2) add or replace a single
collection block, (3) append a repo under an existing `repos:` list.

See docs/task-memory-bank-knowledge-retrieval-design.md for the design rationale.
"""

from __future__ import annotations

import re
from pathlib import Path


_TOP_RE = re.compile(r"^  ([A-Za-z0-9_.-]+):\s*$")
_KV_RE = re.compile(r"^    ([A-Za-z0-9_.-]+):\s*(.*?)\s*$")
_LIST_ITEM_RE = re.compile(r"^      -\s*(.*?)\s*$")


def _strip_inline_comment(value: str) -> str:
    """Drop a trailing ` # ...` comment from a scalar, honoring quotes.

    A `#` inside a quoted string is literal; a `#` that begins a bare token
    (preceded by whitespace or at line start) starts a comment.
    """
    quote: str | None = None
    for i, ch in enumerate(value):
        if quote:
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "#" and (i == 0 or value[i - 1].isspace()):
            return value[:i].rstrip()
    return value.rstrip()


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def parse_collections(path: Path) -> dict[str, dict[str, object]]:
    """Read collections.yaml into {name: {field: value}}.

    `repos:` is returned as a `list[str]`. A legacy single-string `repo:` entry is
    read as a one-element `repos` list (so an unmigrated file still loads), while
    the original `repo` scalar is also preserved for callers/migration that check it.
    Inline comments are stripped from scalar values.
    """
    if not path.exists():
        return {}
    collections: dict[str, dict[str, object]] = {}
    current: str | None = None
    in_repos = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or line == "collections:":
            continue

        top_match = _TOP_RE.match(line)
        if top_match:
            current = top_match.group(1)
            collections[current] = {}
            in_repos = False
            continue

        if current is None:
            continue

        if in_repos:
            item_match = _LIST_ITEM_RE.match(line)
            if item_match:
                item = _unquote(_strip_inline_comment(item_match.group(1)))
                if item:
                    collections[current]["repos"].append(item)  # type: ignore[union-attr]
                continue
            in_repos = False  # dedented out of the list; fall through

        kv_match = _KV_RE.match(line)
        if not kv_match:
            continue
        key, raw_value = kv_match.groups()
        value = raw_value.strip()
        if key == "repos" and value == "":
            collections[current]["repos"] = []
            in_repos = True
            continue
        scalar = _unquote(_strip_inline_comment(value))
        if key == "repos":
            # Inline form `repos: [a, b]` is not emitted by us, but tolerate it.
            inner = scalar.strip().lstrip("[").rstrip("]").strip()
            items = [_unquote(p) for p in inner.split(",")] if inner else []
            collections[current]["repos"] = [p for p in items if p]
        elif key == "repo":
            collections[current]["repo"] = scalar
            collections[current].setdefault("repos", [scalar] if scalar else [])
        else:
            collections[current][key] = scalar
    return collections


def _quote_scalar(value: str) -> str:
    """Quote a scalar if it would otherwise be misread (e.g. contains a `#`).

    Keeps the common case (paths, slugs) unquoted; quotes only when a bare value
    would be truncated or misparsed so that parse(write(x)) == x.
    """
    if value == "":
        return ""
    if value != value.strip() or value != _strip_inline_comment(value) \
            or value[0] in ("'", '"', "[", "{", "#", "&", "*", "!", "|", ">", "@", "`") \
            or ": " in value or value.endswith(":"):
        return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'
    return value


def _render_field(key: str, value: object) -> list[str]:
    """Render one field of a collection block as indented YAML lines."""
    if key == "repos":
        items = list(value) if isinstance(value, (list, tuple)) else ([value] if value else [])
        if not items:
            return ["    repos: []"]
        lines = ["    repos:"]
        lines.extend(f"      - {_quote_scalar(str(item))}" for item in items)
        return lines
    return [f"    {key}: {_quote_scalar(str(value))}"]


def _render_block(name: str, fields: dict[str, object]) -> list[str]:
    """Render a full collection block (its `  name:` line and body).

    A legacy lone `repo` scalar (no `repos`) is promoted to a `repos` list; we
    never emit the `repo` scalar form.
    """
    fields = dict(fields)
    if "repo" in fields:
        repo = fields.pop("repo")
        fields.setdefault("repos", [repo] if repo else [])
    lines = [f"  {name}:"]
    for key, value in fields.items():
        lines.extend(_render_field(key, value))
    return lines


def _find_block_span(lines: list[str], name: str) -> tuple[int, int] | None:
    """Return (start, end) line indices of the `  name:` block, else None.

    The block runs from its `  name:` header up to (not including) the next
    top-level collection header or EOF. A trailing blank separator line, if
    present, is left for the caller to manage.
    """
    start = None
    for i, line in enumerate(lines):
        m = _TOP_RE.match(line)
        if m and m.group(1) == name:
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if _TOP_RE.match(lines[j]):
            end = j
            break
    return start, end


def create_collections_file(path: Path, name: str, fields: dict[str, object]) -> None:
    """Author a fresh collections.yaml with a single seed block (init only)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["collections:", *_render_block(name, fields), ""]
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def upsert_collection_block(path: Path, name: str, fields: dict[str, object]) -> None:
    """Add or replace a single collection block, preserving all other lines.

    Untouched lines (comments, other blocks) are left byte-for-byte. If the file
    does not exist yet, it is created with the `collections:` header.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        create_collections_file(path, name, fields)
        return

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "collections:":
        lines = ["collections:"] + lines

    block = _render_block(name, fields)
    span = _find_block_span(lines, name)
    if span is None:
        # Append a new block. Ensure exactly one blank line before it.
        while lines and lines[-1].strip() == "":
            lines.pop()
        lines.append("")
        lines.extend(block)
    else:
        start, end = span
        # Preserve a single trailing blank separator that belonged to the old block.
        trailing_blank = end > start and end <= len(lines) and \
            (end == len(lines) and lines[end - 1].strip() == "")
        replacement = list(block)
        if trailing_blank:
            replacement.append("")
        lines[start:end] = replacement
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def append_repo(path: Path, name: str, repo: str) -> bool:
    """Append `repo` to the named block's `repos:` list, preserving comments.

    Returns True if the file was changed, False if the repo was already present
    or the block/list was not found. This is the association-accrual primitive
    that new-work will use to record a repo touched by a work item; it is defined
    and tested here but not yet wired into any command.
    """
    if not path.exists():
        return False
    data = parse_collections(path)
    if name not in data:
        return False
    existing = data[name].get("repos") or []
    if repo in existing:
        return False
    fields = dict(data[name])
    fields["repos"] = list(existing) + [repo]
    upsert_collection_block(path, name, fields)
    return True


def migrate_text(text: str) -> str:
    """Return migrated collections.yaml text, preserving comments (surgical).

    - single-string `repo: <x>` -> `repos:` block list (empty/absent -> `repos: []`);
    - drop the legacy `kind: global` umbrella block entirely.
    Idempotent: already-migrated input returns unchanged.
    """
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        top = _TOP_RE.match(line)
        if top:
            # Peek the block body to detect a `kind: global` umbrella entry.
            j = i + 1
            body: list[str] = []
            while j < n and not _TOP_RE.match(lines[j]):
                body.append(lines[j])
                j += 1
            is_umbrella = any(
                _KV_RE.match(b) and _KV_RE.match(b).group(1) == "kind"
                and _unquote(_strip_inline_comment(_KV_RE.match(b).group(2))) == "global"
                for b in body
            )
            if is_umbrella:
                # Drop the whole block; collapse surrounding blanks to one separator.
                i = j
                while out and out[-1].strip() == "":
                    out.pop()
                if out and out[-1].strip() != "":
                    out.append("")
                continue
            out.append(line)
            for b in body:
                kv = _KV_RE.match(b)
                if kv and kv.group(1) == "repo":
                    value = _strip_inline_comment(kv.group(2))
                    repo = _unquote(value)
                    if repo:
                        out.append("    repos:")
                        out.append(f"      - {repo}")
                    else:
                        out.append("    repos: []")
                else:
                    out.append(b)
            i = j
            continue
        out.append(line)
        i += 1
    return "\n".join(out).rstrip() + "\n"
