from __future__ import annotations

import argparse
import re

from .common import WORK_TYPES, collection_name, expand, project_dir, slugify, today, write_new


def next_id(work_root, prefix: str) -> str:
    max_seen = 0
    if work_root.exists():
        pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)-")
        for child in work_root.iterdir():
            if child.is_dir():
                match = pattern.match(child.name)
                if match:
                    max_seen = max(max_seen, int(match.group(1)))
    return f"{prefix}-{max_seen + 1:04d}"


def new_work(args: argparse.Namespace) -> None:
    root = expand(args.root)
    project = slugify(args.project)
    work_type = args.type
    prefix, plural = WORK_TYPES[work_type]
    pdir = project_dir(root, project)
    if not pdir.exists():
        raise SystemExit(f"Project memory does not exist: {pdir}")

    work_root = pdir / "work" / plural
    wid = args.id or next_id(work_root, prefix)
    slug = slugify(args.title)
    wdir = work_root / f"{wid}-{slug}"
    wdir.mkdir(parents=True, exist_ok=True)
    (wdir / "history").mkdir(exist_ok=True)

    domain_line = f"- Domain: `{args.domain}`" if args.domain else "- Domain:"
    write_new(
        wdir / "README.md",
        f"""# {wid}: {args.title}

## Status

active

## Type

{work_type}

## Metadata

- Project: `{project}`
{domain_line}
- Created: {today()}
- Updated: {today()}

## Objective

Describe the intended outcome.

## Scope

- In:
- Out:

## Links

- Active context: [active.md](active.md)
- History: [history/](history/)
""",
    )
    write_new(
        wdir / "active.md",
        f"""# Active Context

## Objective

{args.title}

## Current Phase

setup

## Current Attempt

main

## Repo State

- Repo:
- Branch:
- Worktree:
- Relevant files:

## Known Facts

- Work item created.

## Decisions In Force

- None yet.

## Open Questions

- What exact outcome should this work produce?

## Next Actions

1. Clarify scope.
2. Identify relevant project/domain context with qmd.
3. Begin implementation or create design/spec docs if needed.

## Resume Query

qmd query -c {collection_name(project)} $'lex: {wid} {slug}\\nvec: what context is needed to resume {args.title}'

## Last Updated

{today()} by agent
""",
    )
    print(f"Created {work_type}: {wdir}")


def branch_work(args: argparse.Namespace) -> None:
    wdir = expand(args.work)
    if not (wdir / "active.md").exists():
        raise SystemExit(f"Work item active.md not found under: {wdir}")
    attempt = slugify(args.name)
    adir = wdir / "attempts" / attempt
    adir.mkdir(parents=True, exist_ok=True)
    write_new(
        adir / "notes.md",
        f"""# Attempt: {attempt}

## Status

active

## Reason

{args.reason or "Describe why this attempt exists."}

## Started

{today()}
""",
    )
    print(f"Created attempt: {adir}")


def append_history(args: argparse.Namespace) -> None:
    wdir = expand(args.work)
    if not wdir.exists():
        raise SystemExit(f"Work item not found: {wdir}")
    history = wdir / "history"
    history.mkdir(exist_ok=True)
    date = today()
    existing = sorted(history.glob(f"{date}-session-*.md"))
    session = len(existing) + 1
    summary = args.summary or ""
    if args.summary_file:
        summary = expand(args.summary_file).read_text(encoding="utf-8").strip()
    if not summary:
        raise SystemExit("Provide --summary or --summary-file")
    path = history / f"{date}-session-{session:03d}.md"
    path.write_text(
        f"""# Session {session:03d} - {date}

## Summary

{summary}
""",
        encoding="utf-8",
    )
    print(f"Appended history: {path}")
