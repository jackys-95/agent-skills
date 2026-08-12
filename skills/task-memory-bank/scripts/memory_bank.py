#!/usr/bin/env python3
"""Scaffold and maintain a qmd-backed task memory bank."""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import collections_yaml
from collections_yaml import parse_collections, upsert_collection_block

# Selection, ranking, bank discovery, and the work-item vocabulary + index live
# in the selection module (mirrors collections_yaml's extraction): memory_bank is
# the CLI orchestrator, selection is the pure, unit-tested core. Re-export the
# shared leaf names the scaffolding paths below use.
from selection import (
    WORK_STATUSES,
    WORK_TYPES,
    append_work_index_row,
    display_title,
    enumerate_banks,
    expand,
    gather_candidates,
    git_repo_signals,
    normalize_path,
    regen_work_index,
    validate_status,
)


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9_-]+", "-", value)
    value = re.sub(r"-{2,}", "-", value)
    return value.strip("-_") or "item"


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


def mark_collection_dirty(collection: str) -> None:
    """Signal adapter lifecycle hooks without reindexing provisional writes."""
    marker_dir = Path(
        os.environ.get("TMB_REINDEX_MARKER_DIR", tempfile.gettempdir())
    ).expanduser()
    safe_name = "".join(
        c if c.isalnum() or c in "-_" else "_" for c in collection
    )
    marker_dir.mkdir(parents=True, exist_ok=True)
    (marker_dir / f"tmb_qmd_dirty_{safe_name}").write_text(
        collection,
        encoding="utf-8",
    )


def mark_memory_path_dirty(path: Path) -> None:
    """Infer a project collection from a canonical projects/<name>/ path."""
    parts = path.resolve().parts
    for index in range(len(parts) - 1, -1, -1):
        if parts[index] == "projects" and index + 1 < len(parts):
            mark_collection_dirty(collection_name(parts[index + 1]))
            return


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


def register_qmd_collection(pdir: Path, cname: str, summary: str) -> None:
    """Invoke qmd to register the project collection and attach its context.

    Closes the "config written but qmd never told" drift gap (design Decision 6 +
    Validation notes): `init-project` writes `collections.yaml` as the source of
    truth, so it must also tell qmd, or the two silently diverge.

    Always passes an explicit path + `--name` — `qmd collection add` with no
    positional arg silently creates a collection named after the cwd (observed
    while dogfooding). The context command uses the real CLI form
    `qmd context add <path> "<summary>"` with a virtual collection path, not the
    wrong `qmd context add <project> <readme-path>` this script printed before.

    Warn-and-continue on any failure (matches the SKILL.md rule that a down/absent
    qmd never blocks a markdown/config write): the caller still has valid
    `collections.yaml` + markdown; only the qmd index is behind, and the printed
    commands let the user finish registration by hand.
    """
    commands = [
        ["qmd", "collection", "add", str(pdir), "--name", cname],
        ["qmd", "context", "add", f"qmd://{cname}/", summary],
    ]
    for cmd in commands:
        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            print(
                f"warning: qmd registration step failed ({' '.join(cmd)}); "
                "collections.yaml and markdown were still written. "
                "Run the qmd commands above by hand once qmd is available."
            )
            return


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
    # `--repo` is repeatable (action="append"): a project may be seeded with more
    # than one observed repo. Normalize each to an absolute path; drop empties.
    repos = [str(expand(r)) for r in (args.repo or []) if r]
    domain = getattr(args, "domain", None)
    description = getattr(args, "description", None)
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
    # For the human-facing README/registry rendering, show the repos one per line
    # (or a placeholder when the project is repo-less — a legitimate state).
    repo_text = "\n".join(repos) if repos else ""
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
    upsert_collection(root, project, pdir, cname, repos, description, domain)

    # A generic, collection-level summary (design Validation notes: "not an
    # effort-specific one") — the `description` if the caller gave one, else a
    # template. This becomes the qmd context; editable later via `qmd context add`.
    summary = description or f"Task memory bank for the {title} project."
    register_qmd_collection(pdir, cname, summary)
    mark_collection_dirty(cname)

    print(f"Initialized project memory: {pdir}")
    print(f"Registered qmd collection {cname} (path {pdir}).")


def upsert_collection(
    root: Path,
    project: str,
    pdir: Path,
    cname: str,
    repos: list[str],
    description: str | None = None,
    domain: str | None = None,
) -> None:
    collections = root / ".memory-bank" / "collections.yaml"
    fields: dict[str, object] = {
        "path": str(pdir),
        "mode": "recursive",
        "kind": "project",
        "project": project,
        "repos": list(repos),
        "context": project,
    }
    if description:
        fields["description"] = description
    if domain:
        fields["domain"] = domain
    upsert_collection_block(collections, cname, fields)


def suggest_projects(args: argparse.Namespace) -> None:
    """CLI wrapper: gather ranked candidates for the repo, then render them.

    Judgment-free (design Decision 3/9): the ranking lives in
    `selection.gather_candidates`; this only resolves repo signals, chooses the
    banks to search, and prints (JSON or human). Never hard-exits on zero/many —
    multiplicity is the normal return for the prose selection judgment (Decision 2),
    and zero prints a self-diagnosing report naming the banks searched.
    """
    explicit_root = expand(args.root)
    repo = normalize_path(args.repo)
    signals = [repo] if repo else git_repo_signals(str(Path.cwd()))
    signal_set = {s for s in signals if s}

    banks = enumerate_banks(explicit_root)
    payload = gather_candidates(signal_set, banks)

    if args.json:
        print(json.dumps(payload, indent=2))
        return

    candidates = payload["candidates"]
    if not candidates:
        print("No candidate project maps to these repo signals.")
        print(f"Repo signals: {', '.join(payload['repo_signals']) or '(none — not in a git repo)'}")
        print("Searched banks:")
        for rep in payload["searched_banks"]:
            print(f"  {rep['bank_root']} — {rep['projects']} project(s), {rep['repos']} repo association(s)")
        if not payload["searched_banks"]:
            print("  (none discovered — is qmd installed and are banks registered?)")
        print("Declare the project explicitly (--project on writes) or register this repo.")
        return

    if payload["conflict"]:
        print(f"Multiple candidate projects ({len(candidates)}) — selection is a declaration; pick one:")
    for i, c in enumerate(candidates, 1):
        line = f"{i}. {c['project']}  [{c['collection']}]"
        if c["top_status"]:
            line += f"  status={c['top_status']}"
        print(line)
        if c["description"]:
            print(f"     {c['description']}")
        print(f"     bank: {c['bank_root']}  matched: {', '.join(c['matched_repos'])}")
        for w in c["active_work"]:
            print(f"     - {w['id']} ({w['status']}): {w['title']}")
        print(f"     read first: {', '.join(c['read_first'])}")


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

    # Accrete the repo this work item touches into the project's `repos:` list
    # (design Decision 3: associations are observed from real work, not declared).
    # Repo source mirrors suggest-projects/reindex: explicit --repo wins, else the
    # current git root; skip silently if neither resolves (a repo-less project is
    # legitimate). `append_repo` is comment-preserving and idempotent.
    repo = str(expand(args.repo)) if args.repo else current_git_root()
    if repo:
        collections = root / ".memory-bank" / "collections.yaml"
        cname = collection_name(project)
        if collections_yaml.append_repo(collections, cname, repo):
            print(f"Recorded repo association: {repo} -> {cname}")

    mark_collection_dirty(collection_name(project))
    print(f"Created {work_type}: {wdir}")


def regen_index_cmd(args: argparse.Namespace) -> None:
    root = expand(args.root)
    project = slugify(args.project)
    pdir = project_dir(root, project)
    if not pdir.exists():
        raise SystemExit(f"Project memory does not exist: {pdir}")
    index = regen_work_index(pdir)
    mark_collection_dirty(collection_name(project))
    print(f"Regenerated {index}")


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
    mark_memory_path_dirty(adir)
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
    mark_memory_path_dirty(path)
    print(f"Appended history: {path}")


def reindex(args: argparse.Namespace) -> None:
    # Explicit --collection wins: callers that already know the collection skip
    # cwd/git resolution — the cwd may not map to the target collection, and KB
    # collections have no git repo.
    requested = getattr(args, "collection", None)
    collections: list[str] = (
        [requested] if isinstance(requested, str) else list(requested or [])
    )
    root = getattr(args, "root", None)
    if not collections and root:
        repo = current_git_root()
        if repo:
            data = parse_collections(expand(root) / ".memory-bank" / "collections.yaml")
            for name, fields in data.items():
                repos = fields.get("repos") or []
                if fields.get("kind") == "project" and any(normalize_path(r) == repo for r in repos):
                    collections = [name]
                    break

    update_cmd = ["qmd", "update"]
    print("+ " + " ".join(update_cmd))
    result = subprocess.run(update_cmd, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)

    targets: list[str | None] = collections or [None]
    for collection in targets:
        embed_cmd = ["qmd", "embed"] + (["-c", collection] if collection else [])
        print("+ " + " ".join(embed_cmd))
        result = subprocess.run(embed_cmd, check=False)
        if result.returncode != 0:
            raise SystemExit(result.returncode)


_QMD_COLLECTION_RE = re.compile(r"^(\S+)\s+\(qmd://\1/\)")


def qmd_collection_names() -> set[str] | None:
    """Return the set of collections qmd knows about, or None if qmd is unavailable.

    Parses `qmd collection list`, whose entries render as
    `<name> (qmd://<name>/)`. None (not an empty set) signals "could not ask qmd"
    so the drift check can distinguish "qmd down" from "qmd has zero collections".
    """
    result = subprocess.run(
        ["qmd", "collection", "list"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if result.returncode != 0:
        return None
    names = set()
    for line in result.stdout.splitlines():
        match = _QMD_COLLECTION_RE.match(line)
        if match:
            names.add(match.group(1))
    return names


def doctor(args: argparse.Namespace) -> None:
    root = expand(args.root)
    problems = []
    warnings = []
    if not root.exists():
        problems.append(f"Missing root: {root}")
    # No registry-sync check: registry.md is a deprecated human rendering of
    # collections.yaml (design Decision 6), not a structural requirement — its
    # absence is not a fault. collections.yaml is the source of truth checked below.
    config_collections: set[str] = set()
    if not (root / ".memory-bank" / "collections.yaml").exists():
        problems.append("Missing .memory-bank/collections.yaml")
    else:
        collections = parse_collections(root / ".memory-bank" / "collections.yaml")
        for name, fields in collections.items():
            if fields.get("kind") == "project":
                config_collections.add(name)
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
    else:
        # Config-vs-qmd drift: collections.yaml is the source of truth,
        # but init-project registers with qmd separately, so a project can be
        # declared in config yet never registered with qmd — the "config written
        # but qmd never told" gap (design Validation notes). Warn (not fail): a
        # freshly scaffolded, not-yet-registered project is a legitimate transient.
        #
        # Only the config->qmd direction is checked. The reverse (a qmd collection
        # absent from *this* config) is not drift in the multi-bank model: qmd
        # indexes every bank's collections plus standalone KB collections, so this
        # bank legitimately does not know about them.
        registered = qmd_collection_names()
        if registered is not None:
            for name in sorted(config_collections - registered):
                warnings.append(
                    f"Collection {name} is in collections.yaml but not registered with qmd "
                    "(run init-project registration or `qmd collection add`)"
                )
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

    changed = False

    # 1. Root schema migration (repo: -> repos:, drop the kind: global umbrella).
    before = path.read_text(encoding="utf-8")
    after = collections_yaml.migrate_text(before)
    if before != after:
        changed = True
        if args.check:
            diff = difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=str(path),
                tofile=f"{path} (migrated)",
            )
            sys.stdout.writelines(diff)
            print(f"\n[--check] Would migrate {path}.")
        else:
            path.write_text(after, encoding="utf-8")
            print(f"Migrated {path}")

    # 2. Remove stale per-project `.memory-bank/collection.yaml` manifests. These
    # were dropped by design (Decision 6): a detached copy carries a stale
    # association snapshot. init-project no longer writes them, but banks scaffolded
    # before that still have them on disk — nothing reads them now. Remove the empty
    # `.memory-bank/` dir too, but never touch the *root* `.memory-bank/` (which
    # holds collections.yaml — a project dir named that would be pathological).
    for manifest in sorted((root / "projects").glob("*/.memory-bank/collection.yaml")):
        changed = True
        if args.check:
            print(f"[--check] Would remove stale manifest {manifest}.")
            continue
        manifest.unlink()
        print(f"Removed stale manifest {manifest}")
        mdir = manifest.parent
        if mdir != root / ".memory-bank" and not any(mdir.iterdir()):
            mdir.rmdir()

    if not changed:
        print("collections.yaml already migrated and no stale manifests; no changes.")
    elif args.check:
        print("[--check] No changes written.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "init-project",
        help="Initialize project memory structure and register it with qmd",
        description=(
            "Scaffolds projects/<project>/, writes collections.yaml as the source of "
            "truth, then invokes qmd registration (qmd collection add + qmd context add) "
            "so the config and qmd's index cannot drift. --repo is repeatable to seed "
            "more than one observed repo; --description/--domain annotate the collection."
        ),
    )
    p.add_argument("--memory-root", "--root", dest="root", required=True)
    p.add_argument("--project", required=True)
    p.add_argument(
        "--repo", action="append",
        help="Observed repo path (repeatable). Seeds the project's repos: association list.",
    )
    p.add_argument(
        "--description",
        help="Generic, collection-level summary attached as the qmd context "
             "(not effort-specific). Defaults to a template if omitted.",
    )
    p.add_argument("--domain", help="Optional domain/tag recorded in collections.yaml.")
    p.set_defaults(func=init_project)

    p = sub.add_parser("new-work", help="Create an epic/story/task/spike")
    p.add_argument("--memory-root", "--root", dest="root", required=True)
    p.add_argument("--project", required=True)
    p.add_argument("--type", required=True, choices=sorted(WORK_TYPES))
    p.add_argument("--title", required=True)
    p.add_argument("--id")
    p.add_argument("--domain")
    p.add_argument(
        "--repo",
        help="Repo this work item touches, accreted into the project's repos: "
             "association list. Defaults to the current git root if omitted.",
    )
    p.add_argument(
        "--status", choices=WORK_STATUSES, default="open",
        help="Initial WorkStatus (default: open). Validated against the closed enum.",
    )
    p.set_defaults(func=new_work)

    # suggest-projects supersedes the hard-exiting resolve-project (design
    # Decision 3/9): it returns *ranked candidates* across all discovered banks,
    # never a single silent verdict. `resolve-project` stays as a hidden alias so
    # any lingering caller keeps working through the reference-doc transition.
    for cmd in ("suggest-projects", "resolve-project"):
        p = sub.add_parser(
            cmd,
            help=(
                "Rank candidate projects for the current/declared repo across all "
                "discovered banks (no hard exit; multiplicity is normal)"
                if cmd == "suggest-projects" else argparse.SUPPRESS
            ),
            description=(
                "Gather and rank candidate projects whose observed repos: include the "
                "current (or --repo) git repo, unioned across every memory bank qmd "
                "knows about plus --root. Joins each candidate with its work-item "
                "statuses and sorts by (resume status, association, recency). Prints a "
                "self-diagnosing report (which banks were searched) when nothing matches."
            ),
        )
        p.add_argument("--memory-root", "--root", dest="root", required=True)
        p.add_argument("--repo")
        p.add_argument("--json", action="store_true")
        p.set_defaults(func=suggest_projects)

    p = sub.add_parser(
        "regen-index",
        help="Regenerate work/index.md from work items on disk",
        description=(
            "Rebuilds projects/<project>/work/index.md from the WorkStatus in each "
            "work item's README, resume-ordered. Use after hand-editing statuses so "
            "the index the ranker reads stays truthful."
        ),
    )
    p.add_argument("--memory-root", "--root", dest="root", required=True)
    p.add_argument("--project", required=True)
    p.set_defaults(func=regen_index_cmd)

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
        "--collection", "-c", dest="collection", action="append", default=None,
        help="Scope embed to this exact qmd collection, bypassing cwd/git resolution. "
             "Repeat for multiple collections; qmd update runs once.",
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
            "legacy `kind: global` umbrella block, preserving all comments. Also removes "
            "stale per-project `.memory-bank/collection.yaml` manifests (dropped by "
            "design Decision 6; nothing reads them). Idempotent. Use --check for a "
            "dry-run that writes nothing."
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
