#!/usr/bin/env python3
"""Break a Pi session's reasoning trace into oscillation signals.

This is research tooling, not production adapter behavior. It exists because
"the model thrashed" is easy to assert from reading a trace and hard to compare
across runs: reasoning volume alone conflates a model that deliberates in one
long productive pass with one that re-opens settled decisions. Both look like
"a lot of thinking" in a token count.

The script is deterministic on purpose. It computes what can be counted and
leaves what needs judgment to a reader (or a model) by emitting the candidate
excerpts rather than scoring them. Nothing here decides whether a revisit was
warranted; it locates the revisits.

Terms, since they are used throughout and are easy to blur together:

*Thrashing* is re-opening a decision the model had already settled, with no new
information in between. It is not a synonym for thinking at length: a long
single-pass derivation is not thrashing, and a short trace can contain it.

*Block* is one ``thinking`` content block, which is the reasoning attached to a
single assistant turn.

What it reports, and why each is a distinct signal:

* **block size distribution** -- median, mean, max, and how many blocks exceed
  ``--large-block``. Sorted by length, these distributions are strongly
  right-skewed: in the traces measured so far the median block barely moves
  between effort levels while a handful of blocks grow to fifty times it. Those
  few outsized blocks at the top of the distribution are where the thrashing
  observed so far actually lives, so a comparison of medians misses it entirely
  and a comparison of total characters credits it to the whole trace.
* **largest-three share** -- the share of all thinking held by the three
  largest blocks. Read it against the median: a high share with an ordinary median means
  a few turns ran away, which points at particular decision points. A model that
  is simply more verbose raises every block instead, leaving this share flat.
* **marker rates per 10k characters** -- how often a given phrase appears,
  normalized by trace length. Raw counts cannot be compared between runs, since
  a longer trace contains more of everything. Phrases are grouped by what they
  indicate (below); the groups move independently, which is the point.
* **cross-block repetition** -- word sequences (six words, overlapping) that
  appear in two or more separate blocks. Re-deriving a decision tends to reuse
  the phrasing of the first derivation, so recurrence across blocks is the
  closest deterministic proxy for returning to a settled question. It needs no
  knowledge of the subject matter. Sequences beginning with a stopword are
  dropped, since those recur in any prose.
* **reasoning budget utilization** -- with ``--reasoning-budget``, the largest
  single turn's thinking measured against the server's per-turn cap. This
  answers a specific objection: that a short trace was produced by the cap
  truncating thinking rather than by the model generating less. A peak far below
  the cap means the cap was never reached and cannot be the explanation.

Marker groups:

``fact_adjustment``
    Adjusting a fact mid-derivation ("wait", "actually"). Not itself a defect.
    Its value is as a comparison point: if it holds steady between two runs
    while ``reopening`` collapses, the shorter trace is not just a model writing
    less of everything.
``reopening``
    Returning to a decision already made ("reconsider", "on second thought").
    This is the group that tracks thrashing as defined above.
``alternatives``
    Enumerating options ("option A", "another approach"). Some reasoning-effort
    settings instruct the model to do exactly this, so read it against the
    effort level in force rather than as a fault.
``evidence``
    Reference to something just learned by running code ("traceback", "test
    failed"). A revisit next to one of these was prompted by a result, which is
    verification rather than thrashing.
``settling``
    Settling a question ("I'll go with", "let me write"). Frequent ``reopening``
    with little ``settling`` is the combination worth reading closely.

Two limits worth stating before quoting any of this. Matching is literal, on a
lowercased trace with word boundaries, so it is reproducible but blind to
paraphrase -- a model asked to judge a trace should read ``--excerpts`` output
rather than trust the totals. And a rate computed from a handful of occurrences
carries wide sampling error: at three occurrences the error is roughly ±58%, so
two such rates agreeing to within a few percent is a coincidence of small
numbers, not a measurement of stability. Check the raw ``n`` printed beside each
rate before leaning on it.

Usage::

    pi_thinking_oscillation.py SESSION.jsonl
    pi_thinking_oscillation.py SESSION.jsonl --reasoning-budget 4096
    pi_thinking_oscillation.py SESSION.jsonl --excerpts --json
    pi_thinking_oscillation.py NEW.jsonl --baseline OLD.jsonl
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import statistics
import sys
from typing import TypedDict, cast

DESCRIPTION = "Break a Pi session's reasoning trace into oscillation signals."

# Characters per token. Only used to express thinking volume against a
# token-denominated serving budget, where an order-of-magnitude answer is
# enough. Both ends are reported so a conclusion never rests on the estimate:
# CHARS_PER_TOKEN is typical for English prose, CHARS_PER_TOKEN_LOW is a
# deliberately pessimistic floor that inflates the utilization figure.
CHARS_PER_TOKEN = 3.5
CHARS_PER_TOKEN_LOW = 2.0

LARGE_BLOCK_DEFAULT = 5000
SEQUENCE_WORDS = 6
RATE_BASIS = 10_000

# Phrases are matched with word boundaries on lowercased text. Keep each entry a
# phrase a model actually writes; near-synonyms that never appear only dilute
# the rate.
#
# Known ambiguity, left in place deliberately: "actually" belongs to two groups
# at once. It introduces a fact being adjusted ("actually, the header is
# lowercase") and a settled decision being reversed ("actually, I'll advertise
# 2025-03-26") about equally. Across the two runs measured so far it tracks the
# *reopening* phrases (7.27 -> 1.75 per 10k) rather than "wait" (2.59 -> 2.63,
# on 41 and 3 occurrences), so a fact_adjustment rate driven by "actually"
# must be read phrase by phrase before it is used as a comparison point.
# Reassigning the phrase means reading and labelling its occurrences -- 117
# across both traces, few enough to do exhaustively rather than sample.
MARKERS: dict[str, tuple[str, ...]] = {
    "fact_adjustment": (
        "wait",
        "actually",
        "hold on",
        "oops",
        "scratch that",
        "correction",
    ),
    "reopening": (
        "reconsider",
        "let me reconsider",
        "on second thought",
        "rethink",
        "revisit",
        "second-guess",
        "going back to",
        "back up a",
        "hmm",
    ),
    "alternatives": (
        "alternatively",
        "another approach",
        "another option",
        "one approach",
        "option a",
        "option b",
        "interpretation a",
        "interpretation b",
        "or should",
        "either way",
        "trade-?off",
    ),
    "evidence": (
        "traceback",
        "test failed",
        "tests failed",
        "error:",
        "bug:",
        "crash",
        "returned",
        "output shows",
        "stderr",
        "exit code",
    ),
    "settling": (
        "i'll go with",
        "let me write",
        "let's write",
        "decided",
        "settled",
        "final choice",
        "going with",
    ),
}

# Sequences led by these are structural filler ("let me look at the ...") and
# recur in any trace regardless of oscillation.
SEQUENCE_STOP_LEADS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "but",
        "so",
        "then",
        "now",
        "let",
        "i",
        "it",
        "this",
        "that",
        "to",
        "of",
        "in",
        "is",
        "for",
        "we",
    }
)


class Block(TypedDict, total=False):
    type: str
    thinking: str


class Message(TypedDict, total=False):
    role: str
    content: list[Block]
    model: str


class Record(TypedDict, total=False):
    type: str
    timestamp: str
    message: Message


class ThinkingBlock(TypedDict):
    """One thinking block, kept with its timestamp so findings are locatable."""

    timestamp: str
    chars: int
    text: str


class Distribution(TypedDict):
    blocks: int
    total_chars: int
    median_chars: float
    mean_chars: int
    max_chars: int
    large_blocks: int
    large_block_threshold: int
    largest3_chars: int
    largest3_share_pct: float


class MarkerGroup(TypedDict):
    count: int
    rate_per_10k: float
    hits: dict[str, int]


class Repetition(TypedDict):
    sequence: str
    blocks: int
    timestamps: list[str]


class BudgetUse(TypedDict):
    budget_tokens: int
    peak_turn_chars: int
    peak_turn_timestamp: str
    peak_tokens_est: int
    peak_utilization_pct: float
    peak_utilization_pct_pessimistic: float
    cap_reached: bool


class Excerpt(TypedDict):
    timestamp: str
    group: str
    marker: str
    text: str


class Summary(TypedDict):
    session: str
    models: dict[str, int]
    distribution: Distribution
    markers: dict[str, MarkerGroup]
    repetition: list[Repetition]
    budget: BudgetUse | None
    excerpts: list[Excerpt]


def load_thinking(path: pathlib.Path) -> tuple[list[ThinkingBlock], dict[str, int]]:
    """Return every assistant thinking block in order, plus a model tally.

    The model tally is not decoration: a session with a mid-run model switch
    cannot be attributed to one model, and that is invisible in the prose.
    """
    blocks: list[ThinkingBlock] = []
    models: dict[str, int] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                # json.loads is typed as returning Any; launder it to object at
                # the boundary so nothing downstream inherits an unchecked type.
                decoded = cast(object, json.loads(line))
            except json.JSONDecodeError:
                continue
            if not isinstance(decoded, dict):
                continue
            record = cast(Record, cast(object, decoded))
            if record.get("type") != "message":
                continue
            message = record.get("message") or Message()
            if message.get("role") != "assistant":
                continue
            model = message.get("model") or "unknown"
            models[model] = models.get(model, 0) + 1
            for block in message.get("content", []):
                if block.get("type") != "thinking":
                    continue
                text = block.get("thinking", "")
                if not text:
                    continue
                blocks.append(
                    ThinkingBlock(
                        timestamp=record.get("timestamp", ""), chars=len(text), text=text
                    )
                )
    return blocks, models


def describe_distribution(
    blocks: list[ThinkingBlock], large_block: int
) -> Distribution:
    sizes = sorted(block["chars"] for block in blocks)
    total = sum(sizes)
    largest3 = sum(sizes[-3:])
    return Distribution(
        blocks=len(sizes),
        total_chars=total,
        median_chars=statistics.median(sizes) if sizes else 0.0,
        mean_chars=total // len(sizes) if sizes else 0,
        max_chars=sizes[-1] if sizes else 0,
        large_blocks=sum(1 for size in sizes if size > large_block),
        large_block_threshold=large_block,
        largest3_chars=largest3,
        largest3_share_pct=round(100 * largest3 / total, 1) if total else 0.0,
    )


def _pattern(phrase: str) -> re.Pattern[str]:
    return re.compile(rf"\b{phrase}\b")


def count_markers(text: str, total_chars: int) -> dict[str, MarkerGroup]:
    """Count marker phrases, normalized per 10k characters of thinking.

    Raw counts are not comparable between runs -- a longer trace has more of
    everything -- so the rate is the figure to quote.
    """
    lowered = text.lower()
    groups: dict[str, MarkerGroup] = {}
    for group, phrases in MARKERS.items():
        hits = {
            phrase: len(_pattern(phrase).findall(lowered))
            for phrase in phrases
        }
        count = sum(hits.values())
        groups[group] = MarkerGroup(
            count=count,
            rate_per_10k=round(RATE_BASIS * count / total_chars, 2)
            if total_chars
            else 0.0,
            hits={phrase: n for phrase, n in hits.items() if n},
        )
    return groups


def _word_sequences(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9_./]+", text.lower())
    out: set[str] = set()
    for index in range(len(words) - SEQUENCE_WORDS + 1):
        window = words[index : index + SEQUENCE_WORDS]
        if window[0] in SEQUENCE_STOP_LEADS:
            continue
        out.add(" ".join(window))
    return out


def find_repetition(blocks: list[ThinkingBlock], limit: int) -> list[Repetition]:
    """Sequences recurring across distinct blocks.

    Within-block repetition is normal writing; the same phrasing reappearing in
    a *later* block is the deterministic trace of re-deriving something. Ranked
    by how many blocks a sequence spans, longest span first.
    """
    seen: dict[str, list[str]] = {}
    for block in blocks:
        for sequence in _word_sequences(block["text"]):
            seen.setdefault(sequence, []).append(block["timestamp"])
    repeated = [
        Repetition(sequence=sequence, blocks=len(stamps), timestamps=stamps)
        for sequence, stamps in seen.items()
        if len(stamps) > 1
    ]
    repeated.sort(key=lambda item: (-item["blocks"], item["sequence"]))
    return repeated[:limit]


def measure_budget(blocks: list[ThinkingBlock], budget_tokens: int) -> BudgetUse:
    """Peak per-turn thinking against a serving-side reasoning cap.

    A cap that is never approached cannot explain a short trace, so this is the
    check that decides whether the cap can explain a short trace at all.
    """
    peak = max(blocks, key=lambda block: block["chars"])
    est = int(peak["chars"] / CHARS_PER_TOKEN)
    pessimistic = peak["chars"] / CHARS_PER_TOKEN_LOW
    return BudgetUse(
        budget_tokens=budget_tokens,
        peak_turn_chars=peak["chars"],
        peak_turn_timestamp=peak["timestamp"],
        peak_tokens_est=est,
        peak_utilization_pct=round(100 * est / budget_tokens, 1),
        peak_utilization_pct_pessimistic=round(100 * pessimistic / budget_tokens, 1),
        cap_reached=pessimistic >= 0.9 * budget_tokens,
    )


def collect_excerpts(
    blocks: list[ThinkingBlock], groups: tuple[str, ...], per_group: int
) -> list[Excerpt]:
    """Sentences carrying a marker, for a reader or model to adjudicate.

    The counts above cannot tell a warranted revisit from thrashing. These are
    the passages where that judgment has to be made.
    """
    out: list[Excerpt] = []
    taken: dict[str, int] = {group: 0 for group in groups}
    for block in blocks:
        for sentence in re.split(r"(?<=[.!?\n])\s+", block["text"]):
            lowered = sentence.lower()
            for group in groups:
                if taken[group] >= per_group:
                    continue
                for phrase in MARKERS[group]:
                    if _pattern(phrase).search(lowered):
                        out.append(
                            Excerpt(
                                timestamp=block["timestamp"],
                                group=group,
                                marker=phrase,
                                text=" ".join(sentence.split())[:300],
                            )
                        )
                        taken[group] += 1
                        break
    return out


def summarize(
    path: pathlib.Path,
    large_block: int,
    budget_tokens: int | None,
    repetition_limit: int,
    excerpt_groups: tuple[str, ...],
    excerpts_per_group: int,
) -> Summary:
    blocks, models = load_thinking(path)
    if not blocks:
        raise SystemExit(f"no assistant thinking blocks found in {path}")
    distribution = describe_distribution(blocks, large_block)
    joined = "\n".join(block["text"] for block in blocks)
    return Summary(
        session=path.name,
        models=models,
        distribution=distribution,
        markers=count_markers(joined, distribution["total_chars"]),
        repetition=find_repetition(blocks, repetition_limit),
        budget=measure_budget(blocks, budget_tokens) if budget_tokens else None,
        excerpts=collect_excerpts(blocks, excerpt_groups, excerpts_per_group)
        if excerpts_per_group
        else [],
    )


def print_summary(summary: Summary, baseline: Summary | None) -> None:
    dist = summary["distribution"]
    print(f"session          : {summary['session']}")
    print(f"models           : {summary['models']}")
    print(f"thinking         : {dist['blocks']} blocks, {dist['total_chars']} chars")
    print(
        f"block size       : median {dist['median_chars']:.0f}"
        + f"  mean {dist['mean_chars']}  max {dist['max_chars']}"
    )
    print(
        f"large blocks     : {dist['large_blocks']} over "
        + f"{dist['large_block_threshold']} chars"
    )
    print(
        f"largest 3 blocks : {dist['largest3_chars']} chars "
        + f"({dist['largest3_share_pct']}% of all thinking)"
    )

    print("\nmarker rates per 10k chars of thinking")
    base_markers = baseline["markers"] if baseline else None
    total = dist["total_chars"]
    base_total = baseline["distribution"]["total_chars"] if baseline else 0
    for group, data in summary["markers"].items():
        line = f"   {group:<15} {data['rate_per_10k']:>6.2f}  (n={data['count']})"
        if base_markers:
            line += f"   baseline {base_markers[group]['rate_per_10k']:>6.2f}"
        print(line)
        # Group rates can hide an important split: one phrase holding steady
        # while another in the same group moves several-fold. Break the group
        # out whenever there is a baseline to compare against.
        if not base_markers:
            continue
        phrases = sorted(set(data["hits"]) | set(base_markers[group]["hits"]))
        for phrase in phrases:
            rate = RATE_BASIS * data["hits"].get(phrase, 0) / total if total else 0.0
            base_rate = (
                RATE_BASIS * base_markers[group]["hits"].get(phrase, 0) / base_total
                if base_total
                else 0.0
            )
            print(f"      {phrase:<20} {rate:>6.2f}   baseline {base_rate:>6.2f}")
    if base_markers:
        print(
            "   fact_adjustment is the comparison point: it should track the "
            + "model rather than the effort level. Read it phrase by phrase -- a "
            + "group rate that moved because one phrase moved is a different "
            + "finding from one where all of them did -- and check n before "
            + "treating a small difference as real."
        )

    if summary["repetition"]:
        print("\ncross-block repeated phrasing (candidate re-derivations)")
        for item in summary["repetition"]:
            stamps = ", ".join(item["timestamps"][:4])
            print(f"   x{item['blocks']}  {item['sequence']!r}  [{stamps}]")

    budget = summary["budget"]
    if budget:
        verdict = "cap reached" if budget["cap_reached"] else "cap never reached"
        print(
            f"\nreasoning budget : {budget['budget_tokens']} tokens -- {verdict}\n"
            + f"   peak turn {budget['peak_turn_chars']} chars at "
            + f"{budget['peak_turn_timestamp']} (~{budget['peak_tokens_est']} tok)\n"
            + f"   utilization {budget['peak_utilization_pct']}% "
            + f"(pessimistic {budget['peak_utilization_pct_pessimistic']}%)"
        )
        if not budget["cap_reached"]:
            print(
                "   A cap this far from the peak cannot explain a short trace,\n"
                + "   so a comparison across effort levels still holds."
            )

    if summary["excerpts"]:
        print("\nexcerpts for adjudication (counts cannot judge these)")
        for item in summary["excerpts"]:
            print(f"   [{item['timestamp']}] {item['group']}/{item['marker']}")
            print(f"      {item['text']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    _ = parser.add_argument("session", type=pathlib.Path, help="path to a session .jsonl")
    _ = parser.add_argument(
        "--baseline",
        type=pathlib.Path,
        help="a second session to print marker rates against",
    )
    _ = parser.add_argument(
        "--reasoning-budget",
        type=int,
        help="server-side per-turn reasoning cap in tokens, to test whether it was reached",
    )
    _ = parser.add_argument(
        "--large-block",
        type=int,
        default=LARGE_BLOCK_DEFAULT,
        help=f"threshold for a large thinking block (default: {LARGE_BLOCK_DEFAULT})",
    )
    _ = parser.add_argument(
        "--repetition",
        type=int,
        default=8,
        help="how many repeated sequences to report (default: 8, 0 to skip)",
    )
    _ = parser.add_argument(
        "--excerpts",
        action="store_true",
        help="print marked sentences for a reader or model to adjudicate",
    )
    _ = parser.add_argument(
        "--excerpt-groups",
        default="reopening,alternatives",
        help=(
            "comma-separated marker groups to excerpt "
            + "(default: reopening,alternatives)"
        ),
    )
    _ = parser.add_argument(
        "--excerpts-per-group",
        type=int,
        default=6,
        help="excerpts per group (default: 6)",
    )
    _ = parser.add_argument("--json", action="store_true", help="emit JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # argparse.Namespace attributes are typed Any; pin them at the boundary so
    # nothing downstream inherits an unchecked type.
    session = cast(pathlib.Path, args.session)
    baseline_path = cast("pathlib.Path | None", args.baseline)
    reasoning_budget = cast("int | None", args.reasoning_budget)
    large_block = cast(int, args.large_block)
    repetition_limit = cast(int, args.repetition)
    want_excerpts = cast(bool, args.excerpts)
    excerpts_per_group = cast(int, args.excerpts_per_group)
    as_json = cast(bool, args.json)

    groups = tuple(
        group.strip()
        for group in cast(str, args.excerpt_groups).split(",")
        if group.strip()
    )
    unknown = [group for group in groups if group not in MARKERS]
    if unknown:
        print(
            f"error: unknown marker group(s): {', '.join(unknown)}. "
            + f"Known: {', '.join(MARKERS)}",
            file=sys.stderr,
        )
        return 2

    summary = summarize(
        session,
        large_block,
        reasoning_budget,
        repetition_limit,
        groups,
        excerpts_per_group if want_excerpts else 0,
    )
    baseline = (
        summarize(baseline_path, large_block, None, 0, groups, 0)
        if baseline_path
        else None
    )

    if as_json:
        payload: dict[str, object] = {"session": summary}
        if baseline:
            payload["baseline"] = baseline
        print(json.dumps(payload, indent=2))
    else:
        print_summary(summary, baseline)
    return 0


if __name__ == "__main__":
    sys.exit(main())
