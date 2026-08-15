# Independent Review — `mcp_client`

**Reviewer.** Claude Opus 5, via Claude Code.
**Subject.** The `mcp_client` implementation, its test suite, `SELF_REVIEW.md`, and the session log
of the run that produced them.
**Date.** 2026-08-15.
**Status.** Review only — **no code was changed**. This artifact is an experiment record and is
deliberately left unfixed so that later runs can be scored against it.

---

## 0. Why this document exists

`mcp_client` was written unattended by a locally-served 27B model (Qwen3.8-27B, `UD-Q4_K_XL`) in a
stock Pi harness against a local llama.cpp server, because Pi ships no MCP client. The model then
reviewed its own work in `SELF_REVIEW.md`.

The point of this second review is not to get the client shipped. It is to establish what the model
produced **without any static-analysis feedback loop** — no language server, no linter, no type
checker — and then to compare that against what those tools say after the fact. That comparison is
the measurement: it isolates what the model knows from pretraining and can reason to unaided, from
what a tool would have handed it.

The absence of an LSP in the harness is therefore a property of the experiment, not a deficiency
in it.

Review order matters and is preserved below. Sections 3 and 4 are the reading of the trace and the
code as they stood **before** any checker was consulted; sections 5 onward are what the tools added.
Keeping them separate is what makes the comparison in section 7 meaningful.

---

## 1. Generation conditions (read this before interpreting anything)

The artifact was produced under conditions that were **not** the ones intended, and which were only
discovered afterwards:

| condition | intended | actual |
|---|---|---|
| reasoning effort | `medium` (harness picker) | **`xhigh`** |
| `maxTokens` | — | **8192**, shared between reasoning and answer |
| temperature | — | 1.0 |

The model's chat template defaults to `reasoning_effort='xhigh'` when a client sends nothing, and
the harness's thinking-level control was collapsing every level to a boolean, so it sent nothing.
`xhigh` prepends a system instruction directing the model to *"validate key assumptions, consider
plausible alternatives"* and produces roughly seven times the reasoning of `medium`.

**What this means for scoring.** Conclusions about the model's *process* — long deliberation,
revisiting settled decisions, failure to finish a turn — are not separable from configuration and
should not be charged to the model. Conclusions about the **artifact** are unaffected: the committed
code is the committed code regardless of how many tokens were spent producing it.

---

## 2. Verdict

> Clean at the line level, idiomatically dated, and conformant to a repo convention that static
> analysis dislikes. The one structural complaint a checker raises is the repository's, not the
> model's.

The code is essentially clean at the level of an expression, a function, and the file. It is *not*
importable from the repository root — but neither is any other module in this repository, and the
model identified that convention explicitly before following it (section 6). The defects that
remain attributable to the model are minor.

An earlier draft of this review named the package layout as the model's central failure. That was
wrong, and section 6 documents why.

---

## 3. The generation trace

Recovered from the Pi session log. Pi ships no timing counter, so these are derived from per-record
timestamps by `scripts/probes/pi_session_stats.py` in this repository; re-running that script on the
session JSONL reproduces every figure below.

### 3.1 Quantitative

| metric | value |
|---|---|
| records / assistant messages | 129 / 52 |
| session span | 49.8 min *(includes user idle)* |
| **model working time** | **31.6 min** |
| output tokens | 64,579 |
| throughput | 34.1 tok/s |
| thinking characters | 158,138 |
| answer characters | 12,044 |
| **reasoning share** | **92.9%** |
| turn latency | median 15.5 s, max 252 s |
| stop reasons | `toolUse` ×46, `stop` ×4, **`length` ×2** |

Two notes on method. *Model working time* sums the gap between each assistant message and the record
preceding it, so it excludes the user reading and typing — it is the figure to compare across runs,
and it is the one that should be quoted rather than the 49.8-minute span. *Reasoning share* is
measured in characters rather than tokens because the provider reports `usage.reasoning` as 0 on
every message despite thinking blocks being present; a token-based share would silently read as
zero.

**92.9% of everything the model generated was thinking.** For every character that reached the
artifact, roughly thirteen were spent deliberating. That ratio is a direct consequence of the
`xhigh` condition in section 1 and should not be read as a property of the model.

### 3.2 The two truncations

Both truncated messages stopped at exactly 8,192 output tokens with a tool call cut mid-argument:

| when | thinking before the call | tool call cut |
|---|---|---|
| 04:23:50 | 29,360 chars | `write` — **the initial creation of `mcp_client.py`** |
| 04:50:15 | 30,436 chars | `bash` — a linter-config probe, cut mid-command |

These are not near-misses. In each case roughly 30,000 characters of reasoning consumed the shared
budget before the tool call began serializing, and the call's `arguments` were severed part-way
through a JSON string. The first one truncated the write of the implementation file itself, so the
model had to recover its own primary artifact mid-build.

This is a harness failure, not a model failure. Reasoning and answer share `maxTokens` on this
backend, and 8,192 was about a quarter of what the model's default effort level wants.

### 3.3 Qualitative — deliberation behavior

The trace shows sustained back-and-forth between two sides of a decision — settling a design
question, then re-opening it several turns later without new information. Design choices around the
SSE-versus-JSON response dispatch are re-derived more than once. Turn latencies bear this out: a
median of 15.5 s against a maximum of 252 s means the distribution is dominated by a few very long
deliberative turns.

Two observations, held apart deliberately:

- **The volume of deliberation is explained by the configuration.** `xhigh` literally instructs the
  model to "consider plausible alternatives." Producing long, alternative-weighing reasoning under
  that instruction is compliance, not a defect, and reads as a *positive* instruction-following
  signal once the condition is known.
- **The non-monotonicity is not obviously explained by it.** Re-opening a settled question without
  new information is different from considering alternatives before deciding. At n=1 and
  temperature 1.0, however, sampler wander cannot be separated from instruction-following. This
  needs the controlled rerun in section 10 before it can be called a model property.

### 3.4 Qualitative — task framing

The prompt, in full:

> Firstly, let's implement a lightweight MCP client. We have qmd running as a local http mcp server
> endpoint which is used for your qmd agent-skills.

Two sentences, but more specified than its length suggests. It names the **artifact** (an MCP
client), one **hard constraint** (lightweight), the **transport** (local HTTP), the **target
server** (qmd), and the **consumer** (the model's own qmd skills). What it leaves to inference is
placement in the tree, interface shape (library, CLI, or both), which MCP features are in scope,
and the premise that motivated the task at all — that Pi ships no MCP client, which the model was
never told.

**"Firstly" did not land as intended.** It was meant to steer toward an enumerated planning step
before implementation. The model read it as sequencing — *the first of several tasks* — and began
building. That is the more natural reading of the word, so this is a prompt-design finding rather
than a model failure: a planning step has to be asked for explicitly.

**The one hard constraint was honored exactly.** "Lightweight" produced stdlib-only, single file,
zero dependencies. Where the model had a specific instruction it followed it precisely; the
looseness in the outcome tracks the looseness in the brief.

On not asking: `SELF_REVIEW.md` §2.4 is candid that scope and placement were *"decided unilaterally
[...] assumptions, not confirmations."* But given a brief this concrete, building rather than asking
is a defensible engineering call — most competent contributors handed these two sentences would just
write the client. The earlier framing of this as a straightforward failure to seek clarification was
too harsh. What remains true is narrower: the model never surfaced *which* assumptions it was making
until asked to self-review, and stating them up front costs one sentence.

**The prompt also pointed at a stale source.** "Your qmd agent-skills" directs the model to the
installed qmd skill — whose MCP reference doc, as the model itself discovered (`SELF_REVIEW.md` §3),
documents `get(path, full)` while the running server expects `get(file, fromLine, maxLines,
lineNumbers)`. The model's `path`/`file` error in §2.3 was therefore trusting a source the prompt
had directed it toward. It is still a real diligence gap — it should have preferred the live schema
over the doc — but it is closer to a documentation defect than a hallucination, and the model
correctly identified it as such once it looked.

One confound to record: the harness's own system prompt is unexamined here and may itself discourage
clarifying questions. This should not be charged to the model without checking.

### 3.5 Session-log artifacts worth knowing

- **16 thinking-level changes** appear in a nine-second window early in the session. These are the
  user exercising the harness picker to test whether it was functional; they are not part of the
  task. Final state was `medium` — which, per section 1, was inert.
- **One message came from a different model** (`qwen3.6-27b-q5km`) before the model switch; 51 came
  from `qwen3.8-27b-coding`. Only the latter are attributable.
- **One compaction** occurred at 94,009 tokens, so the model did not hold the whole session in
  context for the final stretch.

---

## 4. First-pass read of the artifact (before any checker)

Recorded here as it stood prior to running any tool, because it is half of the comparison.

### 4.1 What is good

- **The protocol sequencing is correct**: `initialize` (no session) → capture `Mcp-Session-Id` →
  `notifications/initialized` carrying the id, expecting 202 → `tools/list` and `tools/call`
  carrying the id. This is the part most implementations get wrong, and it was verified live.
- **Both response encodings are handled** — `application/json` and `text/event-stream` — each with
  a dedicated test.
- **The argparse arrangement is genuinely nice.** A shared parent parser with
  `default=argparse.SUPPRESS`, attached to both the top-level parser and every subparser, so flags
  work *before or after* the subcommand without the subparser clobbering an already-set value. That
  is a real trick, correctly applied, and most hand-written CLIs do not bother.
- **The tests drive a real in-process `ThreadingHTTPServer`**, not mocks — 20 of them, hermetic, no
  network dependency.
- **Stdlib only, single file**, with a clean `McpError`/`McpHttpError` split and sensible exit codes.

### 4.2 The self-review, reviewed

`SELF_REVIEW.md` was checked finding-by-finding against the code. **Every substantive claim in it is
accurate**, including the cross-cutting §3 finding that the installed qmd skill's reference doc
documents `get(path, full)` while the running server expects `get(file, fromLine, maxLines,
lineNumbers)` — a real defect in a different component, surfaced because the client called the live
schema.

Its §2 process audit is unusually candid and specific: it records a 35-second first test run that it
waved away and never root-caused, an invalid `%default` argparse format string that crashed every
invocation including `-h`, and — most instructively — that it trusted an unverified doc over the
live schema and then "corrected its test" rather than questioning the source. Self-critique at that
resolution is uncommon and is a genuine positive result.

Its stated method was `py_compile`, the test suite, and live probes against a running server. It
explicitly notes in §2.6 that no linter or type checker was run.

### 4.3 What the first pass missed

The first-pass read did not notice that `mcp_client/` is not importable from the repository root.
Neither did it notice that this is true of every other module in the repository. Section 6 covers
both, and the second half is what makes the first half a non-finding.

---

## 5. Static analysis

Tooling, for reproducibility:

| tool | version | mode |
|---|---|---|
| pyright | 1.1.413 | default (`standard`) |
| basedpyright | 1.39.10 | default (`recommended`) |
| ruff | 0.16.3 | default rule selection |

### 5.1 pyright — 1 diagnostic in 381 lines

```
mcp_client.py:242:9  reportUnusedVariable  "_status" is not accessed
```

That is an intentional tuple-unpack discard, already underscore-prefixed. In standard type-checking
mode the implementation file is clean.

### 5.2 ruff — 40 findings across both files

```
22  UP006   non-pep585-annotation      Dict/List  -> dict/list
 7  UP045   non-pep604-annotation      Optional[X] -> X | None
 4  UP031   printf-string-formatting
 2  UP035   deprecated-import
 2  EXE001  shebang-not-executable
 1  I001    unsorted-imports
 1  RUF100  unused-noqa
 1  UP012   unnecessary-encode-utf8
```

**Zero `F`-class (pyflakes) findings.** No unused imports, no undefined names, no shadowing, no
malformed f-strings. This is the single most favourable result in the review: those are precisely
the defects a language server surfaces within a second of typing, and there are none of them in 666
lines written without one.

Under `--select ALL`, the notable addition is `S310` ×2 — `urllib.request.urlopen` called on a URL
whose scheme is not validated. For a client whose URL arrives from a `--url` flag, `file://` is
reachable. Low severity, but real, and neither review made it.

### 5.3 basedpyright — 33 errors, 252 warnings

Error-severity breakdown:

| count | finding | location |
|---|---|---|
| **23** | `"<symbol>" is not a known attribute of module "mcp_client"` | `tests/` throughout |
| 7 | `.state` attribute on `ThreadingHTTPServer` / `BaseServer` | `tests/` |
| 2 | `Expected type arguments for generic class "tuple"` | `mcp_client.py:201`, `:309` |
| 1 | `log_message` override signature incompatible | `tests/test_mcp_client.py:43` |

The 7 `.state` errors are a working, widely-used Python idiom (attaching an attribute to a server
instance) that the checker dislikes; they are not defects. The `log_message` override is harmless at
runtime.

The 252 warnings are dominated by `reportAny` (35), `reportDeprecated` (32), `reportExplicitAny`
(15) and `reportUnknown*Type` (~36 combined) — `recommended`-mode strictness applied to code that
passes `json.loads` output around untyped. `reportUnusedCallResult` accounts for 9, mostly
`parser.add_argument(...)` calls whose returned `Action` is discarded.

---

## 6. The package-layout finding — and why it is the repository's, not the model's

**23 of 33 errors trace to one fact: `mcp_client/` has no `__init__.py`.**

```
tests/test_mcp_client.py:162  "McpClient"   is not a known attribute of module "mcp_client"
tests/test_mcp_client.py:181  "result_text" is not a known attribute of module "mcp_client"
tests/test_mcp_client.py:210  "parse_sse"   is not a known attribute of module "mcp_client"
tests/test_mcp_client.py:252  "DEFAULT_URL" is not a known attribute of module "mcp_client"
...
```

Confirmed at runtime from the repository root:

```
>>> import mcp_client
<module 'mcp_client' (namespace) from ['.../agent-skills/mcp_client']>
__file__     : None
McpClient?   : False
```

`import mcp_client` resolves to a **PEP-420 namespace package** — the directory — not to
`mcp_client.py`. It does not raise. It succeeds and yields an empty module, so the failure surfaces
later as `AttributeError` at the point of use, which is a worse failure mode than a missing module
would be.

The suite passes only because of line 16 of the test file:

```python
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mcp_client
```

That inserts `mcp_client/` itself onto `sys.path`, at which point the name resolves to the module.

### 6.1 This is the repository's prevailing convention

Read in isolation, the above looks like a straightforward packaging bug and the model's central
failure. It is neither. The convention is repo-wide:

- **There are zero `__init__.py` files anywhere in this repository.**
- `adapters/core/tests/test_manifest.py` opens with the identical idiom:

  ```python
  sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
  import manifest
  import snapshot_revert as sr
  ```

- The same `sys.path` manipulation appears in `adapters/zed/install.py`,
  `adapters/zed/tests/unit/`, `adapters/codex/tests/`, `adapters/core/memory_bank_adapter.py`, and
  `adapters/core/tests/`.
- `adapters/zed/hooks/_zed_common.py:9` documents it as deliberate: the hook relies on "the script's
  own directory [being] on `sys.path`".
- Repo-wide, basedpyright reports **31 `reportMissingImports`** and **26
  `reportImplicitRelativeImport`** — the same finding, in the same shape, across `adapters/` and
  `scripts/`. `mcp_client/`'s 23 are a proportionate share of a pre-existing pattern.

And the model said so. `SELF_REVIEW.md` §1.3:

> **Naming.** `mcp_client/mcp_client.py` is mildly redundant. Chosen so the module imports as
> `mcp_client` and matches the repo's plain-module convention (`adapters/core/manifest.py`), but a
> package would arguably be cleaner.

It named the convention, cited a specific file exemplifying it — `adapters/core/manifest.py`, which
basedpyright flags under `reportImplicitRelativeImport` — conformed to it, and recorded the tradeoff
in the same breath. That is what a careful contributor does with an established house style they
mildly disagree with.

**The correct attribution is therefore to the repository.** The convention is checker-hostile and
makes every module in the tree non-importable from the root, which is worth fixing — but it is
pre-existing, it is not this artifact's defect, and a model that had *broken* the convention by
adding an `__init__.py` here would arguably have been the one making the mistake.

### 6.2 What survives as a genuine observation

One narrower point still stands and is worth keeping. Because the tests insert `parents[1]` onto
`sys.path`, the suite validates the module only from a vantage point it constructs for itself; it
cannot detect an import-path regression. That is a real weakness of the convention, and it applies
equally to `adapters/core/tests/test_manifest.py`. It is a repository-level observation about test
design, not a finding against this artifact.

---

## 7. Self-review versus static analysis

The expectation going in was that these would be disjoint — the model finding semantic defects, the
tools finding structural ones. **That is not what the evidence shows.** The self-review anticipated
most of the static analysis.

| finding | in `SELF_REVIEW.md` | in checkers |
|---|---|---|
| unused `status` read | ✅ §1.3 | ✅ pyright's only finding |
| bare `tuple` return annotations | ✅ §1.3 | ✅ basedpyright, 2 errors |
| over-wide lines (100 / 108 chars) | ✅ §1.3 | ✅ `E501` |
| `_decode` mishandles non-object JSON | ✅ §1.2 | ❌ |
| D1 — schemeless `--url` escapes as `ValueError` | ✅ §1.1 | ❌ |
| D2 — no stale-session recovery | ✅ §1.1 | ❌ |
| D3 — `McpHttpError` branch untested | ✅ §1.1 | ❌ |
| D4 — `$MCP_URL` honored by CLI but not library | ✅ §1.1 | ❌ |
| stale qmd reference doc (outside this repo) | ✅ §3 | ❌ |
| legacy typing dialect | ❌ | ✅ 31 ruff + 32 basedpyright |
| unvalidated URL scheme (`S310`) | ❌ | ✅ |
| package layout / `__init__.py` | ✅ §1.3, *as a deliberate convention choice* | ✅ 23 errors, *repo-wide pattern* |

Most striking, §2.6 predicts the tool output directly:

> No **linter or type-checker** run (only `py_compile`) [...] but `mypy`/`ruff` would have flagged
> the unused `status`, the `ValueError` escape, and the `tuple` annotations.

All three predictions are correct. The model, with no static analysis available, correctly
enumerated what static analysis would say about its code — and then, in the same document, missed
the one thing static analysis actually had to teach it.

The self-review's unique contribution is substantial and no checker approaches it: live protocol
verification, an untested-branch audit, a documentation/behavior mismatch, and a stale third-party
doc found by calling the live schema.

What it uniquely missed is thin: the legacy typing dialect (a corpus-vintage artifact, see section
8b) and the unvalidated URL scheme. The package layout, which an earlier draft counted against it,
turns out to be a case where the model reasoned about the question, chose the house convention, and
documented the tradeoff — so the checker and the self-review are in agreement there, differing only
in whether the convention is a good one.

---

## 8. What this measures

The findings sort into three kinds, which should not be scored alike.

**(a) Unaided line-level correctness — strong.** One trivial pyright diagnostic in 381 lines, zero
pyflakes-class defects in 666, one import-ordering nit. Manual SSE parsing, session-header
threading, and a two-level argparse arrangement, all correct on the first pass with no feedback
loop. This is a real capability result and it is the headline.

**(b) Idiom currency — dated, consistent, and not a reasoning signal.** 22 `UP006` + 7 `UP045` + 2
`UP035`, corroborated by 32 `reportDeprecated` findings dated *"deprecated as of Python 3.9"* and
*"as of Python 3.10"*. Two details make it informative. It is perfectly consistent — `Dict` and
`dict` are never mixed — indicating a settled internal style rather than confusion. And it coexists
with `from __future__ import annotations`, which is the modern move and the very thing that makes
the modern vocabulary safe. **The model knows the mechanism and defaults to the older vocabulary.**

This is a readout of training-corpus vintage, not of reasoning quality. No effort budget or prompt
changes it. It is a useful fingerprint for identifying and dating a model; it would be misleading as
a grade, and should be excluded from any capability score.

**(c) Convention conformance — a pass, and the most surprising result.** The package layout was the
candidate for a whole-artifact reasoning failure, and it is not one. The model inspected the
repository, identified an undocumented house convention (plain modules, no `__init__.py`, sibling
imports via `sys.path`), conformed to it, cited a specific exemplar, and recorded its reservation.
Conforming to an unstated local convention rather than importing a generic best practice is a
harder thing to do than following a style guide, and it is a genuine positive result.

The corollary is that **this run produced no clear whole-artifact reasoning failure**. That is a
real gap in the evaluation rather than a clean bill of health: the task was a single self-contained
module, which does not put much pressure on cross-file coherence. A future run should use a task
that spans several files with real interdependencies before concluding anything about the model at
that scope.

### 8.1 A caveat on "unaided"

The model was not working blind. It ran `py_compile`, ran the suite, and exercised the CLI
end-to-end against a live server — which is what caught its `%default` argparse crash and a wrong
parameter name. So the condition being measured is not *generation without tools*; it is
**generation whose only verification tool is one the model designed itself**.

That is a more interesting condition, and it grades differently — "what the model misses with no
tools" and "what it misses when its only tool is one it built itself" are different questions, and
this run answers the second. The two should be distinguished in any follow-on experiment.

It also means the run cannot speak to what the model does *with* an LSP available. Given that its
self-review correctly predicted the linter's findings (section 7), the interesting follow-up is
whether access to a checker changes the artifact or merely confirms what it already knew.

---

## 9. Findings ledger

Defects confirmed in this review, beyond those already listed in `SELF_REVIEW.md` §1:

| id | severity | finding |
|---|---|---|
| O1 | ⚪ | **Not a finding against this artifact.** `mcp_client/` lacks `__init__.py`, so `import mcp_client` yields an empty namespace package from anywhere but inside the directory — but this is the repository's convention (0 `__init__.py` files repo-wide; 57 equivalent errors across `adapters/` and `scripts/`), the model identified it explicitly, and conformed. Re-filed as R1 below. |
| O2 | 🟡 | `urlopen` is called without validating the URL scheme (`S310`, 2 sites). `file://` and other schemes are reachable from `--url`. Related to, but distinct from, `SELF_REVIEW.md` D1. |
| O3 | 🟢 | Legacy typing dialect throughout (`Dict`/`List`/`Optional`) despite `from __future__ import annotations`. Style, not a defect. |
| O4 | 🟢 | An unused `# noqa` (`RUF100`) suppressing nothing. |
| O5 | 🟢 | Unsorted imports at one site (`I001`); shebang present on a non-executable file (`EXE001`, 2 sites). |

**Not applied.** See the status note at the top.

### 9.1 Repository-level findings surfaced by this review

These are not about `mcp_client` and should be triaged separately from it.

| id | severity | finding |
|---|---|---|
| R1 | 🟡 | No module in the repository is importable from the repository root. There are zero `__init__.py` files; sibling imports rely on `sys.path` insertion at the top of each entrypoint and test. Static analysis reports 31 `reportMissingImports` and 26 `reportImplicitRelativeImport` across `adapters/` and `scripts/`. Deliberate (documented at `adapters/zed/hooks/_zed_common.py:9`) but it costs the whole tree its type-checkability. |
| R2 | 🟡 | Because tests insert their own parent directory onto `sys.path`, no test suite in the repository validates the import path a consumer would use. Applies equally to `adapters/core/tests/test_manifest.py` and `mcp_client/tests/test_mcp_client.py`. |
| R3 | 🟢 | Repo-wide, `basedpyright` at `recommended` reports 210 errors across 52 files. The bulk are R1's import pattern plus `reportUninitializedInstanceVariable` (37) and `reportAttributeAccessIssue` (35). Worth a triage pass to separate real defects from convention artifacts before any of it is used as an evaluation baseline. |

R1 and R2 are pre-existing and predate this artifact. They matter here only because misreading them
as *this artifact's* defects is exactly the error an earlier draft of this review made.

---

## 10. Suggested additions to future runs

1. **Establish the repository's own baseline before scoring any run against it.** This review nearly
   charged a model with a defect that is the repository's convention (R1). Any static-analysis score
   must be a *delta* against a clean baseline of the untouched tree, not an absolute count — and the
   baseline must be captured at a pinned tool version and config, since both move.
2. **Score error-severity structural findings; exclude idiom findings.** `UP*` and
   `reportDeprecated` measure corpus age; `reportAny` and `reportUnknown*` measure annotation density
   under an opinionated mode. Neither belongs in a capability score.
3. **Record idiom dialect as a fingerprint field** alongside model, quant, chat template, and
   reasoning effort. It is cheap to collect and appears to be stable per model.
4. **Re-run this prompt at `medium` with a larger `maxTokens`**, and separately at a lower
   temperature, before drawing any conclusion about deliberation behavior. The `medium` arm tests
   whether the 92.9% reasoning share collapses; the low-temperature arm separates sampler wander
   from instruction-following in section 3.3.
5. **Test clarification-seeking with a prompt that actually requires it.** This one did not: it named
   the artifact, the constraint, the transport, and the target server, so building without asking was
   reasonable. A real probe needs a brief with a genuine fork in it — one where two readings produce
   materially different artifacts — and should also control for the harness system prompt, which
   section 3.4 could not rule out as the reason no questions were asked.
6. **State the motivating premise in the brief.** The model was never told that Pi ships no MCP
   client. Scope decisions it had to guess at (persistent SSE, batching, library-vs-CLI) follow
   directly from that premise, and withholding it made the task harder in a way that does not
   measure anything interesting.
7. **Ask for a plan explicitly if a plan is wanted.** "Firstly" was intended as a planning cue and
   read as sequencing.
8. **Run `pi_session_stats.py` on every session** so trace metrics are collected uniformly rather
   than reconstructed per run.
9. **Use a multi-file task next.** Section 8c could not test whole-artifact coherence, because a
   single self-contained module does not exercise it. A task spanning several interdependent files
   would.
