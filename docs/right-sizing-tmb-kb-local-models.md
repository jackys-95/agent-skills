# Design Outline — Right-Sizing tmb/kb Operations to Local Models

*Status: design outline. Tracks #67. The experimental shape and layer taxonomy are settled; fixture construction and the phase-0 prerequisites are not yet designed.*

## 1. Motivation & Objective

Thesis: not every tmb/kb operation requires general intelligence, and defaulting to a frontier model plus a general-purpose harness is over-provisioning.

Goal: locate the capability/cost pareto frontier for offloading specific operations from frontier to local.

**Objective: extend effective frontier capacity.** Subscriptions are Claude Pro and ChatGPT Plus, where quota is tight enough that frontier tokens are genuinely scarce at the margin. Cost and context-hygiene therefore collapse into a single objective rather than competing ones.

Offline/privacy capability is a nice-to-have, not a design driver at current data sensitivity.

Non-goal: rebuilding harness infrastructure (see §5 exclusions).

**Not** a non-goal: replacing frontier models for judgment-tier work. Whether that is possible is an open question the experiment exists to answer — see §14. It must not be assumed in the design, or the hardest tier gets under-instrumented precisely where data is most needed.

## 2. Cost Model

Four distinct costs, separately measured. Offload is justified when (1) + (2) exceed (3) + (4).

**Freed by offloading:**

1. **Quota/token consumption by low-value operations** — frontier tokens spent on routing decisions and boilerplate argument synthesis. Dominant term under Pro/Plus.
2. **Context occupancy** — tmb/kb bookkeeping crowding the window that should hold the actual problem.

**Added by offloading:**

3. **Remediation cost** — fixing tmb/kb misuse by a weaker model. Captured via error-reversibility weighting (§6).
4. **Supervision/handholding overhead** — the least substitutable resource. A local model needing more steering can be a net loss at zero token cost. Needs a human-time proxy in the fixture, likely turns-to-acceptable-result.

## 3. Operation Taxonomy

The taxonomy is drawn around the **CLI boundary**, not around abstract intelligence demand. `memory_bank.py` already absorbs the mechanical execution layer, so the earlier framing (which treated history appends and index maintenance as model work) was wrong. What remains for the model is routing plus argument synthesis, and those differ sharply in how they fail.

### Layer 0 — Already deterministic (control surface, not under test)

`memory_bank.py` provides `init-project`, `new-work`, `suggest-projects`, `regen-index`, `branch-work`, `append-history`, `reindex`, `doctor`, and `migrate-collections`.

Between them these already handle ID allocation, directory scaffolding, README and `active.md` template instantiation, session numbering, history formatting, index regeneration from on-disk status, qmd collection registration, and status-enum validation.

A "right-size to zero" audit would therefore find very little left — that work is done. This layer is the control surface the experiment measures against, which makes defects in it a direct threat to scoring validity (see §12).

### Layer 1 — Routing

Decide whether to invoke, and which command. Failures are loud and observable: wrong command, missing invocation, invoking when nothing was warranted.

Highly harness-tractable through tool descriptions, trigger text, and turn-boundary hooks. Some routing is removable from the model entirely; some is not, since "epic or three tasks?" cannot be triggered deterministically.

### Layer 2 — Closed-argument synthesis

Enum and identity arguments: `--type {epic,spike,story,task}`, `--status {open,in-progress,blocked,paused,done,shipped,cancelled,superseded}`, `--work`, `--project`, `--memory-root`.

Failures are loud — the CLI validates enums against a closed set and identity arguments against the filesystem, so a wrong value errors at the boundary rather than silently corrupting the bank.

**This is the strongest offload case in the design.** A small model supplying closed-set arguments to a validating CLI is a well-founded expectation, and the validation provides machine-checkable scoring for free. `doctor` supplies a structural check on top.

### Layer 3 — Free-text argument synthesis

`--title`, `--summary`, `--description`, `--reason`. Unvalidatable, and they carry all the actual information content.

Writing a `--summary` that a future agent can genuinely resume from is a compression-and-salience judgment, not a formatting task. Failures are **silent** — a bad summary is not detected until a resume months later goes wrong. This layer sits far closer to taxonomic judgment than to mechanical work, and conflating it with schema-bound operations was the central error in the earlier taxonomy.

### Layer 4 — Unscripted artifact editing

`active.md` maintenance, knowledge-file placement, file splitting, cross-reference selection, epic/story/task decomposition, promotion of WIP primers to approved knowledge.

No CLI boundary, no validation, silent and durable failures. The hardest tier.

**Finding worth separating out:** there is no `update-active` command. `active.md` is the highest-traffic artifact in the bank and the one every resume depends on, yet it has no deterministic interface — it is free-form model editing against prose conventions in `references/workflows.md`. That is simultaneously the largest measurement target here and, plausibly, a missing script. Worth its own issue independent of this experiment.

### Cross-cutting note

Routing and argument synthesis fail independently and respond to different fixes, so they are scored separately throughout.

## 4. Central Hypothesis

Harness specialization improves realized performance through **two distinct mechanisms**, which make different predictions.

**Rule substitution** — an articulable criterion replaces a judgment call ("split when it covers more than one entity"). Converts judgment into rule-following, which small models do comparatively well.

**Grounding / disambiguation** — supplying domain terminology, local conventions, and system-specific meanings absent from public training data. The model has judgment capacity but lacks referents; supplying them removes an obstacle to inference rather than overriding it.

Exemplars are ambiguous between the two and likely function as both, varying with how close the new case is to the example.

**Discriminator: the brittleness signature.** Rule substitution should produce edge-case failures where the stated rule misfires on cases it does not cover. Grounding should not, because it improves the model's model of the domain rather than constraining inference. Test with adversarial edge cases in the fixture.

**Mapping to the taxonomy:** Layer 2 is where rule substitution should dominate, since the criteria are fully articulable and the enum is closed. Layer 3 and Layer 4 are where grounding should carry the weight, since the difficulty is knowing what this system means by "phase" or "promotable", not knowing a rule.

**Deliberately out of scope:** whether supplied context "adds judgment capacity" in an intrinsic sense. Capability is only observed conditional on context; there is no context-free judgment to measure, and the harness is part of the system under test. The metaphysical claim is dropped; the mechanism distinction is kept because it is testable.

**Costs to watch:** externalized criteria consume context, over-specified rules misfire at edges, and there is a ceiling effect where stating a criterion does not help if the model cannot apply it.

## 5. Experimental Design

Factorial: **harness × layer**.

| | Local (Qwen3.6-27B, Gemma4-26B-A4B) | Near-frontier (OpenRouter) | Frontier |
|---|---|---|---|
| **Barebones Pi** | ✔ baseline | ✔ | ✖ subscription-only |
| **Specialized Pi** | ✔ primary arm | ✔ | ✖ subscription-only |
| **General harness** | — | — | CC / Codex reference |

Frontier-via-API cells are excluded because access is subscription-bound (Pro/Plus) and official tooling is the economical path. OpenRouter near-frontier models (GLM, Kimi, MiniMax, DeepSeek) restore the row.

CC/Codex is a reference point, not a controlled cell, since model and harness co-vary there. Claims against it are directional only.

**Excluded: self-built harness (Strands / LangGraph).** It would measure framework quirks alongside model behavior and rebuild what Pi provides. Revisit only if Pi's loop cannot express something required.

Pi has no native MCP by design — a four-tool core plus TypeScript extensions — though community adapters exist. qmd exposes both `qmd mcp` (stdio) and a full CLI.

## 6. Measurement

**Per-layer fixture** — the load-bearing artifact. Task-level, harness-agnostic, keyed by layer. `qmd bench` measures retrieval quality against a fixture, which is adjacent but not sufficient. Build first; useful independent of whether the benchmark runs.

**Free scoring at Layers 1–2.** The CLI's closed enums, filesystem validation, and `doctor` give machine-checkable pass/fail without human labels. This is why the pilot starts here.

**Human and LLM judging at Layers 3–4.** tmb/kb artifacts must be interpretable by both humans and models, so the rubric carries both. Disagreements are findings, not noise — a file a model resumes from perfectly but a human finds impenetrable has failed. Protocol: human-label a seed set, test whether an LLM judge reproduces the labels, and automate only if it tracks.

**Error-cost weighting.** Weight by reversibility rather than raw pass rate. Layer 3 and Layer 4 errors are silent and contaminate the corpus every future agent reads, including frontier ones. Offload gating is capability/cost weighted by whether a mistake is caught.

**Reported per layer**, never averaged into a single harness score. A model that nails 90% and silently botches 10% is a good offload target if the 10% can be named.

**Oracle-retrieval condition** — inject known-correct context directly, to separate "the model judged badly" from "qmd surfaced the wrong files" (see §7).

## 7. Confounds & Controls

**qmd's internal model stack sits underneath every arm:** `embeddinggemma-300M-Q8_0` for embeddings, `qwen3-reranker-0.6b-q8_0` for reranking, and `qmd-query-expansion-1.7b_q4_k_m` for query expansion, finetuned from Qwen 1.7B. Pin and version-stamp these, since a qmd upgrade mid-experiment invalidates cross-arm comparison.

**Ceiling effect.** If retrieval is the binding constraint, frontier and local arms bottleneck on the same substrate and the measured gap compresses, making offload look attractive for reasons unrelated to the agent model. Detect via the oracle-retrieval condition.

**Index freshness.** The agent-skills collection was last indexed 2026-07-05 while work continued through 2026-08-08. Stale indexes degrade retrieval for every arm, so reindex before baselining and treat freshness as a controlled variable.

**Second study, higher leverage:** which models produce better qmd results. That lifts every arm at once, including live frontier sessions. Keep it separate from the harness comparison.

## 8. Capability Screen (prerequisite gate)

Direct model invocation, treated as infrastructure rather than an experimental arm. It separates "this model curates knowledge poorly" from "the jinja template mangles nested arguments."

Unit of test: `(weights × quant × chat template × llama.cpp version × parser flag)`. Tool-calling is a property of the stack, not of the model.

**Must include nested-object arguments** — qmd's `query` takes an array of typed sub-query objects, exactly where parsers diverge. Flat string arguments pass nearly everywhere and give a false green.

Re-run on every llama.cpp bump.

Per-model concerns:

- **Qwen3.6-27B** uses the `qwen3_coder` tool parser, thinks by default (so reasoning blocks need controlling on tool-call turns), and has open reports of empty tool calls in agent loops.
- **Gemma4-26B-A4B** requires `--jinja`, and its stock chat template is known to need fixes for some harnesses. The MoE shape with 4B active makes it the more interesting result if it holds tool-call discipline over long sessions.

## 9. Eval-Set Mining from CC/Codex Transcripts

*Script design deferred to a separate conversation. Noted here as a planned component.*

**Available on disk:** 39 CC session JSONL files across 7 projects (~19MB), plus Codex `session_index.jsonl` and `history.jsonl`. Small enough to parse exhaustively, so no sampling is needed.

**What it yields:**

- **Real operation distribution and frequency** — which tmb/kb operations actually dominate by volume. Offloading a twice-a-month operation is worthless regardless of local performance, so frequency should drive which layers get instrumented first. This is currently guesswork.
- **Routing and argument traces** — which command was invoked, with what arguments, and whether the CLI accepted them. Layer 1 and Layer 2 ground truth is partly recoverable directly from exit status.
- **Implicit preference labels from the Zed adapter flow**, already accumulating as a byproduct:
  - `r <file>` reply — an explicit negative label on a specific write.
  - User Cmd+S during the diff window — the user preferred their own version, and *both* versions exist (the snapshot from `pre_edit_zed_snapshot.py` plus the user's final). That is a preference pair, in the format rung 3 of §11 needs.
  - Next-turn natural-language corrections ("no, that belongs in X") — Layer 4 placement labels, the hardest kind to synthesize.

**Framing constraint: candidate miner, not label generator.** Transcripts must not become ground truth.

- **Circularity** — what CC did becomes the gold label, but Layer 3 and Layer 4 quality is exactly what is unverified. A bad placement nobody remarked on would be canonized as correct.
- **Survivorship** — transcripts record what was done, not what was omitted. A silently skipped index regeneration leaves no trace; catching it requires diffing bank state against the transcript.
- **Harness bias** — mining CC transcripts encodes CC's tool surface into the fixture, which then flatters the CC arm. Normalize operations to harness-agnostic descriptions.

Pipeline: mine, producing candidates plus weak signals, then have a human adjudicate a seed set. This is the same protocol as §6's judge validation; the miner makes assembling the seed set cheap rather than tedious.

**Design constraints:**

- Read-only, with output to scratch rather than the repo.
- **Identifier scrubbing is a hard requirement, not a polish step.** Transcripts are saturated with work-item IDs and bank-internal paths. Any checked-in fixture must carry public issue numbers or synthetic IDs per repo hygiene rules. Build scrubbing in from the start, since retrofitting means re-auditing every extracted item.
- CC and Codex store sessions differently, so normalize both into one intermediate schema and let neither shape the fixture.

**Caution:** these transcripts are *not* the CC/Codex reference arm's score. They are observational — different tasks, different context, no controls. They are useful for distribution and weak labels, but the reference arm still runs the actual fixture.

**Sequencing advantage:** the miner depends on none of the §12 blockers. It is read-only over transcripts, so it parallelizes with harness-portability work instead of queuing behind it.

## 10. Transport Study (separate)

Distinct dependent variables, so keep this out of the harness comparison.

MCP-stdio versus a thin HTTP server on the qmd SDK.

The rationale for a unified endpoint is **memory, not protocol**: qmd loads embedding, rerank, and expansion weights per process, so a CLI-per-client footprint scales with client count. The CLI arm is dropped as an unrealistic access pattern.

Measure tool-surface token overhead, per-call latency, and resident memory, using a fixed script with no model in the loop.

## 11. Preference Encoding Ladder

Ordered by cost and reversibility:

1. **Human labels** — measurement only.
2. **Harness layer** — skill files, system prompt, exemplars. Cheap, inspectable, reversible, and expected to capture most of the value.
3. **Weight-level (DPO / LoRA)** — the last rung. It needs label volume unavailable early, **and it binds you to one model, in direct tension with the right-sizing goal of swapping models freely.** Take it only for a preference that demonstrably will not stick via prompting.

The eval set is the same asset at every rung.

## 12. Prerequisites (Phase 0)

**Hard blockers — harness portability:**

- **#45** — the query-kb registry is harness-locked and has no authoring origin. This stops a Pi arm cold: if query-kb only resolves under CC, Pi has no equivalent retrieval path and the arms are not comparable.
- **#16** — document and verify task-memory-bank's permission model. Its assumptions are CC-shaped, and Pi has no permission layer.
- **#62** — establish a script-interface-and-permissions design principle that avoids requiring auto/bypass mode. If tmb scripts need bypass mode, running Pi against them is unsafe or blocked.

**Control-surface defects — these corrupt the baseline, not just the measurement:**

- **#64** — `append_history()` numbers sessions per-date rather than globally, emitting backwards or colliding session numbers.
- **#63** — `work/index.md` "Created" column shows README mtime rather than creation date.

Both sit in Layer 0, the deterministic surface the experiment measures against. A model doing exactly the right thing would still produce wrong output, and the error would be misattributed to the harness. Fix before baselining.

**Sequencing risk:**

- **#21** — redesign task-memory-bank so a project is a declared effort rather than a location. Design doc merged 2026-07-04.

  **Partially landed already, contrary to the bank's own record.** `suggest-projects`, the closed `WorkStatus` enum on `new-work --status`, `migrate-collections`, and worktree-aware repo signals (`selection.py:154`, resolving a linked worktree's canonical main-worktree path via `--git-common-dir`) are all present on `main`. The bank's active context still says no implementation work item exists on this host, so the bank is stale relative to the code and should be reconciled before it is used as a planning input.

  Remaining redesign work still churns Layer 4 fixtures. The upside is that the strict enums already provide machine-checkable invariants, which is exactly the deterministic validator layer the hybrid design wants.

**Also:** one early work item is flagged as opened-but-stalled with status unverified, and the agent-skills collection needs reindexing.

## 13. Sequencing

**Pilot scope: Layer 1 (routing) + Layer 2 (closed-argument synthesis).**

This is the re-scoped pilot. It is self-scoring through the CLI's enum validation, filesystem checks, and `doctor`, so it needs no human label set to produce signal. It is also largely insulated from #21 churn, since the enums it depends on have already landed. Layer 3 and Layer 4 follow once the redesign settles and the judge-validation protocol has a seed set.

1. Transcript miner — operation inventory and frequency (parallel; no blocker dependency)
2. Phase 0: resolve #45, #16, #62; fix #64 and #63; reindex the bank; reconcile the bank against what #21 has already landed
3. Capability screen per `model × quant × template`
4. Layer 1 + Layer 2 fixture (self-scoring)
5. Barebones Pi arm, local models
6. Specialized Pi arm, local models — primary hypothesis test
7. OpenRouter near-frontier row
8. Transport study (parallelizable, independent)
9. Layer 3 extension — free-text synthesis, with human seed labels and judge validation
10. Layer 4 extension — after #21 settles

## 14. Open Questions

- Can Layer 3 and Layer 4 work be offloaded at all, and under what harness conditions? Explicitly open.
- Should `active.md` get a deterministic interface before it is measured, or is it more informative to measure the unscripted case first? Tracked as #68; the answer changes what Layer 4 measures.
- Fixture scale and human-label volume needed for judge validation at Layer 3.
- Definition of "correct" for placement and promotion when human and model judges disagree — whose call governs?

## 15. Preliminary Signal (ad hoc, pre-pilot)

Not part of the controlled experiment — one manual smoke test, logged because it produced a
concrete failure signature worth watching for once the real fixture exists.

**Setup:** a Pi extension (`~/.pi/agent/extensions/local-model-review.ts`, global scope) registers
`qwen3.6-27b-q5km` served from a local llama.cpp host as a provider, plus a `/review-pr`
command that fetches a PR diff via `gh` and hands it to the model with a review prompt. Run
against PR #66 (adapter core extraction), reviewed independently against the actual diff.

**Result: 3 of 4 findings correct, 1 confidently wrong.**

- Two real defects correctly identified and accurately quoted: an O(N) manifest
  read-modify-write loop (`bulk_seed` calling `_load`+`_save` per file instead of batching), and
  a non-atomic manifest write (`_save` writing directly to the final path instead of
  write-temp-then-rename).
- A real policy violation (checked-in tmb identifiers) correctly caught at all 6 occurrences —
  but every claimed line number was off (by 2 to 12 lines), so location precision cannot be
  trusted even when the finding itself is right.
- One finding was **invented but plausible-sounding**: a claimed failure path through
  `os.path.isfile("/dev/null")` returning `True` on Unix and causing silent truncation via
  `shutil.copyfile`. Directly tested: `os.path.isfile("/dev/null")` is `False` (it's a character
  device, not a regular file — `isfile` only follows `S_ISREG`). The premise it was hung on
  (pointer file format changed, so old-format pointers won't resolve at the new path) is true and
  harmless; the specific mechanism asserted for the edge case is fabricated Unix-semantics detail
  dressed up as a verified claim.

**Why this matters for the design:** this is exactly the Layer 3/4 risk named in §6 and §11 —
a silent, confident, wrong claim about system behavior, not a loud validation-rejected error.
A single sample doesn't establish a rate, but it's a concrete instance of the failure mode the
fixture needs to be able to catch, and argues for verifying any local-model-claimed *mechanism*
(not just the flagged location) against actual behavior before trusting it unsupervised.
