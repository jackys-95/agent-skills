#!/usr/bin/env python3
"""Scaffold and maintain a qmd-backed task memory bank."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path


WORK_TYPES = {
    "epic": ("EPIC", "epics"),
    "story": ("STORY", "stories"),
    "task": ("TASK", "tasks"),
    "spike": ("SPIKE", "spikes"),
}


def expand(path: str) -> Path:
    return Path(path).expanduser().resolve()


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9_-]+", "-", value)
    value = re.sub(r"-{2,}", "-", value)
    return value.strip("-_") or "item"


def display_title(slug_or_title: str) -> str:
    return slug_or_title.replace("_", " ").replace("-", " ").strip().title()


def today() -> str:
    return dt.date.today().isoformat()


def write_new(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(content.rstrip() + "\n", encoding="utf-8")


def append_once(path: Path, marker: str, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if marker in current:
            return
        path.write_text(current.rstrip() + "\n\n" + content.rstrip() + "\n", encoding="utf-8")
    else:
        path.write_text(content.rstrip() + "\n", encoding="utf-8")


def project_dir(root: Path, project: str) -> Path:
    return root / "projects" / project


def collection_name(project: str) -> str:
    return "mb-" + project.replace("_", "-")


def normalize_path(path: str | None) -> str:
    if not path:
        return ""
    return str(expand(path))


def current_git_root() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if result.returncode != 0:
        return ""
    return str(expand(result.stdout.strip()))


def parse_collections(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    collections: dict[str, dict[str, str]] = {}
    current: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.lstrip().startswith("#") or line == "collections:":
            continue
        top_match = re.match(r"^  ([A-Za-z0-9_.-]+):\s*$", line)
        if top_match:
            current = top_match.group(1)
            collections[current] = {}
            continue
        kv_match = re.match(r"^    ([A-Za-z0-9_.-]+):\s*(.*)\s*$", line)
        if kv_match and current:
            key, value = kv_match.groups()
            collections[current][key] = value.strip().strip("\"'")
    return collections


def write_collections(path: Path, collections: dict[str, dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["collections:"]
    for name, fields in collections.items():
        lines.append(f"  {name}:")
        for key, value in fields.items():
            lines.append(f"    {key}: {value}")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


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

    print(f"Initialized project memory: {pdir}")
    print(f"Suggested qmd commands:")
    print(f"  qmd collection add {pdir} --name {cname}")
    print(f"  qmd context add {project} {pdir / 'README.md'}")


def upsert_collection(root: Path, project: str, pdir: Path, cname: str, repo: str) -> None:
    collections = root / ".memory-bank" / "collections.yaml"
    data = parse_collections(collections)
    data.setdefault(
        "task-memory-bank",
        {
            "path": str(root),
            "mode": "recursive",
            "kind": "global",
        },
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


def resolve_project(args: argparse.Namespace) -> None:
    root = expand(args.root)
    repo = normalize_path(args.repo) or current_git_root()
    if not repo:
        raise SystemExit("Provide --repo or run from inside a git repository")

    collections_path = root / ".memory-bank" / "collections.yaml"
    data = parse_collections(collections_path)
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
    payload = {
        "project": fields.get("project", ""),
        "collection": name,
        "memory_path": fields.get("path", ""),
        "repo": repo,
        "context": fields.get("context", ""),
        "read_first": [
            str(Path(fields.get("path", "")) / "README.md"),
            str(Path(fields.get("path", "")) / "active.md"),
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


def next_id(work_root: Path, prefix: str) -> str:
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


def reindex(args: argparse.Namespace) -> None:
    for command in (["qmd", "update"], ["qmd", "embed"]):
        print("+ " + " ".join(command))
        result = subprocess.run(command, check=False)
        if result.returncode != 0:
            raise SystemExit(result.returncode)


def doctor(args: argparse.Namespace) -> None:
    root = expand(args.root)
    problems = []
    warnings = []
    if not root.exists():
        problems.append(f"Missing root: {root}")
    if not (root / "registry.md").exists():
        problems.append("Missing registry.md")
    if not (root / ".memory-bank" / "collections.yaml").exists():
        problems.append("Missing .memory-bank/collections.yaml")
    else:
        collections = parse_collections(root / ".memory-bank" / "collections.yaml")
        for name, fields in collections.items():
            if fields.get("kind") == "project":
                for key in ("path", "project", "repo", "context"):
                    if not fields.get(key):
                        problems.append(f"Collection {name} is missing {key}")
                if fields.get("path") and not expand(fields["path"]).exists():
                    problems.append(f"Collection {name} path does not exist: {fields['path']}")
                if fields.get("repo") and not expand(fields["repo"]).exists():
                    warnings.append(f"Collection {name} repo does not exist on this machine: {fields['repo']}")
    qmd = subprocess.run(["qmd", "--help"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if qmd.returncode != 0:
        problems.append("qmd CLI is unavailable")
    if problems:
        print("Problems:")
        for problem in problems:
            print(f"- {problem}")
        raise SystemExit(1)
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")
    print("Memory bank looks structurally healthy.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init-project", help="Initialize project memory structure")
    p.add_argument("--root", required=True)
    p.add_argument("--project", required=True)
    p.add_argument("--repo")
    p.set_defaults(func=init_project)

    p = sub.add_parser("new-work", help="Create an epic/story/task/spike")
    p.add_argument("--root", required=True)
    p.add_argument("--project", required=True)
    p.add_argument("--type", required=True, choices=sorted(WORK_TYPES))
    p.add_argument("--title", required=True)
    p.add_argument("--id")
    p.add_argument("--domain")
    p.set_defaults(func=new_work)

    p = sub.add_parser("resolve-project", help="Resolve current or provided git repo to memory project")
    p.add_argument("--root", required=True)
    p.add_argument("--repo")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=resolve_project)

    p = sub.add_parser("branch-work", help="Create an attempt under a work item")
    p.add_argument("--work", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--reason")
    p.set_defaults(func=branch_work)

    p = sub.add_parser("append-history", help="Append a session history entry")
    p.add_argument("--work", required=True)
    p.add_argument("--summary")
    p.add_argument("--summary-file")
    p.set_defaults(func=append_history)

    p = sub.add_parser("reindex", help="Run qmd update and qmd embed")
    p.set_defaults(func=reindex)

    p = sub.add_parser("doctor", help="Check memory-bank structure and qmd availability")
    p.add_argument("--root", required=True)
    p.set_defaults(func=doctor)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
