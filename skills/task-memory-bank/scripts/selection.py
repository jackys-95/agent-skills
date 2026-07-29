#!/usr/bin/env python3
"""Project selection: discover banks, gather & rank candidate projects, read work status.

This is the core library beneath the memory_bank CLI. It answers "which project is
this repo?" the declaration-led way (design Decision 2/3): it never returns a single
silent verdict — it gathers *ranked candidates* across every memory bank on the
machine and hands them to the prose selection judgment. It also owns the closed
work-item vocabulary the ranker sorts on and the `work/index.md` status table.

Layering: memory_bank.py (CLI + file scaffolding) imports this; this imports only
the stdlib and collections_yaml (routing config I/O). Keeping the pure logic here —
git signals, qmd-derived bank discovery, ranking, work-index (re)generation, and the
candidate-gathering core — keeps memory_bank.py a thin orchestrator and lets this be
unit-tested without argparse. See docs/task-memory-bank-knowledge-retrieval-design.md.
"""

from __future__ import annotations

import datetime as dt
import re
import subprocess
from pathlib import Path

from collections_yaml import parse_collections


# --- path helpers (shared leaf; memory_bank imports these) -----------------

def expand(path: str) -> Path:
    return Path(path).expanduser().resolve()


def normalize_path(path: str | None) -> str:
    if not path:
        return ""
    return str(expand(path))


def display_title(slug_or_title: str) -> str:
    return slug_or_title.replace("_", " ").replace("-", " ").strip().title()


# --- work-item vocabulary (the type the ranker sorts on) -------------------

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
# open) is the ranker's concern (see resume_sort_key), deliberately not fixed here.
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

# Resume priority — how the ranker orders statuses when picking what to resume.
# Distinct from WORK_STATUS_ORDER (lifecycle order): a naive ascending lifecycle
# sort puts `open` (0) above `in-progress` (1), but for resume the most-resumable
# work must come first. Order: actively in flight, then deliberately parked (you
# can pick it straight back up), then externally blocked (stuck until a dependency
# clears), then not-yet-started, then terminal. The lifecycle ordinal above must
# not be used for resume sorting; this is the resume consumer's key. Exact weights
# are a deferred design decision — this is a revisable sensible-default.
RESUME_STATUS_ORDER = {
    "in-progress": 0,
    "paused": 1,
    "blocked": 2,
    "open": 3,
    "done": 4,
    "shipped": 4,
    "cancelled": 4,
    "superseded": 4,
}

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

_WORST_RESUME = max(RESUME_STATUS_ORDER.values()) + 1


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


def resume_sort_key(status: str) -> int:
    """Resume priority of a WorkStatus (lower = more resumable). Unknown → last."""
    return RESUME_STATUS_ORDER.get(status, _WORST_RESUME)


# --- git repo signals ------------------------------------------------------

def _git(start: str, *rev_parse_args: str) -> str:
    """Run `git -C <start> rev-parse <args>` and return stripped stdout ("" on error)."""
    result = subprocess.run(
        ["git", "-C", start, "rev-parse", *rev_parse_args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def git_repo_signals(start: str) -> list[str]:
    """Normalized repo paths that identify `start` for candidate matching.

    Returns the current worktree's toplevel *and*, when `start` is a linked Git
    worktree, its canonical main-worktree path — so a sibling worktree ranks the
    same declared project as its main checkout instead of resolving to nothing
    (design Decision 1: project is a declared effort, not a location). Deduped,
    symlink-resolved via `expand`. Empty when `start` is not inside a git repo.
    """
    signals: list[str] = []
    top = _git(start, "--show-toplevel")
    if top:
        signals.append(str(expand(top)))

    # --git-common-dir points at the *main* repo's `.git` for a linked worktree
    # (and at a plain `.git` for the main worktree itself). When it names a
    # `.git` dir, its parent is the canonical main-worktree path. Git returns this
    # relative to the `-C` dir (`start`) — e.g. `../.git` from a subdir — so a
    # relative value is resolved against `start`, never `top`.
    common = _git(start, "--git-common-dir")
    if common:
        cpath = Path(common)
        if not cpath.is_absolute():
            cpath = Path(start) / cpath
        cpath = cpath.resolve()
        if cpath.name == ".git":
            main = str(expand(str(cpath.parent)))
            if main not in signals:
                signals.append(main)
    return signals


# --- qmd-derived bank discovery --------------------------------------------

def _run_qmd(*qmd_args: str) -> str | None:
    """Run a read-only `qmd` subcommand; return stdout, or None if qmd is absent/failed."""
    try:
        result = subprocess.run(
            ["qmd", *qmd_args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


_QMD_MB_NAME_RE = re.compile(r"^(mb-[A-Za-z0-9._-]+)\b")
_QMD_SHOW_PATH_RE = re.compile(r"^\s*Path:\s*(.+?)\s*$")


def find_bank_root(project_path: str | Path) -> Path | None:
    """Walk up from a project dir to the bank root holding `.memory-bank/collections.yaml`."""
    p = expand(str(project_path))
    for cur in (p, *p.parents):
        if (cur / ".memory-bank" / "collections.yaml").exists():
            return cur
    return None


def discover_bank_roots() -> list[Path]:
    """Enumerate memory-bank roots from qmd's own collection catalog (design Decision 3/7).

    qmd-derived, not a hand-maintained roots list: read `qmd collection list`,
    keep the `mb-*` collections, resolve each one's filesystem path via
    `qmd collection show`, and walk up to the nearest `.memory-bank/collections.yaml`.
    This lets `gather_candidates` union candidates across every bank on the machine
    (the multi-bank fold) without a config file that could silently drift — a
    project unreachable by qmd is already broken. Returns [] when qmd is
    unavailable, so callers fall back to the `--root`/cwd bank.
    """
    listing = _run_qmd("collection", "list")
    if listing is None:
        return []
    names: list[str] = []
    for line in listing.splitlines():
        m = _QMD_MB_NAME_RE.match(line)
        if m:
            names.append(m.group(1))

    roots: list[Path] = []
    seen: set[str] = set()
    for name in names:
        shown = _run_qmd("collection", "show", name)
        if shown is None:
            continue
        for line in shown.splitlines():
            pm = _QMD_SHOW_PATH_RE.match(line)
            if not pm:
                continue
            root = find_bank_root(pm.group(1))
            if root and str(root) not in seen:
                seen.add(str(root))
                roots.append(root)
            break
    return roots


def enumerate_banks(explicit_root: Path) -> list[Path]:
    """Bank roots to search: qmd-discovered ∪ the explicit `--root` (deduped, ordered).

    Discovery is qmd-derived (design Decision 3/7); the explicit `--root` is always
    included so a bank qmd has not indexed yet is still searched and the caller
    degrades cleanly when qmd is absent.
    """
    banks: list[Path] = []
    seen: set[str] = set()
    for root in [explicit_root, *discover_bank_roots()]:
        key = str(root)
        if key not in seen and (root / ".memory-bank" / "collections.yaml").exists():
            seen.add(key)
            banks.append(root)
    return banks


# --- work-item status + index ----------------------------------------------

WORK_INDEX_HEADER = (
    "# Work Index\n\n"
    "| ID | Type | Status | Title | Created |\n"
    "| --- | --- | --- | --- | --- |\n"
)

_STATUS_HEADING_RE = re.compile(r"^##+\s+status\s*$", re.IGNORECASE)
_WID_RE = re.compile(r"^(EPIC|STORY|TASK|SPIKE)-(\d+)-(.*)$")
_TITLE_RE = re.compile(r"^#\s+\S+:\s*(.+?)\s*$")
_PREFIX_TO_TYPE = {"EPIC": "epic", "STORY": "story", "TASK": "task", "SPIKE": "spike"}


def read_work_item(wdir: Path) -> dict[str, object] | None:
    """Read one work item's facts (id, type, status, title, updated) from its README.

    Status is the first non-blank line under the `## Status` heading; off-vocabulary
    or missing values fall back to `open` (a hand-edit that skipped write validation —
    status is validated only on the write path). Title prefers the README `# WID: title`
    line, else the slug. `updated` is the README's mtime, used only as the recency
    tiebreaker (Decision 9), not authority.
    """
    name_match = _WID_RE.match(wdir.name)
    if not name_match:
        return None
    prefix, num, slug = name_match.groups()
    wid = f"{prefix}-{num}"
    work_type = _PREFIX_TO_TYPE[prefix]

    readme = wdir / "README.md"
    status = "open"
    title = display_title(slug)
    updated = 0.0
    if readme.exists():
        updated = readme.stat().st_mtime
        lines = readme.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            tm = _TITLE_RE.match(line)
            if tm and title == display_title(slug):
                title = tm.group(1)
            if _STATUS_HEADING_RE.match(line.strip()):
                for follow in lines[i + 1:]:
                    if follow.strip():
                        candidate = follow.strip().strip("`").lower()
                        status = candidate if candidate in WORK_STATUS_ORDER else "open"
                        break
    return {
        "id": wid,
        "type": work_type,
        "status": status,
        "title": title,
        "updated": updated,
        "slug": slug,
    }


def scan_work_items(pdir: Path) -> list[dict[str, object]]:
    """All work items under `work/{epics,stories,tasks,spikes}/`, sorted by resume priority."""
    items: list[dict[str, object]] = []
    for _prefix, plural in WORK_TYPES.values():
        wroot = pdir / "work" / plural
        if not wroot.exists():
            continue
        for child in sorted(wroot.iterdir()):
            if child.is_dir():
                item = read_work_item(child)
                if item:
                    items.append(item)
    items.sort(key=lambda it: (resume_sort_key(str(it["status"])), -float(it["updated"]), str(it["id"])))
    return items


def regen_work_index(pdir: Path) -> Path:
    """Regenerate `work/index.md` from the work items on disk (Decision 9, resume-ordered)."""
    index = pdir / "work" / "index.md"
    rows = [
        f"| {it['id']} | {it['type']} | {it['status']} | {it['title']} | "
        f"{dt.date.fromtimestamp(float(it['updated'])).isoformat() if it['updated'] else ''} |\n"
        for it in scan_work_items(pdir)
    ]
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text(WORK_INDEX_HEADER + "".join(rows), encoding="utf-8")
    return index


def append_work_index_row(pdir: Path, wid: str, work_type: str, status: str, title: str) -> None:
    """Surface a newly-created work item's status in `work/index.md` (design Decision 9).

    Appends one row, creating the file with a header if absent. Full deterministic
    (re)generation of the index is `regen_work_index`; this keeps the flat status
    table current as items are created, matching the manual step in workflows.md.
    """
    index = pdir / "work" / "index.md"
    row = f"| {wid} | {work_type} | {status} | {title} | {dt.date.today().isoformat()} |\n"
    if not index.exists():
        index.parent.mkdir(parents=True, exist_ok=True)
        index.write_text(WORK_INDEX_HEADER + row, encoding="utf-8")
        return
    current = index.read_text(encoding="utf-8")
    if f"| {wid} |" in current:  # idempotent: do not duplicate an existing row
        return
    index.write_text(current.rstrip("\n") + "\n" + row, encoding="utf-8")


# --- candidate gathering (pure; the deterministic spine) -------------------

def _read_first(project_path: str) -> list[str]:
    """Entrypoint files to read before broad search (per-project collection.yaml is dropped)."""
    base = Path(project_path)
    return [str(base / "README.md"), str(base / "active.md")]


def gather_candidates(signal_set: set[str], banks: list[Path]) -> dict[str, object]:
    """Rank candidate projects for the given repo signals across the given banks.

    The deterministic fact-gathering spine (design Decision 9), free of argparse
    and printing so it is directly testable. Unions candidates whose observed
    `repos:` intersect `signal_set` across every bank, joins each with its
    work-item statuses, and sorts by (resume status, association, recency). Returns
    a payload dict: `searched_banks` (per-bank project/repo counts for the
    self-diagnosing empty case), `conflict` (>1 candidate), and ranked `candidates`.
    Never raises on zero/many — multiplicity is the normal return.
    """
    candidates: list[dict[str, object]] = []
    bank_reports: list[dict[str, object]] = []

    for bank in banks:
        data = parse_collections(bank / ".memory-bank" / "collections.yaml")
        project_count = 0
        repo_count = 0
        for name, fields in data.items():
            if fields.get("kind") != "project":
                continue
            project_count += 1
            repos = [normalize_path(r) for r in (fields.get("repos") or []) if r]
            repo_count += len(repos)
            associated = signal_set.intersection(repos)
            if not associated:
                continue
            pdir = str(fields.get("path", ""))
            work = scan_work_items(Path(pdir)) if pdir else []
            active_work = [w for w in work if str(w["status"]) not in TERMINAL_STATUSES]
            top_status = str(active_work[0]["status"]) if active_work else ""
            latest = max((float(w["updated"]) for w in work), default=0.0)
            candidates.append({
                "project": fields.get("project", ""),
                "collection": name,
                "memory_path": pdir,
                "context": fields.get("context", ""),
                "description": fields.get("description", ""),
                "bank_root": str(bank),
                "matched_repos": sorted(associated),
                "association_count": len(associated),
                "top_status": top_status,
                "active_work": [
                    {"id": w["id"], "type": w["type"], "status": w["status"], "title": w["title"]}
                    for w in active_work
                ],
                "recency": latest,
                "read_first": _read_first(pdir),
            })
        bank_reports.append({
            "bank_root": str(bank),
            "projects": project_count,
            "repos": repo_count,
        })

    # Deterministic sort: most-resumable status, then strongest association, then
    # most-recently-touched, then collection name for a stable tiebreak.
    candidates.sort(key=lambda c: (
        resume_sort_key(str(c["top_status"])) if c["top_status"] else _WORST_RESUME,
        -int(c["association_count"]),
        -float(c["recency"]),
        str(c["collection"]),
    ))

    return {
        "repo_signals": sorted(signal_set),
        "searched_banks": bank_reports,
        "conflict": len(candidates) > 1,
        "candidates": candidates,
    }
