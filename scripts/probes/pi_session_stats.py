#!/usr/bin/env python3
"""Summarize a Pi agent session log for local-model evaluation runs.

This is research tooling, not production adapter behavior. Pi records each
session as JSONL with per-record timestamps but ships no timing counter, so
wall-clock, throughput, reasoning share, and truncation counts have to be
recovered from the log after the fact. This script does that recovery so the
same numbers are produced the same way on every run.

Reported metrics and how they are derived:

* **session span** -- last record timestamp minus first. Includes time the user
  spent reading and typing, so it is an upper bound, not model cost.
* **model working time** -- summed gap between each assistant message and the
  record preceding it. This is the figure to compare across runs; it excludes
  user idle time.
* **throughput** -- output tokens divided by model working time. This is the
  duration-weighted conversation mean: long turns dominate, so the whole session
  reads as one stream.
* **per-turn throughput** -- for each assistant message, that turn's output tokens
  divided by the turn's duration, where the duration is the wall-clock gap between
  the timestamp of the preceding record and the assistant record's timestamp. This
  is a **client wall-clock measurement, not a server measurement**: Pi stamps the
  log with its own local clock, and the OpenAI-compatible response from the model
  server carries token counts and stop metadata but no server-side timings (no
  prefill/decode split, no time to first token). Turn time therefore includes
  request dispatch, prefill, decode, and log write; it excludes tool execution
  (the preceding record for a tool-follow-up turn is the tool result, written
  after the tool ran). Timestamps have 1 ms resolution, so turns under ~100 ms
  carry a meaningful relative error. A per-turn median is reported alongside the
  weighted mean as the robustness check: the mean of per-turn rates would
  over-weight short turns. A turn whose *preceding record is a compaction
  entry* is flagged (``post_compaction``): its duration then spans the
  compaction's own summary-generation model call, so its tok/s is an
  underestimate and the weighted mean is dragged down by the same amount.
  Compactions are also invisible in ``output_tokens``: the summary's tokens
  live on the compaction entry's ``usage``, not on any assistant message.
* **reasoning share** -- thinking characters as a fraction of all generated
  prose. Characters, not tokens: providers frequently report ``usage.reasoning``
  as 0 even when thinking blocks are present, so a token-based share silently
  reads as zero. Character share is always available and is comparable across
  runs of the same model.
* **truncations** -- assistant messages with ``stopReason == "length"``. These
  hit the ``maxTokens`` ceiling. When such a message also carries a tool call,
  that call's arguments are cut mid-serialization and the turn is unusable;
  the summary flags this because it is the failure mode that most distorts an
  otherwise valid run.

Usage::

    pi_session_stats.py SESSION.jsonl
    pi_session_stats.py --latest ~/.pi/agent/sessions/--Users-me-repo--
    pi_session_stats.py SESSION.jsonl --json
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import pathlib
import sys
from typing import TypedDict, cast

DESCRIPTION = "Summarize a Pi agent session log for local-model evaluation runs."

TRUNCATED = "length"


# --------------------------------------------------------------------------
# Pi session schema.
#
# Pi does not publish this format, so these declarations were derived by
# enumerating every key present in real session logs (record header version 3).
# They exist for typo protection more than for type safety: every field below is
# read with ``.get()``, and a mistyped key would otherwise return ``None``
# silently and produce a plausible but wrong metric.
#
# All are ``total=False`` -- presence varies by record and message kind, and an
# unrecognized future field is ignored rather than fatal.
# --------------------------------------------------------------------------


class Cost(TypedDict, total=False):
    input: float
    output: float
    cacheRead: float
    cacheWrite: float
    total: float


class Usage(TypedDict, total=False):
    input: int
    output: int
    cacheRead: int
    cacheWrite: int
    reasoning: int  # observed as 0 on llama.cpp backends even when thinking is present
    totalTokens: int
    cost: Cost


class Block(TypedDict, total=False):
    """One content block. ``type`` is "text", "thinking", or "toolCall"."""

    type: str
    text: str
    thinking: str
    thinkingSignature: str
    id: str
    name: str
    arguments: object


class Message(TypedDict, total=False):
    """``role`` is "user", "assistant", or "toolResult"."""

    role: str
    content: list[Block]
    timestamp: str
    api: str
    provider: str
    model: str
    usage: Usage
    stopReason: str  # "stop" | "toolUse" | "length"
    rawStopReason: str
    responseId: str
    toolCallId: str
    toolName: str
    isError: bool
    details: object


class _RecordHeader(TypedDict):
    """Fields present on every record, verified across whole session logs.

    Separated from the optional half so that indexing them is checked as safe
    rather than a possible ``KeyError``.
    """

    type: str
    id: str
    timestamp: str


class Record(_RecordHeader, total=False):
    """``type`` is "session", "message", "thinking_level_change",
    "model_change", or "compaction"."""

    parentId: str
    version: int
    cwd: str
    provider: str
    modelId: str
    thinkingLevel: str
    message: Message
    summary: str
    firstKeptEntryId: str
    tokensBefore: int
    usage: Usage
    details: object
    fromHook: bool


# --------------------------------------------------------------------------
# Summary schema (this script's own output, also the shape of ``--json``).
# --------------------------------------------------------------------------


class Latency(TypedDict):
    min: float | None
    median: float | None
    max: float | None


class Truncation(TypedDict):
    timestamp: str
    output_tokens: int
    thinking_chars: int
    tool_calls_cut: list[str]


class LevelChange(TypedDict):
    timestamp: str
    level: str | None


class Turn(TypedDict):
    """One assistant message, paired with the thinking level in effect for it.

    Qwen-family chat templates inject the effort instruction into the *prompt*,
    so ``prompt_tokens`` is a deterministic tell for which level was actually
    applied — unlike output length, which is noisy at temp 1.0. Comparing turns
    that share a prompt isolates the injected text.

    ``turn_s`` and ``throughput_tok_s`` are client wall-clock figures derived from
    the log's own timestamps (see the per-turn throughput note in the module
    docstring); they are not server measurements.

    ``post_compaction`` marks turns directly preceded by a compaction entry:
    their ``turn_s`` may include the compaction's own model call.
    """

    timestamp: str
    level: str | None
    prompt_tokens: int
    output_tokens: int
    turn_s: float
    throughput_tok_s: float | None
    post_compaction: bool


class Compaction(TypedDict):
    timestamp: str
    tokens_before: int | None


class Summary(TypedDict):
    records: int
    assistant_messages: int
    session_span_s: float
    model_working_s: float
    output_tokens: int
    throughput_tok_s: float | None
    throughput_median_tok_s: float | None
    thinking_chars: int
    text_chars: int
    reasoning_share_pct: float | None
    latency_s: Latency
    stop_reasons: dict[str, int]
    models: dict[str, int]
    truncations: list[Truncation]
    thinking_levels: list[LevelChange]
    turns: list[Turn]
    compactions: list[Compaction]


def parse_ts(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_records(path: pathlib.Path) -> list[Record]:
    """Decode the JSONL, skipping unparsable lines rather than aborting.

    The ``cast`` is the one unchecked assertion in this script: the schema above
    is asserted, not validated. Every read afterwards is defensive, so a drifted
    schema degrades to missing metrics rather than a crash.
    """
    records: list[Record] = []
    for lineno, line in enumerate(path.read_text().splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            # json.loads is typed as returning Any; launder it to object at the
            # boundary so nothing downstream inherits an unchecked type.
            decoded = cast(object, json.loads(stripped))
        except json.JSONDecodeError as exc:
            print(f"{path.name}:{lineno}: skipping unparsable line ({exc})", file=sys.stderr)
            continue
        if isinstance(decoded, dict) and {"type", "id", "timestamp"} <= decoded.keys():
            # isinstance narrows to dict[Unknown, Unknown]; widen back to object
            # so the assertion to Record is a declared conversion, not a guess.
            records.append(cast(Record, cast(object, decoded)))
        elif isinstance(decoded, dict):
            print(f"{path.name}:{lineno}: skipping record with no type/id/timestamp", file=sys.stderr)
    return records


def latest_session(directory: pathlib.Path) -> pathlib.Path:
    sessions = sorted(directory.glob("*.jsonl"))
    if not sessions:
        raise SystemExit(f"no .jsonl session logs in {directory}")
    return sessions[-1]


def _blocks(message: Message) -> list[Block]:
    """Content blocks, skipping anything that is not an object.

    The schema is asserted rather than validated, so a malformed entry is
    dropped here instead of crashing on attribute access downstream.
    """
    raw = cast(object, message.get("content") or [])
    if not isinstance(raw, list):
        return []
    items = cast("list[object]", raw)
    return [cast(Block, cast(object, b)) for b in items if isinstance(b, dict)]


def _thinking_chars(blocks: list[Block]) -> int:
    return sum(len(b.get("thinking") or "") for b in blocks if b.get("type") == "thinking")


def _text_chars(blocks: list[Block]) -> int:
    return sum(len(b.get("text") or "") for b in blocks if b.get("type") == "text")


def summarize(records: list[Record]) -> Summary:
    if not records:
        raise SystemExit("empty session log")

    span = (
        parse_ts(records[-1]["timestamp"]) - parse_ts(records[0]["timestamp"])
    ).total_seconds()

    output_tokens = 0
    thinking_chars = 0
    text_chars = 0
    latencies: list[float] = []
    truncations: list[Truncation] = []
    stop_reasons: collections.Counter[str] = collections.Counter()
    models: collections.Counter[str] = collections.Counter()
    turns: list[Turn] = []
    level: str | None = None

    for index, record in enumerate(records):
        # Level changes are their own record type; the level applies to every
        # assistant message after it until the next change.
        if record.get("type") == "thinking_level_change":
            level = record.get("thinkingLevel")
        if record.get("type") != "message":
            continue
        message = record.get("message") or Message()
        if message.get("role") != "assistant":
            continue

        usage = message.get("usage") or Usage()
        turn_output = usage.get("output", 0)
        output_tokens += turn_output
        stop_reasons[str(message.get("stopReason"))] += 1
        models[str(message.get("model"))] += 1

        blocks = _blocks(message)
        thinking_chars += _thinking_chars(blocks)
        text_chars += _text_chars(blocks)

        # The preceding record is whatever the model was responding to: a user
        # message, a tool result, or a settings change. Its timestamp is the
        # closest available proxy for when generation started. Both stamps are
        # written by Pi's own clock, so the gap is client wall-clock time, not a
        # server-side measurement.
        previous = records[index - 1] if index else record
        started = parse_ts(previous["timestamp"])
        turn_s = (parse_ts(record["timestamp"]) - started).total_seconds()
        latencies.append(turn_s)

        turns.append(
            Turn(
                timestamp=record["timestamp"],
                level=level,
                prompt_tokens=usage.get("input", 0),
                output_tokens=turn_output,
                turn_s=round(turn_s, 3),
                throughput_tok_s=round(turn_output / turn_s, 1) if turn_s else None,
                post_compaction=previous.get("type") == "compaction",
            )
        )

        if message.get("stopReason") == TRUNCATED:
            truncations.append(
                Truncation(
                    timestamp=record["timestamp"],
                    output_tokens=usage.get("output", 0),
                    thinking_chars=_thinking_chars(blocks),
                    tool_calls_cut=[
                        str(b.get("name")) for b in blocks if b.get("type") == "toolCall"
                    ],
                )
            )

    working = sum(latencies)
    prose = thinking_chars + text_chars
    ordered = sorted(latencies)
    # Per-turn rates, median as the robust figure: an unweighted mean of rates
    # over-weights short turns (a tiny fast turn looks like hundreds of tok/s).
    turn_rates = sorted(
        t["output_tokens"] / t["turn_s"] for t in turns if t["turn_s"] > 0
    )
    throughput_median = (
        round(turn_rates[len(turn_rates) // 2], 1) if turn_rates else None
    )

    return Summary(
        records=len(records),
        assistant_messages=len(latencies),
        session_span_s=round(span, 1),
        model_working_s=round(working, 1),
        output_tokens=output_tokens,
        throughput_tok_s=round(output_tokens / working, 1) if working else None,
        throughput_median_tok_s=throughput_median,
        thinking_chars=thinking_chars,
        text_chars=text_chars,
        reasoning_share_pct=round(thinking_chars / prose * 100, 1) if prose else None,
        latency_s=Latency(
            min=round(ordered[0], 1) if ordered else None,
            median=round(ordered[len(ordered) // 2], 1) if ordered else None,
            max=round(ordered[-1], 1) if ordered else None,
        ),
        stop_reasons=dict(stop_reasons),
        models=dict(models),
        truncations=truncations,
        thinking_levels=[
            LevelChange(timestamp=r["timestamp"], level=r.get("thinkingLevel"))
            for r in records
            if r.get("type") == "thinking_level_change"
        ],
        turns=turns,
        compactions=[
            Compaction(timestamp=r["timestamp"], tokens_before=r.get("tokensBefore"))
            for r in records
            if r.get("type") == "compaction"
        ],
    )


def format_duration(seconds: float) -> str:
    return f"{seconds:.0f}s ({seconds / 60:.1f} min)"


def render(summary: Summary, path: pathlib.Path) -> None:
    latency = summary["latency_s"]
    counts = f"{summary['records']}  ({summary['assistant_messages']} assistant)"
    share = (
        f"{summary['reasoning_share_pct']}%  "
        f"({summary['thinking_chars']} thinking / {summary['text_chars']} answer chars)"
    )

    print(f"session          : {path.name}")
    print(f"records          : {counts}")
    print(f"session span     : {format_duration(summary['session_span_s'])}   [includes user idle]")
    print(f"model working    : {format_duration(summary['model_working_s'])}")
    print(f"output tokens    : {summary['output_tokens']}")
    print(f"throughput       : {summary['throughput_tok_s']} tok/s   [duration-weighted, client wall-clock]")
    print(f"throughput median: {summary['throughput_median_tok_s']} tok/s   [per-turn, robust to outlier turns]")
    print(f"reasoning share  : {share}")
    spread = f"median {latency['median']}s   min {latency['min']}s   max {latency['max']}s"
    print(f"latency          : {spread}")

    print()
    print("models           : " + ", ".join(f"{k} x{v}" for k, v in summary["models"].items()))
    print("stop reasons     : " + ", ".join(f"{k} x{v}" for k, v in summary["stop_reasons"].items()))

    levels = summary["thinking_levels"]
    if levels:
        print(f"thinking levels  : {len(levels)} change(s), final = {levels[-1]['level']}")

    turns = summary["turns"]
    if turns:
        print()
        print("per-turn throughput : client wall-clock only -- Pi stamps the log locally;")
        print("                     the OpenAI-compatible response carries token counts,")
        print("                     not server timings, so turn time cannot separate")
        print("                     prefill from decode. 1 ms timestamp resolution.")
        print("   timestamp   level     turn_s   prompt_tok   output_tok   tok/s")
        for turn in turns:
            stamp = turn["timestamp"][11:19]
            shown = (turn["level"] or "-")[:9]
            rate = (
                f"{turn['throughput_tok_s']:.1f}"
                if turn["throughput_tok_s"] is not None
                else "-"
            )
            mark = " *" if turn["post_compaction"] else ""
            cells = (
                f"{turn['turn_s']:>8.3f}   {turn['prompt_tokens']:>10}   "
                f"{turn['output_tokens']:>10}   {rate:>7}{mark}"
            )
            print(f"   {stamp}   {shown:<9} {cells}")
        print("   A turn that hit the maxTokens ceiling (flagged below) spent its whole")
        print("   budget on output, so its tok/s is inflated; turns under ~100 ms carry")
        print("   meaningful timing error at 1 ms resolution.")
        if any(t["post_compaction"] for t in turns):
            print("   * directly follows a compaction entry; its turn_s includes the")
            print("     compaction's own summary-generation call, so its tok/s is an")
            print("     underestimate (the per-turn median is the robust figure).")
        if any(t["level"] for t in turns):
            print("   Same prompt, different levels => prompt_tok must differ (medium is")
            print("   the baseline: low adds ~30 tokens, xhigh ~42). Identical values mean")
            print("   the level never reached the chat template.")
    for event in summary["compactions"]:
        print(f"compaction       : {event['timestamp']}  ({event['tokens_before']} tokens before)")

    truncations = summary["truncations"]
    if truncations:
        print()
        print(f"!! {len(truncations)} turn(s) hit the maxTokens ceiling:")
        for item in truncations:
            cut = ", ".join(n for n in item["tool_calls_cut"] if n) or "none"
            spent = f"output={item['output_tokens']}  thinking={item['thinking_chars']} chars"
            print(f"   {item['timestamp']}  {spent}  tool call cut: {cut}")
        print("   A cut tool call has truncated arguments and cannot be replayed.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    _ = parser.add_argument("session", nargs="?", type=pathlib.Path, help="path to a session .jsonl")
    _ = parser.add_argument(
        "--latest",
        type=pathlib.Path,
        metavar="DIR",
        help="use the most recent .jsonl in DIR instead of a named session",
    )
    _ = parser.add_argument("--json", action="store_true", help="emit the summary as JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    latest = cast("pathlib.Path | None", args.latest)
    session = cast("pathlib.Path | None", args.session)

    if latest is not None:
        path = latest_session(latest)
    elif session is not None:
        path = session
    else:
        parser.error("give a session path or --latest DIR")

    if not path.is_file():
        raise SystemExit(f"not a file: {path}")

    # argparse.Namespace attributes are typed Any; pin them at the boundary.
    as_json = cast(bool, args.json)

    summary = summarize(load_records(path))
    if as_json:
        print(json.dumps(summary, indent=2))
    else:
        render(summary, path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
