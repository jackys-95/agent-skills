#!/usr/bin/env python3
"""List and search prior Pi agent session logs.

This is research tooling, not production adapter behavior. Pi stores every
session as JSONL under ``~/.pi/agent/sessions/<encoded-cwd>/*.jsonl`` (see the
session-format docs; the per-record schema is the same one
``pi_session_stats.py`` works from). Pi's own discovery is interactive only —
``/resume`` and ``pi -r`` are TTY pickers, and ``pi --session <path|id>`` needs
the path or ID you are trying to find — so this script is the shell-side
counterpart: a way to find the session file and hand it to the other probes
without opening a TUI.

Two modes:

* **List** (no query): one line per session, newest first — start time,
  project, assistant turns, output tokens, models, and a title (the session
  name set via ``/name`` or ``--name`` when present, otherwise the first user
  prompt).
* **Search** (with a query): case-insensitive substring match over user
  prompts and assistant text (``--regex`` for patterns), printing every
  matching line with its timestamp, role, and the session file. Results are
  grouped by session, newest session first (so ``head -n 1`` on
  ``--paths-only`` means the newest match).
* **Compare** (``--compare``): run the full ``pi_session_stats`` summary over
  each session selected by the list filters and print a side-by-side
  throughput table — turns, model working time, output tokens, the
  duration-weighted and per-turn-median tok/s, reasoning share, and
  truncation count. All rates are client wall-clock measurements (the stats
  probe's caveat applies); comparison across sessions is only meaningful when
  the same model is in use, which the models column makes visible.

Examples::

    pi_sessions.py                          # list recent sessions, all projects
    pi_sessions.py --project agent-skills   # one project (substring on cwd)
    pi_sessions.py --since 2026-08-01 --limit 50
    pi_sessions.py "truncat"                # full-text search
    pi_sessions.py --regex "hit the max.*ceiling"
    # hand the newest match straight to the stats probe:
    pi_sessions.py --paths-only "throughput" | head -n 1 | xargs pi_session_stats.py
    # throughput across the last five sessions of a project, no bash loop:
    pi_sessions.py --project agent-skills --limit 5 --compare
    pi_sessions.py --project agent-skills --limit 5 --compare --json
    pi_sessions.py --json | jq '.[0].path'
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys
from typing import TypedDict, cast

DESCRIPTION = "List and search prior Pi agent session logs."

DEFAULT_ROOT = pathlib.Path.home() / ".pi" / "agent" / "sessions"
EXCERPT_CHARS = 120


# --------------------------------------------------------------------------
# Session log schema. Same source and same caveats as pi_session_stats.py:
# derived from real logs, asserted not validated, read defensively with
# ``.get()`` so a drifted schema degrades to missing data rather than a crash.
# --------------------------------------------------------------------------


class _RecordHeader(TypedDict):
    """Fields present on every record."""

    type: str
    id: str
    timestamp: str


class Record(_RecordHeader, total=False):
    """``type`` is "session", "session_info", "message",
    "thinking_level_change", "model_change", or "compaction"."""

    cwd: str
    name: str
    message: object


class SessionInfo(TypedDict):
    """One session file, as shown in the listing.

    ``started``/``project``/``name`` come from header records; the counts come
    from scanning assistant messages. All are best-effort: a truncated or
    partially written file still yields what was read.
    """

    path: str
    project: str
    session_id: str
    started: str
    named: bool
    assistant_turns: int
    output_tokens: int
    models: list[str]
    title: str


class Match(TypedDict):
    """One searched line in one session."""

    path: str
    started: str
    project: str
    timestamp: str
    role: str
    text: str


def parse_ts(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def _load_records(path: pathlib.Path) -> list[Record]:
    records: list[Record] = []
    for line in path.read_text(errors="replace").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            decoded = cast(object, json.loads(stripped))
        except json.JSONDecodeError:
            continue
        if (
            isinstance(decoded, dict)
            and {"type", "id", "timestamp"} <= decoded.keys()
        ):
            records.append(cast(Record, cast(object, decoded)))
    return records


def _message_text(message: object) -> str:
    """Concatenated ``text`` blocks of one message (user or assistant)."""
    if not isinstance(message, dict):
        return ""
    raw = message.get("content")
    if not isinstance(raw, list):
        return ""
    parts: list[str] = []
    for block in raw:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


def _flatten(value: object) -> str:
    """One line of search text per message: prompt or answer, no tool args."""
    return " ".join(_message_text(value).split())


def _project_started(records: list[Record], path: pathlib.Path) -> tuple[str, str]:
    """(project, started) for one session file. The ``session`` header record is
    authoritative; a truncated file falls back to the first record's timestamp,
    and the directory name stands in when the project cannot be read."""
    header = next((r for r in records if r.get("type") == "session"), None)
    project = ""
    started = ""
    if header is not None:
        cwd = header.get("cwd")
        project = pathlib.Path(cwd).name if isinstance(cwd, str) else ""
        started = header["timestamp"]
    if not started and records:
        started = records[0]["timestamp"]
    return project or path.parent.name, started


def _title(records: list[Record]) -> tuple[str, bool]:
    """Session name if one was set, else the first user prompt; plus whether it
    was an explicit name (so the listing can flag it).

    The name is the *latest* ``session_info`` entry with one — pi's own
    display-name lookup works the same way, so a renamed session shows the new
    name here too."""
    name = ""
    for record in records:
        if record.get("type") == "session_info":
            candidate = record.get("name")
            if isinstance(candidate, str) and candidate.strip():
                name = candidate.strip()
    if name:
        return name, True
    for record in records:
        if record.get("type") != "message":
            continue
        message = record.get("message")
        if isinstance(message, dict) and message.get("role") == "user":
            text = _flatten(message)
            if text:
                return text[:EXCERPT_CHARS], False
    return "(no prompts)", False


def _excerpts(records: list[Record]) -> list[tuple[str, str, str]]:
    """(timestamp, role, flattened text) for every user/assistant message."""
    out: list[tuple[str, str, str]] = []
    for record in records:
        if record.get("type") != "message":
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role not in ("user", "assistant"):
            continue
        text = _flatten(message)
        if text:
            out.append((record["timestamp"], str(role), text))
    return out


def summarize_session(path: pathlib.Path) -> SessionInfo:
    records = _load_records(path)

    project, started = _project_started(records, path)
    session_id = path.stem.split("_")[-1]
    header = next((r for r in records if r.get("type") == "session"), None)
    if header is not None:
        session_id = header.get("id") or session_id

    title, titled = _title(records)
    assistant_turns = 0
    output_tokens = 0
    models: list[str] = []
    for record in records:
        if record.get("type") != "message":
            continue
        message = record.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        assistant_turns += 1
        usage = message.get("usage")
        if isinstance(usage, dict):
            output_tokens += int(usage.get("output") or 0)
        model = message.get("model")
        if isinstance(model, str) and model not in models:
            models.append(model)

    return SessionInfo(
        path=str(path),
        project=project,
        session_id=session_id,
        started=started,
        named=titled,
        assistant_turns=assistant_turns,
        output_tokens=output_tokens,
        models=models,
        title=title,
    )


def _session_files(root: pathlib.Path, project: str | None) -> list[pathlib.Path]:
    if not root.is_dir():
        raise SystemExit(f"no sessions directory at {root}")
    files: list[pathlib.Path] = []
    for project_dir in sorted(root.iterdir()):
        if not project_dir.is_dir():
            continue
        if project and project.lower() not in project_dir.name.lower():
            continue
        files.extend(sorted(project_dir.glob("*.jsonl")))
    return files


def _in_range(started: str, since: dt.date | None, until: dt.date | None) -> bool:
    if not started:
        return False
    try:
        day = parse_ts(started).date()
    except ValueError:
        return False
    if since and day < since:
        return False
    if until and day > until:
        return False
    return True


def _parse_day(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not a YYYY-MM-DD date: {value}") from exc


def _search_match(text: str, query: str, pattern: re.Pattern[str] | None) -> bool:
    if pattern is not None:
        return pattern.search(text) is not None
    return query.lower() in text.lower()


def search_sessions(
    files: list[pathlib.Path],
    query: str,
    pattern: re.Pattern[str] | None,
    since: dt.date | None,
    until: dt.date | None,
) -> list[Match]:
    # Collected per session, then emitted newest-session-first (line order
    # inside a session is preserved) so `head -n 1` on --paths-only means
    # "newest match", matching the listing order.
    per_session: list[tuple[str, str, str, list[Match]]] = []
    for path in files:
        records = _load_records(path)
        project, started = _project_started(records, path)
        if not _in_range(started, since, until):
            continue
        hits: list[Match] = []
        for timestamp, role, text in _excerpts(records):
            if _search_match(text, query, pattern):
                hits.append(
                    Match(
                        path=str(path),
                        started=started,
                        project=project,
                        timestamp=timestamp,
                        role=role,
                        text=text[:EXCERPT_CHARS],
                    )
                )
        if hits:
            per_session.append((started, str(path), project, hits))

    matches: list[Match] = []
    for _started, _path, _project, hits in sorted(
        per_session, key=lambda item: item[0], reverse=True
    ):
        matches.extend(hits)
    return matches


def render_listing(infos: list[SessionInfo]) -> None:
    for info in infos:
        when = info["started"][:16].replace("T", " ")
        models = ",".join(info["models"]) or "-"
        title = info["title"]
        suffix = "  [named]" if info["named"] else ""
        print(
            f"{when}Z  {info['project']:<24} {info['assistant_turns']:>3}t  "
            f"{info['output_tokens']:>7}tok  {models:<28} {title}{suffix}"
        )
        print(f"          {info['path']}")


def render_compare(infos: list[SessionInfo], as_json: bool) -> int:
    """Side-by-side throughput table: the pi_session_stats summary per session.

    Imports the sibling probe rather than re-deriving the numbers: one
    definition of working time, weighted vs median rates, and the client
    wall-clock caveat they both carry.
    """
    import pi_session_stats  # sibling probe; same directory on sys.path[0]

    def _summary_for(info: SessionInfo):
        return pi_session_stats.summarize(
            pi_session_stats.load_records(pathlib.Path(info["path"]))
        )

    if as_json:
        print(
            json.dumps(
                [
                    {"session": dict(info), "stats": _summary_for(info)}
                    for info in infos
                ],
                indent=2,
            )
        )
        return 0

    print("throughput comparison : client wall-clock only -- 'w' is the")
    print("                        duration-weighted mean, 'med' the per-turn median")
    print("  started        project              turns  working   out_tok  tok/s(w)  tok/s(med)  think%  trunc  models")
    for info in infos:
        summary = _summary_for(info)
        when = info["started"][:16].replace("T", " ") + "Z"
        weight = (
            f"{summary['throughput_tok_s']:.1f}"
            if summary["throughput_tok_s"] is not None
            else "-"
        )
        median = (
            f"{summary['throughput_median_tok_s']:.1f}"
            if summary["throughput_median_tok_s"] is not None
            else "-"
        )
        share = (
            f"{summary['reasoning_share_pct']:.0f}"
            if summary["reasoning_share_pct"] is not None
            else "-"
        )
        models = ",".join(summary["models"]) or "-"
        print(
            f"  {when}  {info['project']:<18} {summary['assistant_messages']:>5}  "
            f"{summary['model_working_s']:>7.0f}s  {summary['output_tokens']:>8}  "
            f"{weight:>8}  {median:>10}  {share:>7}  {len(summary['truncations']):>5}  {models}"
        )
    return 0


def render_matches(matches: list[Match]) -> None:
    current = ""
    for match in matches:
        if match["path"] != current:
            current = match["path"]
            when = match["started"][:16].replace("T", " ")
            print(f"{when}Z  {match['project']}  {match['path']}")
        stamp = match["timestamp"][11:19]
        print(f"  {stamp}  {match['role']:<9} {match['text']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="search user prompts and assistant text (substring unless --regex)",
    )
    parser.add_argument(
        "--root",
        type=pathlib.Path,
        default=DEFAULT_ROOT,
        help=f"sessions root (default {DEFAULT_ROOT})",
    )
    parser.add_argument(
        "--project",
        metavar="NAME",
        help="only project directories whose name contains NAME (case-insensitive)",
    )
    parser.add_argument("--since", type=_parse_day, metavar="YYYY-MM-DD", help="only sessions started on/after this day")
    parser.add_argument("--until", type=_parse_day, metavar="YYYY-MM-DD", help="only sessions started on/before this day")
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        metavar="N",
        help="max sessions in a listing (default 20, 0 for all)",
    )
    parser.add_argument("--regex", action="store_true", help="treat QUERY as a case-insensitive regex")
    parser.add_argument(
        "--compare",
        action="store_true",
        help="per-session throughput table (runs the pi_session_stats summary over each selected session)",
    )
    parser.add_argument(
        "--paths-only",
        action="store_true",
        help="print only session file paths (one per line), for piping",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON (list of sessions, or matches)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.expanduser()
    as_json = cast(bool, args.json)
    paths_only = cast(bool, args.paths_only)

    if args.compare and args.query:
        raise SystemExit("--compare cannot be combined with a query; use the list filters")
    if args.regex and not args.query:
        raise SystemExit("--regex requires a query")
    try:
        pattern = (
            re.compile(args.query, re.IGNORECASE) if (args.query and args.regex) else None
        )
    except re.PatternError as exc:
        raise SystemExit(f"invalid --regex pattern: {exc}")
    files = _session_files(root, args.project)

    if args.query:
        matches = search_sessions(files, args.query, pattern, args.since, args.until)
        if paths_only:
            for path in dict.fromkeys(m["path"] for m in matches):
                print(path)
            return 0
        if as_json:
            print(json.dumps([dict(m) for m in matches], indent=2))
            return 0
        if not matches:
            print(f"no matches for {args.query!r}", file=sys.stderr)
            return 1
        render_matches(matches)
        return 0

    infos = []
    for path in files:
        info = summarize_session(path)
        if not _in_range(info["started"], args.since, args.until):
            continue
        infos.append(info)
    infos.sort(key=lambda i: i["started"], reverse=True)
    if args.limit > 0:
        infos = infos[: args.limit]

    if args.compare:
        if paths_only:
            for info in infos:
                print(info["path"])
            return 0
        return render_compare(infos, as_json)

    if paths_only:
        for info in infos:
            print(info["path"])
        return 0
    if as_json:
        print(json.dumps([dict(i) for i in infos], indent=2))
        return 0
    if not infos:
        print("no sessions found", file=sys.stderr)
        return 1
    render_listing(infos)
    return 0


if __name__ == "__main__":
    sys.exit(main())
