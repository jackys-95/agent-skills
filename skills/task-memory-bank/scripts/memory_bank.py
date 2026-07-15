#!/usr/bin/env python3
"""Scaffold and maintain a qmd-backed task memory bank."""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

import collections_yaml
from collections_yaml import parse_collections, upsert_collection_block


WORK_TYPES = {
    "epic": ("EPIC", "epics"),
    "story": ("STORY", "stories"),
    "task": ("TASK", "tasks"),
    "spike": ("SPIKE", "spikes"),
}

# Closed, ordinal work-status vocabulary (design Decision 9). Replaces the
# informal `active`/`open`/`setup` mix the script used to write. The ordinal is
# lifecycle order — open → in-progress → blocked/paused → terminal — grouped to
# match the design's four tiers; statuses in the same tier share a value so a
# stable sort falls through to the next key. This supplies only the *type*: how
# the resume ranker weights it (e.g. whether a stale in-progress outranks a fresh
# open) is TASK-0003's concern, deliberately not decided here.
WORK_STATUSES = (
    "open",
    "in-progress",
    "blocked",
    "paused",
    "done",
    "shipped",
    "cancelled",
    "superseded",
)
WORK_STATUS_ORDER = {
    "open": 0,
    "in-progress": 1,
    "blocked": 2,
    "paused": 2,
    "done": 3,
    "shipped": 3,
    "cancelled": 3,
    "superseded": 3,
}
TERMINAL_STATUSES = frozenset({"done", "shipped", "cancelled", "superseded"})

# Workflow phase — a separate, non-ranking enum (design Decision 9), kept
# distinct so "status" is never re-overloaded with workflow phase. Reconciles
# two vocabulary defects: the script's stray `setup` (dropped) and `paused`
# being listed as a phase in references/structure.md (it is a WorkStatus, not a
# phase). `planned` is the plan-checkpoint state before design work begins.
PHASES = (
    "planned",
    "design",
    "specification",
    "implementation",
    "verification",
    "handoff",
)


def validate_status(value: str) -> str:
    if value not in WORK_STATUS_ORDER:
        raise SystemExit(
            f"Invalid work status {value!r}; expected one of: {', '.join(WORK_STATUSES)}"
        )
    return value


def validate_phase(value: str) -> str:
    if value not in PHASES:
        raise SystemExit(
            f"Invalid phase {value!r}; expected one of: {', '.join(PHASES)}"
        )
    return value


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


def write_project_collection_manifest(
    pdir: Path, project: str, cname: str, repo: str
) -> None:
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

## Scripts

Memory-bank scripts are installed with the task-memory-bank skill:

```bash
python3 ~/.claude/skills/task-memory-bank/scripts/memory_bank.py --help
```
""",
    )
    # No umbrella collection (Decision 5): seed only the header; project blocks
    # are added by upsert_collection. Cross-project search is multi-`-c` query,
    # not a recursive umbrella (which would double embed cost and leave stale
    # vectors). Bank-root config is never qmd-indexed.
    write_new(
        root / ".memory-bank" / "collections.yaml",
        "collections:\n",
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

planned

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

collection: {cname}
intent: resume current active work for {title}
lex: {slugify(title)} active work
vec: what context is needed to resume current work in {title}

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
    print(f"Suggested qmd commands:")
    print(f"  qmd collection add {pdir} --name {cname}")
    print(f"  qmd context add {project} {pdir / 'README.md'}")


def upsert_collection(root: Path, project: str, pdir: Path, cname: str, repo: str) -> None:
    collections = root / ".memory-bank" / "collections.yaml"
    fields: dict[str, object] = {
        "path": str(pdir),
        "mode": "recursive",
        "kind": "project",
        "project": project,
        "repos": [repo] if repo else [],
        "context": project,
    }
    upsert_collection_block(collections, cname, fields)


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
        repos = fields.get("repos") or []
        if any(normalize_path(r) == repo for r in repos):
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
            str(Path(fields.get("path", "")) / ".memory-bank" / "collection.yaml"),
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


WORK_INDEX_HEADER = (
    "# Work Index\n\n"
    "| ID | Type | Status | Title | Created |\n"
    "| --- | --- | --- | --- | --- |\n"
)


def append_work_index_row(pdir: Path, wid: str, work_type: str, status: str, title: str) -> None:
    """Surface a work item's status in `work/index.md` (design Decision 9).

    Appends one row, creating the file with a header if absent. Full
    deterministic (re)generation of the index for ranking is TASK-0003; this
    only keeps the flat status table current as items are created, matching the
    manual step documented in references/workflows.md.
    """
    index = pdir / "work" / "index.md"
    row = f"| {wid} | {work_type} | {status} | {title} | {today()} |\n"
    if not index.exists():
        index.parent.mkdir(parents=True, exist_ok=True)
        index.write_text(WORK_INDEX_HEADER + row, encoding="utf-8")
        return
    current = index.read_text(encoding="utf-8")
    if f"| {wid} |" in current:  # idempotent: do not duplicate an existing row
        return
    index.write_text(current.rstrip("\n") + "\n" + row, encoding="utf-8")


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

    status = validate_status(getattr(args, "status", None) or "open")
    domain_line = f"- Domain: `{args.domain}`" if args.domain else "- Domain:"
    write_new(
        wdir / "README.md",
        f"""# {wid}: {args.title}

## Status

{status}

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

planned

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

collection: {collection_name(project)}
intent: resume {args.title}
lex: {wid} {slug}
vec: what context is needed to resume {args.title}
hyde: The active.md for {args.title} describes the current state, next actions, and any decisions or blockers relevant to continuing this work.

## Last Updated

{today()} by agent
""",
    )
    append_work_index_row(pdir, wid, work_type, status, args.title)
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
    # Explicit --collection wins: callers that already know the collection skip
    # cwd/git resolution — the cwd may not map to the target collection, and KB
    # collections have no git repo.
    collection: str | None = getattr(args, "collection", None)
    root = getattr(args, "root", None)
    if not collection and root:
        repo = current_git_root()
        if repo:
            data = parse_collections(expand(root) / ".memory-bank" / "collections.yaml")
            for name, fields in data.items():
                repos = fields.get("repos") or []
                if fields.get("kind") == "project" and any(normalize_path(r) == repo for r in repos):
                    collection = name
                    break

    update_cmd = ["qmd", "update"]
    print("+ " + " ".join(update_cmd))
    result = subprocess.run(update_cmd, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)

    embed_cmd = ["qmd", "embed"] + (["-c", collection] if collection else [])
    print("+ " + " ".join(embed_cmd))
    result = subprocess.run(embed_cmd, check=False)
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
                for key in ("path", "project", "context"):
                    if not fields.get(key):
                        problems.append(f"Collection {name} is missing {key}")
                if fields.get("path") and not expand(str(fields["path"])).exists():
                    problems.append(f"Collection {name} path does not exist: {fields['path']}")
                # `repos` is an association list (0..N); a repo-less project is valid,
                # but a listed repo that has vanished on this machine is a warning.
                for r in (fields.get("repos") or []):
                    if r and not expand(r).exists():
                        warnings.append(f"Collection {name} repo does not exist on this machine: {r}")
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


def migrate_collections(args: argparse.Namespace) -> None:
    root = expand(args.root)
    path = root / ".memory-bank" / "collections.yaml"
    if not path.exists():
        raise SystemExit(f"Missing .memory-bank/collections.yaml under: {root}")
    before = path.read_text(encoding="utf-8")
    after = collections_yaml.migrate_text(before)
    if before == after:
        print("collections.yaml already migrated; no changes.")
        return
    if args.check:
        diff = difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=str(path),
            tofile=f"{path} (migrated)",
        )
        sys.stdout.writelines(diff)
        print(f"\n[--check] Would migrate {path}. No changes written.")
        return
    path.write_text(after, encoding="utf-8")
    print(f"Migrated {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init-project", help="Initialize project memory structure")
    p.add_argument("--memory-root", "--root", dest="root", required=True)
    p.add_argument("--project", required=True)
    p.add_argument("--repo")
    p.set_defaults(func=init_project)

    p = sub.add_parser("new-work", help="Create an epic/story/task/spike")
    p.add_argument("--memory-root", "--root", dest="root", required=True)
    p.add_argument("--project", required=True)
    p.add_argument("--type", required=True, choices=sorted(WORK_TYPES))
    p.add_argument("--title", required=True)
    p.add_argument("--id")
    p.add_argument("--domain")
    p.add_argument(
        "--status", choices=WORK_STATUSES, default="open",
        help="Initial WorkStatus (default: open). Validated against the closed enum.",
    )
    p.set_defaults(func=new_work)

    p = sub.add_parser("resolve-project", help="Resolve current or provided git repo to memory project")
    p.add_argument("--memory-root", "--root", dest="root", required=True)
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

    p = sub.add_parser(
        "reindex",
        help="Run qmd update and qmd embed",
        description=(
            "Runs `qmd update` then `qmd embed`. "
            "With --collection, scopes embed to that collection directly (qmd embed -c <name>) — "
            "no cwd/git resolution. Otherwise, with --memory-root and from inside a git repo, "
            "resolves the current project collection and scopes embed to it. "
            "With neither, rebuilds all collections globally. "
            "Does not accept --project or --repo — project is auto-detected from the git root."
        ),
    )
    p.add_argument(
        "--collection", "-c", dest="collection", required=False, default=None,
        help="Scope embed to this exact qmd collection, bypassing cwd/git resolution. "
             "For callers that already know the target collection.",
    )
    p.add_argument(
        "--memory-root", "--root", dest="root", required=False, default=None,
        help="Memory bank root (e.g. ~/memory/task-memory-bank). "
             "When provided (and --collection is not), scopes embed to the current git repo's collection.",
    )
    p.set_defaults(func=reindex)

    p = sub.add_parser("doctor", help="Check memory-bank structure and qmd availability")
    p.add_argument("--memory-root", "--root", dest="root", required=True)
    p.set_defaults(func=doctor)

    p = sub.add_parser(
        "migrate-collections",
        help="One-time migration of collections.yaml to the repos: list schema",
        description=(
            "Converts single-string `repo:` entries to a `repos:` list and drops the "
            "legacy `kind: global` umbrella block, preserving all comments. Idempotent. "
            "Use --check for a dry-run diff that writes nothing."
        ),
    )
    p.add_argument("--memory-root", "--root", dest="root", required=True)
    p.add_argument("--check", action="store_true", help="Show the diff without writing")
    p.set_defaults(func=migrate_collections)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
