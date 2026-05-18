from __future__ import annotations

import argparse
import json
from pathlib import Path

from .common import (
    append_once,
    collection_name,
    current_git_root,
    display_title,
    expand,
    normalize_path,
    parse_collections,
    project_dir,
    slugify,
    today,
    write_collections,
    write_new,
)


def write_project_collection_manifest(pdir: Path, project: str, cname: str, repo: str) -> None:
    manifest = pdir / ".memory-bank" / "collection.yaml"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        f"""collection:
  name: {cname}
  kind: project
  project: {project}
  repo: {repo}
  context: {project}
  path: .
  mode: recursive
""",
        encoding="utf-8",
    )


def init_root(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    write_new(
        root / "registry.md",
        """# Task Memory Bank Registry

## Projects

Add project links here as memory-bank projects are initialized.
""",
    )
    write_new(
        root / ".memory-bank" / "collections.yaml",
        f"""collections:
  task-memory-bank:
    path: {root}
    mode: recursive
    kind: global
""",
    )


def upsert_collection(root: Path, project: str, pdir: Path, cname: str, repo: str) -> None:
    collections = root / ".memory-bank" / "collections.yaml"
    data = parse_collections(collections)
    data.setdefault(
        "task-memory-bank",
        {"path": str(root), "mode": "recursive", "kind": "global"},
    )
    data[cname] = {
        "path": str(pdir),
        "mode": "recursive",
        "kind": "project",
        "project": project,
        "repo": repo,
        "context": project,
    }
    write_collections(collections, data)


def init_project(args: argparse.Namespace) -> None:
    root = expand(args.root)
    project = slugify(args.project)
    repo = expand(args.repo) if args.repo else None
    init_root(root)

    pdir = project_dir(root, project)
    pdir.mkdir(parents=True, exist_ok=True)
    for subdir in [
        "overviews",
        "domains",
        "work/epics",
        "work/stories",
        "work/tasks",
        "work/spikes",
    ]:
        (pdir / subdir).mkdir(parents=True, exist_ok=True)

    title = display_title(project)
    repo_text = str(repo) if repo else ""
    cname = collection_name(project)

    write_new(
        pdir / "README.md",
        f"""# {title}

## Purpose

Describe what this project is for.

## Repository

{repo_text}

## qmd

- Collection: `{cname}`
- Memory path: `{pdir}`

## Entry Points

- Current state: [active.md](active.md)
- Product overview: [overviews/product.md](overviews/product.md)
- Architecture overview: [overviews/architecture.md](overviews/architecture.md)
- Delivery overview: [overviews/delivery.md](overviews/delivery.md)
- Decision overview: [overviews/decisions.md](overviews/decisions.md)

## Domains

Add stable system/product domains under `domains/`.

## Work

- Epics: `work/epics/`
- Stories: `work/stories/`
- Tasks: `work/tasks/`
- Spikes: `work/spikes/`
""",
    )
    write_new(
        pdir / "active.md",
        f"""# Active Context

## Objective

Establish project memory for {title}.

## Current Phase

setup

## Current Focus

- Initialize memory-bank structure.
- Register qmd collections.

## Open Questions

- What domains should this project track first?
- What work item should become active first?

## Next Actions

1. Fill in project purpose and overview files.
2. Add domains as they become useful.
3. Create a work item for active work.

## Resume Query

qmd query -c {cname} "current active work for {title}"

## Last Updated

{today()} by agent
""",
    )

    overview_templates = {
        "product.md": "Route to product surfaces, user workflows, feature specs, and non-goals.",
        "architecture.md": "Route to domain architecture docs, cross-domain flows, and technical constraints.",
        "delivery.md": "Route to active initiatives, milestones, release notes, testing, and deployment context.",
        "decisions.md": "Route to durable project, domain, and work-item decisions.",
    }
    for filename, purpose in overview_templates.items():
        write_new(
            pdir / "overviews" / filename,
            f"""# {filename[:-3].title()} Overview

## Purpose

{purpose}

## Canonical Links

- Project active context: [../active.md](../active.md)

## Notes

- Add links as docs become real.
""",
        )

    append_once(
        root / "registry.md",
        f"projects/{project}/README.md",
        f"""### {title}

- Path: [projects/{project}/README.md](projects/{project}/README.md)
- Repo: `{repo_text}`
- qmd collection: `{cname}`
""",
    )
    upsert_collection(root, project, pdir, cname, repo_text)
    write_project_collection_manifest(pdir, project, cname, repo_text)

    print(f"Initialized project memory: {pdir}")
    print("Suggested memory-bank setup command:")
    print(f"  memory_bank.py setup-qmd --root {root} --project {project}")


def resolve_project(args: argparse.Namespace) -> None:
    root = expand(args.root)
    repo = normalize_path(args.repo) or current_git_root()
    if not repo:
        raise SystemExit("Provide --repo or run from inside a git repository")

    data = parse_collections(root / ".memory-bank" / "collections.yaml")
    matches = []
    for name, fields in data.items():
        if fields.get("kind") != "project":
            continue
        if normalize_path(fields.get("repo")) == repo:
            matches.append((name, fields))

    if not matches:
        raise SystemExit(f"No memory-bank project maps to repo: {repo}")
    if len(matches) > 1:
        names = ", ".join(name for name, _ in matches)
        raise SystemExit(f"Multiple memory-bank projects map to repo {repo}: {names}")

    name, fields = matches[0]
    memory_path = Path(fields.get("path", ""))
    payload = {
        "project": fields.get("project", ""),
        "collection": name,
        "memory_path": fields.get("path", ""),
        "repo": repo,
        "context": fields.get("context", ""),
        "read_first": [
            str(memory_path / ".memory-bank" / "collection.yaml"),
            str(memory_path / "README.md"),
            str(memory_path / "active.md"),
        ],
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Project: {payload['project']}")
        print(f"Collection: {payload['collection']}")
        print(f"Memory path: {payload['memory_path']}")
        print(f"Repo: {payload['repo']}")
        print("Read first:")
        for path in payload["read_first"]:
            print(f"  {path}")
