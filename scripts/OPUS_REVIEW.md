# Review: `qmd_mcp.py` / `test_qmd_mcp.py` (local-model run, medium effort, Q4_K_XL)

**Reviewer.** `claude-opus-5` at reasoning effort `medium`, via Claude Code. Taken from the review session's own transcript rather than asserted: 168 assistant records, all `claude-opus-5`, all `effort: medium`, no other value present. The prior review ran under the same configuration — 474 assistant records on 2026-08-15, all `claude-opus-5` at `medium` — so the two reviews are comparable as instruments, and both are medium-effort reviewers evaluating a medium-effort subject.

**Artifact.** `scripts/qmd_mcp.py` (292 lines) + `scripts/test_qmd_mcp.py` (348). Written unattended from a single prompt, identical verbatim to the prior run's prompt.

**Status.** Review only — no code was changed. Like the prior review, this artifact is an experiment record and is deliberately left unfixed so later runs can be scored against it.

Method follows the earlier evaluation: trace metrics from the session probe, a qualitative read of the reasoning trace, static analysis as a delta against the repository baseline, then a read of the code. The prior run's artifact was re-measured from its branch with today's instruments rather than quoted from the earlier review, whose figures were taken with pyright 1.1.413.

**Two deviations from the prior method, disclosed.** First, that review recorded its first-pass read of the artifact *before* any checker was consulted, keeping the two halves separate so the comparison in its §7 was meaningful; here the checkers were run alongside the read, so no clean pre-tool baseline exists for this artifact and none is reconstructed after the fact. Second, pyright 1.1.413 is not installed on this machine — the `pyright` on `PATH` is a basedpyright shim — so `standard` mode is basedpyright's, which is close but not the same instrument.

## 1. Trace metrics

From `scripts/probes/pi_session_stats.py` on the session JSONL.

| Metric | This run (medium, 32768) | Prior run (xhigh, 8192) | Comparable? |
| --- | --- | --- | --- |
| Assistant messages | 22 | 52 | yes |
| Output tokens | 12,690 | 64,579 | yes |
| Model working time | 13.7 min | 31.6 min | yes |
| Reasoning share (chars) | 77.8% (11,164 / 3,180) | 92.9% | yes, with caveat |
| Truncations | **0** | 2, both at exactly 8,192 | yes |
| Throughput | 15.5 tok/s | 34.1 tok/s | **no** — different device and quant |
| Turn latency | median 19.8 s, max 202 s | median 15.5 s, max 252 s | roughly |

Tool use: 27 calls — 18 `bash`, 6 `edit`, 2 `write`, 1 `read`. Stop reasons: 21 `toolUse`, 1 `stop`; no `length`. Thinking level `medium` held for every turn.

**The clearest result is the truncation count.** Zero, against two in the baseline. That confirms the earlier reading: the 8,192-token ceiling was the defect in the first run, not the model. The first truncation there severed the `write` that created the primary artifact; nothing comparable happened here.

Four conditions moved from the baseline and only two were intended, so this was planned as a coding-performance run rather than an effort isolation. The reasoning-share drop (92.9% → 77.8%) was therefore expected to be uninterpretable, since `--reasoning-budget 4096` could have capped thinking independently of effort. **§1.2 shows the budget never bound** — peak utilization 9.8% — so the drop is behavioral after all, and `medium` is the operative variable. The device and quant remain unisolated but are not plausible causes of a change in deliberation structure.

Session hygiene, checked because the prior trace was not clean on these axes: **no compaction**, **no mid-session model switch** (23 assistant messages, all `qwen3.8-27b-coding`), and **one thinking-level record**, set once to `medium`. The prior session had a compaction at 94,009 tokens, one message from a different model, and 16 level changes in a nine-second window. This trace is attributable end to end.

### 1.1 Deliberation behavior — the thrashing question

The prior run's central qualitative concern was what the user termed *LLM thrashing*: sustained back-and-forth between two sides of a decision, with settled questions re-opened several turns later without new information. Its SSE-versus-JSON dispatch was re-derived more than once across 158,138 characters of thinking. The prior review's recommendation 4 named a `medium` rerun as the test of whether that collapses.

**It collapsed.** 23 thinking blocks, 11,164 characters in total, longest single block 1,406 characters. The progression is strictly monotone: survey the repo, find `codex_qmd_mcp.py` and establish it is an installer rather than a client, verify the transport against the live server, choose placement once at T5 (`scripts/qmd_mcp.py`) and never relitigate it, write, test, fix, ship.

Every revisit in the trace is **evidence-triggered rather than deliberative** — the distinction the prior review drew but could not test:

| block | trigger | revisit |
| --- | --- | --- |
| T10 | test run crashed | diagnoses the `_request` / `_initialize_result` recursion |
| T11 | reading its own fix | notices `instructions` sits at the result's top level, not in `serverInfo` |
| T15 | writing the stub | realizes a 400 makes the JSON-RPC error path untested; changes it to 200 per the spec |
| T19 | live `get` call | finds `resource` content items that `extract_text` drops |
| T21 | before re-running | checks concatenation order, confirms, moves on |

None of these re-open a settled question; each responds to something the model had just learned by running code. T18 and T22 also show it correctly identifying "Firstly" as sequencing and proposing follow-on steps rather than expanding scope on its own.

### 1.2 Re-analysis of the xhigh trace, and what the collapse is not

The prior session log was re-read rather than taken on trust, and it refines the thrashing claim in two ways.

**Thrashing came in a few isolated bursts, not spread through the trace.** *Thrashing* here is the user's term from the first evaluation, and it means one specific thing: re-opening a decision the model had already settled, without new information. It is not the same as thinking a lot.

Sort every thinking block by length and the xhigh run is heavily right-skewed: median block 627 characters, largest block 30,436 — about fifty times the median — with five blocks over 5,000 characters and **the largest three holding 56.3% of all thinking in the session**. This run has no block over 5,000 characters and a median of 329, the same order as the baseline's.

That difference in shape is the finding, and it distinguishes two behaviors a token count would conflate. Had every block roughly doubled, the model would simply be more verbose at higher effort — a uniform effect. Instead the ordinary turns stayed ordinary and a few ran away, which points at specific decision points rather than a general style. It also explains the truncations: two of those three giant blocks are the turns that hit the 8,192 ceiling and were cut mid-tool-call, so thrashing and truncation are one event, not two findings.

One bookkeeping note on the totals: this session's log gained a 238-character block at 06:23 — an acknowledgement of `/exit`, an hour after the work finished. Task-scoped thinking is **11,164 characters**; a whole-file count reads 11,402. The task-scoped figure is the one compared above.

**The vocabulary separates cleanly, and one marker does not move.** Figures below are from `scripts/probes/pi_thinking_oscillation.py`, which was written for this question so the counts are reproducible rather than hand-tallied; rates are per 10,000 characters of thinking, matched on word boundaries.

| marker | xhigh | medium |
| --- | --- | --- |
| `wait` | 2.59 | **2.63** |
| `actually` | 7.27 | 1.75 |
| `reconsider` | 1.77 | 0 |
| `let me reconsider` | 1.52 | 0 |
| `hmm` | 1.45 | 0 |
| `alternatively` | 0.19 | 0 |
| `interpretation a` / `b` | 0.13 / 0.06 | 0 / 0 |

The argument these numbers support needs one thing to hold: some feature of the model's writing that did *not* change, showing the trace got shorter without its basic style being different. `wait` — adjusting a fact mid-derivation — is that feature, at 2.59 against 2.63, while every phrase that signals re-opening drops to zero. `xhigh` prepends an instruction to "consider plausible alternatives", and the phrases that vanish are the ones that instruction solicits, which supports the first review's hypothesis that the deliberation volume was the model complying with its instructions rather than failing at the task.

**How much weight that comparison bears is limited by counts, not percentages.** `wait` occurs 41 times in the xhigh trace and **3 times** in this one. At n=3 the sampling error on a rate is roughly ±58%, so "2.59 versus 2.63" is not a measurement of stability to within 2% — it is consistent with no change, and would look much the same if the true rate had moved by half. The claim to make is the weak one: nothing in the trace suggests the model's local self-correction habit changed, and the collapse in re-opening phrases is far too large to be explained that way.

One caveat on the phrase list itself, recorded because it would otherwise be a buried assumption: **`actually` does double duty.** It introduces a fact being adjusted ("actually, the header is lowercase") and a settled choice being reversed ("actually, I'll advertise `2025-03-26`") about equally, and in these two runs it tracks the re-opening phrases rather than `wait`. Grouping it with `wait` would therefore inflate the very quantity the argument depends on, which is why the probe prints each phrase separately whenever a baseline is given. Deciding where it belongs needs the occurrences read and labelled — 115 in the xhigh trace, 2 here, few enough to go through exhaustively rather than sample.

Reading inside the largest complete block (04:20:08, 29,236 chars) shows the oscillation is mostly *intra*-block rather than across turns: it enumerates two interpretations of the brief, then settles the advertised protocol version by talking itself from `2025-06-18` to `2025-03-26` inside a single paragraph. This run picked `2025-06-18` in one line without deliberation, and it works. Topic recurrence across blocks is a weak signal on its own — both runs mention SSE in most blocks, because SSE is the subject — but CLI shape recurs in 10 xhigh blocks against 1 here, and that one is genuine rework, since the `%default` crash and the `--json` flag placement forced it.

Reproduce the whole of §1.2 with:

```
scripts/probes/pi_thinking_oscillation.py MEDIUM.jsonl --baseline XHIGH.jsonl --reasoning-budget 4096
```

**The reasoning budget did not cause the collapse, which makes `medium` the credible explanation.** `--reasoning-budget 4096` caps how much thinking the server will emit per turn, so the obvious objection is that the long blocks were cut off by that cap rather than never written. The trace refutes it: the largest thinking turn here is 1,406 characters, roughly 400 tokens, **9.8% of the 4,096-token cap** — at a deliberately pessimistic 2 characters per token, still only 17%. No turn came within four times the ceiling, so the cap was never reached and cannot explain either the missing long blocks or most of the drop in reasoning share. That leaves the effort level as the cause. Two other conditions also differed from the baseline — the GPU and the quantization — but neither plausibly changes *how* a model deliberates, only how fast it emits.

## 2. Static analysis

Tooling: ruff 0.16.3, basedpyright 1.39.10 (`recommended` and `standard`). No repo-local ruff or pyright config; the user's global ruff config is in force.

Repository baseline for context: `ruff check scripts/*.py` reports 63 findings across 3,708 lines, including 17 `F401` unused-import. The model's two files contribute 7 of those 63.

- **ruff on the artifact: 7 findings, all 7 in the test file, zero in `qmd_mcp.py`.** `EXE001` (shebang, not executable), 2× `RUF100` (unused `noqa` for rules the global config does not enable), 2× `RUF012` (mutable class attribute — deliberate, the stub's per-test state), `UP012`, `RUF059` (unused `err` unpack). **Zero F-class findings in 640 lines** — no unused imports, undefined names, or shadowing, written without a language server. That repeats the strongest result of the prior run at a comparable line count; it does **not** improve on it, see §5.
- **basedpyright `standard`: 0 errors in `qmd_mcp.py`**, 4 in the test file. One is `reportMissingImports` on `import qmd_mcp` after `sys.path.insert` — the repository's own convention (zero `__init__.py` files repo-wide), a baseline item, not a defect. The other three: `log_message` override signature, and two `str | None` arguments that the stub's own contract makes non-None in practice.
- **basedpyright `recommended`: 27 errors / 180 warnings**, but 16 of the 27 errors are `reportMissingTypeArgument` on bare `dict` — annotation density under an opinionated mode, which the scoring rule excludes. Excluding those and the repo-convention import leaves **10 error-severity findings, 1 of them in the implementation file** (line 129, `expect_id` receives the JSON-RPC id typed as the union of a heterogeneous dict's values — a typing weakness with no runtime effect).

Under `--select ALL`, the prior review's one genuinely missed finding reappears here: **`S310` ×2** — `urllib.request.urlopen` called on a URL whose scheme is never validated, so `file://` is reachable through `--url` or `$QMD_MCP_URL`. Identical to the earlier artifact's O2, and neither the model nor the first pass of this review caught it. The rest of the `ALL` profile is house-style noise (`COM812` ×9, `TRY003` ×7, `EM102` ×6, `T201` ×6 for a CLI that is supposed to print). Worth noting on the other side: this artifact draws **no `C901`, `PLR0911`, or `PLR0912`** complexity findings, where the prior one drew all three — its `_request`/`_parse_response` split is flatter than the earlier `McpClient`.

Dialect fingerprint, recorded not graded: this run uses **modern** annotation vocabulary throughout (`str | None`, `list[dict]`, PEP 604 unions) with `from __future__ import annotations`. That is a change from the prior run's uniform `Dict`/`List`/`Optional`, and it is again internally consistent.

## 3. Behavior, verified live

- `python3 scripts/qmd_mcp.py tools` returns all four qmd tools with schemas.
- `call status` returns the live index status.
- `python3 scripts/test_qmd_mcp.py`: **17 tests, all pass**, in 7.1 s.

The client is correct on the parts that matter: lazy `initialize`, `mcp-session-id` capture and reuse, the `notifications/initialized` 202, JSON *and* SSE response bodies, JSON-RPC errors raised as `QmdMcpError`, `isError` results exiting 1 with text on stderr, and `resource` content items unwrapped alongside `text` ones.

The model found and fixed two real bugs mid-build without being told: infinite recursion between `_request` and `_initialize_result`, and `get` returning `resource` items its first `extract_text` dropped. Both were caught by running the thing against the live server, which it did 18 times.

## 4. Findings

**F1 — the stale-doc error recurred, from the same source (docstring only).** `qmd_mcp.py:15` documents `call get '{"path":"#abc123"}'`. The live tool requires `file`; running that example verbatim returns `MCP error -32602`. The origin is unchanged since the last run: `~/.claude/skills/qmd/references/mcp-setup.md:81` still documents the parameter as `path`. This is the same miss as the prior run, from the same unfixed document — but it is now confined to a docstring example, because the CLI passes user JSON through untouched, so no code path is wrong. The repo-side documentation defect is worth fixing; it has now cost two runs.

**F2 — the stub's session-rejection branch is never exercised.** `test_qmd_mcp.py:150` implements a 404 for an unknown `mcp-session-id`, but `session_ids` starts empty each test and is only ever populated with the client's own id, so the guard's first clause is always false on the first call. No test asserts what the client does when a session expires — and the client has no answer: `_post` raises `QmdMcpError` on the 404 with no re-initialize and retry. That is a genuine robustness gap for a long-lived session against a restarting server, and the test file gestures at it without covering it.

**F3 — an empty response body is silently success.** `_parse_response` returns `{}` for a blank body. Correct for the 202 notification, but a truncated or empty response to `tools/list` yields an empty tool list rather than an error. Low severity.

**F4 — minor:** `_print_tool` indexes `tool['name']` directly (KeyError on a malformed tool entry); `RUF012`/`RUF100`/`EXE001` in the test file are house-style noise rather than defects.

**F5 — unvalidated URL scheme** (`S310` ×2). `urlopen` is called on a URL taken from `--url` or `$QMD_MCP_URL` with no scheme check, so `file://` and friends are reachable. Same finding as the prior artifact's O2; low severity for a local developer tool, but real and missed by both the model and this review's first pass.

Nothing in the implementation file rises above F3. There is no fabricated API, no invented behavior, and no whole-artifact reasoning failure.

### 4.1 Findings ledger

| id | severity | finding |
| --- | --- | --- |
| F1 | 🟡 | Docstring example uses `get {"path": ...}`; the live tool requires `file`. Traceable to an unfixed reference doc outside this repo — re-filed as R4. |
| F2 | 🟡 | No stale-session recovery: a 404 on an expired `mcp-session-id` raises instead of re-initializing, and the stub's own 404 branch is unreachable in tests. |
| F3 | 🟢 | Empty response body parses as success (`{}`), so a truncated `tools/list` yields an empty tool list rather than an error. |
| F4 | 🟢 | `_print_tool` indexes `tool['name']` directly; `RUF012` / `RUF100` / `EXE001` in the test file are house-style noise. |
| F5 | 🟢 | `urlopen` called without validating the URL scheme (`S310` ×2). |

**Not applied.** See the status note at the top.

### 4.2 Repository-level findings

Not about this artifact, and to be triaged separately from it.

| id | severity | finding |
| --- | --- | --- |
| R4 | 🟡 | `~/.claude/skills/qmd/references/mcp-setup.md:81` documents `get`'s parameter as `path`; the live server requires `file`. This has now produced a wrong artifact in two consecutive runs — a code path in the first, a docstring in this one. One-word fix, and the highest-value repo-side change before the next run. |
| R1–R3 | — | The prior review's repository findings (no module importable from the repo root; no suite validates a consumer's import path; repo-wide `recommended` noise) stand unchanged and are not re-litigated here. |

## 5. Comparison to the baseline run

- **Truncations solved.** Zero, against two. The harness ceiling was the defect.
- **Thrashing collapsed, and it is attributable.** 11,164 characters of thinking against 158,138, no decision re-opened without new information, every revisit evidence-triggered, and the re-opening vocabulary (`reconsider`, `Hmm`, `Alternatively`) gone to zero while local self-correction (`Wait`) holds steady. This answers the prior review's recommendation 4. The reasoning budget was the obvious alternative explanation and §1.2 rules it out at 9.8% peak utilization.
- **Cost fell by roughly five times.** 12,690 output tokens and 13.7 minutes produced 640 lines against 64,579 tokens and 31.6 minutes for 664 lines. Whether that is `medium`, the reasoning budget, or the larger token ceiling removing recovery work is not separable from this arm.
- **Static analysis is a wash, measured the same way.** The prior artifact was re-run through today's ruff and basedpyright from `zed-local-pi/qwen3.8-experiment-xhigh-effort`:

  | Same instruments | medium (640 ln) | xhigh (664 ln) |
  | --- | --- | --- |
  | ruff, raw | 7 | 40 |
  | ruff, excluding `UP*` per the scoring rule | 6 | 4 |
  | basedpyright `standard`, implementation file | 0 | 0 |
  | basedpyright `standard`, test file | 4 | 8 |
  | basedpyright `recommended`, errors after exclusions | 10 | 9 |
  | own test suite | 17/17 pass | 20/20 pass |

  **The 40-vs-7 raw gap is 36 `UP*` findings** — `Dict`/`List`/`Optional` and `%`-formatting — which the scoring rule already excludes as training-corpus vintage. On the scored subset the two are indistinguishable. Both implementation files are clean under `standard`; the prior artifact's extra `standard` errors are one idiom repeated seven times (attaching a `.state` attribute to the stub server). This run's 16 `reportMissingTypeArgument` come from bare `dict` where the prior run wrote `Dict[str, Any]` — on that one axis the older artifact is the more precisely annotated.

  So the medium arm's gain is **cost, not quality**: zero truncations, one-fifth the tokens, half the wall clock, at equal artifact quality.
- **Repo-convention conformance again correct.** Flat module in `scripts/`, `sys.path.insert` test idiom, stdlib-only, argparse CLI — matching `codex_qmd_mcp.py` and the rest of the tree. The model read the existing `codex_qmd_mcp.py` first and correctly did not duplicate it (that file configures Codex's MCP entry; it is not a client).
- **Idiom vintage moved forward.** Modern union/builtin-generic syntax this run, older `Dict`/`List`/`Optional` last run. Same prompt, same model family — worth tracking as a quant or configuration fingerprint rather than a capability change.
- **No self-review this run**, because the session had one user turn. The prior run's `SELF_REVIEW.md` came from a later prompt. Not a regression; the probe simply was not run.

## 6. Gaps this run still does not close

Unchanged from the prior evaluation: single self-contained module, so cross-file coherence is untested; the prompt still contains no genuine fork, so clarification-seeking measures nothing; and "unaided" again means *verification by a tool the model wrote itself*, plus a live server it drove by hand.
