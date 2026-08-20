# Task Memory Bank Knowledge Retrieval Design

This note records the design (tracked by
[issue #21](https://github.com/jackys-95/agent-skills/issues/21)) for how the task memory
bank (tmb) selects projects and retrieves context, and how it relates to the broader
knowledge base whose knowledge-file implementation is
[issue #14](https://github.com/jackys-95/agent-skills/issues/14). It captures decisions
made during design discussion so they survive outside the base skill instructions.

This is the historical TMB retrieval design. Its forward-looking descriptions of the knowledge-file implementation are superseded by the current [Knowledge Base Architecture](knowledge-base-architecture.md), which is authoritative for cross-skill taxonomy, catalog ownership, and collection cardinality.

## Scope and sequencing

This ([issue #21](https://github.com/jackys-95/agent-skills/issues/21)) is **phase 1** of the
knowledge base: fixing tmb as that base's first and only existing node, ahead of the
knowledge-file implementation ([issue #14](https://github.com/jackys-95/agent-skills/issues/14)).
The investigation began at "how do
knowledge files join tmb to form the knowledge base?" and immediately surfaced that tmb's own
project abstraction was malformed (location-as-identity, see Problem). You cannot define how a
second knowledge source plugs into a spine that is itself broken, so fixing tmb is a
**design prerequisite** for the rest.

It is a prerequisite by design, not just sequencing: tmb is the first instance of the
knowledge-base pattern, and the reusable pieces every later source will sit on — the retrieval
ladder (Decision 7), `collections.yaml` as source of truth, qmd-registration encapsulation,
and the deterministic-selection / semantic-retrieval split — are settled *here*. Building the
domain-/technical-knowledge skills before these are sound would mean designing the integration
contract twice.

So the knowledge-file skills are a **deliberate follow-on, intentionally out of scope** until
tmb is sound — not a forgotten goal. Decision 8 and the Tier 3 entry in Deferred Decisions
hold their seam open without committing to it.

## Assumptions

- **The harness can execute scripts.** tmb already shells out to `memory_bank.py` for
  init/new-work/etc.; this design assumes the same. A pure-prose harness (no shell) would
  push the deterministic steps below into prose and is out of scope here.

## Problem

The current skill treats a project as a function of **location**: `resolve-project` maps
the current working directory to a project by exact-string match on a single `repo:`
field in `.memory-bank/collections.yaml` (`scripts/memory_bank.py:345`), hard-exiting if
zero or multiple projects match (`:349`, `:352`).

This location-as-identity model breaks on every realistic case:

- **Repo-less projects** — `repo: ""` is tolerated but makes the project invisible to
  resolution.
- **Monorepo, multiple efforts** — several projects share one git root, so exact-match
  resolution is ambiguous.
- **Multi-repo efforts** — one effort spans several repos; a single string cannot express it.
- **Partial-touch efforts** — an effort may modify only a model and one handler in a repo
  it does not "own" in any meaningful sense.

The root error: **a git repo is only a collection of tracked files and history. It carries
no information about which effort a change belongs to.** The repo↔effort relationship is
many-to-many and non-exclusive, so `project = f(location)` is computing a function that
does not exist. Every prior patch (repo → subpath → "anchored location") only narrowed the
domain until the falsehood was less visible.

Separately: how should an agent search *across* projects, and should an umbrella collection
exist to support it?

A third problem surfaces in resume: **work status is an informal, contradictory
vocabulary.** `new_work` writes the literal `active` as a work item's status
(`scripts/memory_bank.py:414`, `:512`) and `setup` as its phase (`:236`, `:452`), while
`references/workflows.md:40` says new items are `open`, its close states are
`done`/`shipped`/`cancelled`/`superseded` (`:153`), and `references/structure.md:139`
defines a *phase* enum (`design|specification|implementation|verification|handoff|paused`)
that does not include the `setup` the script writes. Nothing validates any of it. So an
item is off-vocabulary the moment it is created, and "in-progress" — the signal resume
ranks on — exists only as a negative over an open set ("not closed"), which a deterministic
ranker cannot rely on.

## Decisions

### 1. Project is a declared effort, not a location

A tmb **project is a coherent unit of work/effort**, structured by agile entities
(epic/story/task/spike). Its identity is **declared** — by the user or by the agent reading
intent from the prompt — not derived from cwd, repo, branch, or file path.

Consequences:

- **Repos are *associated*, not *owned*.** A project links to 0..N repos; a repo may be
  linked by several projects. The link is evidence for discovery/ranking, never a boundary
  or an ownership claim.
- **Branch lives at the work-item layer**, not project identity. A work item's `active.md`
  already records `Repo State → Branch`; an effort that spans branches is one project with
  multiple work items/attempts, not multiple projects.
- **No invariant** that "a location maps to ≤1 project." That assumption was the
  location-as-identity error in disguise and is abandoned, along with subpath partitioning
  (which would have forced code layout to bend to the tool and limited code reuse).

### 2. Selection is by declaration; path and search only rank candidates

Resolving "which project/effort is this?" is a **selection** decision, and the authority is
**declaration**, never an algorithm:

- **Authority = explicit declaration.** Writes already take `--project`. When the prompt
  names the effort ("/resume control plane"), the agent commits to it and announces the
  choice — no human turn required.
- **Discovery aids (non-authoritative, produce *ranked candidates* only):**
  - **Repo association** — efforts whose `repos:` include the current repo. Strong when you
    are sitting in a repo a known effort uses; precise; cheap.
  - **Semantic search** — efforts whose memory resembles the task. Strong when the name is
    unknown or for cross-project discovery (Tier 2 below); weak at cold start.
  - Neither *picks*; both *suggest*.
- **Never silently auto-resolve.** The agent must **announce** the selected project so the
  user can correct it before any memory is written or queried; a silent wrong commit
  (writing/querying the wrong project's memory) does not satisfy the bar, but a one-line
  announcement of a confident pick does. **Justification scales with ambiguity** — name a
  brief reason only when choosing among multiple candidates, on a low-confidence pick, or
  when surfacing a cwd/signal conflict. The human is the **escalation path** for genuine
  ambiguity, not a gate on every selection.
- **Correcting a pick must not require recall.** If the user rejects the announced project,
  the agent does not ask them to name the right one from memory. It presents the
  **ranked candidate list** (from `suggest-projects`) — project, description, and any
  in-progress work — for the user to choose from, widening beyond the current repo's
  associations if the user indicates the effort is elsewhere. Only if no candidate fits does
  it fall back to an explicit project name or offer to create a new project.

Using semantic ranking to *select* a project would repeat the location error in a new form:
it derives identity from similarity, which identity does not carry, and at cold start it
confidently returns the nearest *existing* effort precisely when the new one is unknowable.

### 3. Associations are observed, read centrally — no repo-local pointer

Earlier drafts proposed a repo-local pointer file to make resolution O(1). That is
superseded: with selection demoted to ranked-candidates-plus-confirmation, there is no
authoritative lookup to cache, no invariant to disambiguate, and the pointer's only
surviving role (an intent cache) is better served centrally.

- **Repo associations *accrete* from actual work.** When a work item records its
  `Repo State`, that repo is added to the project's `repos:` list in `collections.yaml`.
  Association is *observed*, not declared up front.
- **The agent reads `collections.yaml` directly** (by known path) for routing metadata —
  the project list, descriptions, and associations. No scan-to-resolve, no pointer file
  scattered in each repo, no global-excludes setup, no stale-breadcrumb failure mode.
- **`resolve-project` becomes `suggest-projects`** (a.k.a. resume-candidates): given an
  optional repo, it returns *ranked candidates* joined with work status — never a single
  silent verdict, never a hard exit on multiplicity. Multiple candidates is a normal
  return, handed to the selection judgment in Decision 2.
- **Candidates are unioned across *all discovered bank roots*, not one `--root`.** A machine
  can hold several independent banks (e.g. a knowledge-base domain split can produce distinct
  roots such as `~/memory/task-memory-bank` and `~/Documents/<program>/task-memory-bank`); a
  repo's project may live in any of them, so a single-scope lookup silently misses it. Bank
  roots are enumerated **from qmd's own
  collection catalog** (`qmd collection list` → resolve each `mb-*` collection's path via
  `qmd collection show` → walk up to its nearest `.memory-bank/collections.yaml`), then their
  `collections.yaml` files are unioned for the routing metadata qmd does not hold (`repos:`,
  `description`). This is qmd-derived rather than a hand-maintained roots list because the
  design already makes qmd the cross-project substrate (Decisions 5, 7): a project unreachable
  by qmd is already broken, so qmd's catalog cannot silently drift the way a dedicated-but-
  unmaintained list could. It is **not** a Decision 6 violation — reading qmd's catalog by CLI
  to learn *where banks live* is not qmd-*indexing* config; the coupling is one-way
  (tmb → qmd) and interface-stable. **New coupling to record:** cross-root discovery now needs
  qmd installed (already mandatory for the skill). When no candidate matches, `suggest-projects`
  reports *which* banks it searched and their project/repo counts, so an unregistered repo is
  distinguishable from a wrong-scope lookup at a glance.
- **A git worktree ranks its declared project.** `suggest-projects` identifies the repo by both
  the current worktree's toplevel *and*, for a linked worktree, its canonical main-worktree path
  (`--git-common-dir`), so a sibling worktree ranks the same project as its main checkout instead
  of resolving to nothing. This is ranking evidence, not a location-as-identity rule (Decision 1).

### 4. Keep the 1:1 project ↔ collection mapping

A collection is qmd's unit of query *scoping* (`-c`) and embed *batching* (`qmd embed -c`)
— not its unit of retrieval, which is the document/chunk. A project is the natural boundary
at which we want queries scoped and embeds batched, so it is the correct granularity for a
collection. The 1:1 mapping is load-bearing for two properties a single shared collection
cannot provide:

- **Scoped query** — qmd scopes queries by collection *name* only (`-c`/`--collection`).
  There is no `--context` or `--path` query filter, so a single shared collection would
  draw all projects into one global top-K pool and leak cross-project results.
- **Incremental embed** — `qmd embed`/`qmd update` are scoped per collection. There is no
  sub-collection embed scope, so per-project collections are required to re-embed one
  project's changes without touching others.

A shared collection also underrepresents small collections in a shared top-K pool (per the
qmd README), starving the project an agent is actually resuming.

### 5. No umbrella collection

An umbrella `task-memory-bank` collection (recursive over the bank root) is removed:

- **Doubles embedding cost** — every file belongs to both `mb-<project>` and the umbrella.
- **Leaves umbrella vectors stale** — `qmd update` has no collection scope and re-indexes
  every collection, but `qmd embed` is scopeable and `reindex` scopes it to the resolved
  project (`scripts/memory_bank.py:571`). After an edit the umbrella's chunks are re-indexed
  but its vectors are never re-embedded; keeping them correct means re-embedding the
  umbrella too — the doubled cost above.

Cross-project search is done by multi-collection query (Decision 7), not an umbrella. This
also means **bank-root config is never qmd-indexed**, which is correct — see Decision 6.

### 6. Config and generated indexes are path-accessed; only memory content is queried

A clean separation of access modes:

- **`collections.yaml` = source of truth (machine + agent read directly).** It holds
  per-project config: collection name, path, observed `repos:`, `description`, `domain`,
  qmd `context`. Read by `memory_bank.py` and by the agent via the `Read` tool by known
  path. **Never qmd-indexed** — routing is deterministic, not a search.
- **`registry.md` is dropped.** It was only a human-readable rendering of data that is
  already legible in `collections.yaml`; maintaining a generated second copy adds a
  sync burden for no reader that `collections.yaml` does not already serve. If a
  browsing-human view is ever wanted, regenerate it from `collections.yaml` then.
- **Per-project `.memory-bank/collection.yaml` is dropped.** Its original rationales —
  portability ("travels with the project") and indexability ("indexed when qmd includes
  YAML") — are superseded: config is centralized, and a detached travelling copy would
  carry a stale association snapshot. One fewer file to keep in sync.

Only project **memory content** (under `projects/<project>/`) is qmd-indexed, via the
per-project `mb-*` collection.

#### Storage format: YAML, with a round-trip parser

`collections.yaml` stays **YAML**, chosen for **inline comments as semantic context** — the
primary reader is now an LLM interpreting fields whose names do not fully carry their meaning
(e.g. annotating that `repos:` is *association, not ownership* at the point of use). JSON
cannot carry that grounding inline, and its only real advantage here (transform-free machine
reading) is moot once the consumer reads the file as text anyway.

The hand-rolled regex parser (`parse_collections`/`write_collections`) must be **replaced
with a real comment-preserving YAML library** (e.g. `ruamel.yaml`). This is required, not
optional: the current parser cannot represent the `repos:` list, and a naive emitter would
erase comments every time `new-work` rewrites the file to accrete an association — which
would defeat the reason for keeping YAML.

### 7. Hybrid retrieval — select deterministically, retrieve semantically

This ladder serves **every context-needing operation**, not just resume — starting or
continuing work ("have I solved this before?"), authoring a design/decision (checking prior
decisions or cross-project precedent), and any task needing domain grounding all draw on the
same tiers. Resume (Decision 9) is one *consumer*: its hydrate step is just Tier 0–1. The
two payoffs below — cross-project learning (Tier 2) and external-knowledge fallback (Tier 3)
— are mid-work retrieval, rarely resume.

The deterministic-vs-semantic line is between **selection** (which collections — always
declaration-led per Decision 2) and **retrieval** (searching within the selected set, which
may be broad and semantic). Retrieval follows a confidence-gated escalation ladder, default
tight, widening only on demand:

- **Tier 0 (default)** — deterministic: chosen project entrypoints (`README.md`,
  `active.md`, work item files) and `work/index.md` by known path.
- **Tier 1** — semantic search within the current project collection (`-c mb-current`).
- **Tier 2** — semantic search across *selected related* projects (multi-`-c`, chosen from
  the `description`/associations in the `collections.yaml` of *all discovered bank roots*, not
  one `--root` — see Decision 3). Use `--min-score` rather than default top-K to avoid
  underrepresenting smaller collections.
- **Tier 3** — hand off to a knowledge-base skill (Decision 8) when the agent judges it
  lacks domain or technical grounding.

The agent should narrate *why* it escalates. This unlocks **cross-project learning** (Tier
2) and **external-knowledge fallback** (Tier 3) the prior design could not serve.

`description` (in `collections.yaml`) is **pre-query routing input** for Tiers 2–3: read
*before* querying to decide which collections to fan out to. It is read-and-reasoned, not
embedded — it is **not** searchable corpus content and is **not** copied into the README.
(A project's README/overviews are the searchable text, indexed naturally inside its own
collection; reaching a README already implies a collection was selected.)

### 8. External knowledge is sibling-skill-owned (issue #14)

Per [issue #14](https://github.com/jackys-95/agent-skills/issues/14), domain knowledge and
technical knowledge will be **separate RAG skills**, each owning its own collections,
descriptions, and retrieval idioms. tmb does not catalog or query foreign collections
directly. Tier 3 is a **skill handoff**, not a query into another namespace.

| Skill | Owns | Knowledge type | Lifespan |
|---|---|---|---|
| task-memory-bank | `mb-*` collections | what *I* did / am doing | per-task, episodic |
| domain-knowledge (#14) | domain collections | valid states/ops in the domain | cross-task, semi-stable |
| technical-knowledge (#14) | technical/ML/math collections | grounding for pretrained knowledge | cross-task, stable |

Because #14 has no integration spec yet, tmb exposes a **named seam** for Tier 3 ("delegate
to a knowledge-base skill if available") without hardcoding collection names or a call shape.

### 9. Resume workflow — script gathers facts, prose decides

Resume was always agent-orchestrated prose; only its one mechanical helper
(`resolve-project`) was a script command. That split is preserved — we only upgrade the
helper, because the deterministic portion of resume grew from one lookup to several.

**Deterministic spine (`memory_bank.py suggest-projects`)** — gathers and ranks facts,
never decides:

1. Resolve cwd's repo — its worktree toplevel and, for a linked worktree, the canonical
   main-worktree path (Decision 3) — as evidence, not an answer.
2. From the `collections.yaml` of *every discovered bank root* (Decision 3), find efforts whose
   `repos:` include this repo (candidate set), unioned across banks.
3. For each candidate, read `work/index.md` status column → collect in-progress work.
4. Rank by association + status (+ recency only to order the shortlist) and return
   structured candidates with conflict flags; on zero, report the banks searched.

**Judgment (prose in `references/workflows.md`, under `memory.resume`)** — consumes that
output:

- exactly one high-confidence candidate, no conflict → resume it, **announce** the choice
- multiple candidates, or a flagged cwd-conflict → present the shortlist, **ask** which
- explicit signal in the prompt → **select by it**; cwd only ranks/flags and never overrides
  an explicit declaration; if cwd contradicts, proceed but surface the mismatch
- after selection → **hydrate** by invoking the Decision 7 ladder (Tier 0 known-path reads
  of the work item's entrypoints, Tier 1 the work item's Resume Query in qmd if more is
  needed) — resume does not define its own retrieval, it consumes the shared ladder

Selection signals, by role: **explicit declaration** = identity (overrides); **status** =
primary ranker when no explicit signal (in-progress work from `work/index.md`, per the
migrated Cline `resume-task.md` model); **repo association / cwd** = ranker and
conflict-flag, never authority; **recency** = shortlist ordering only.

#### Ranking is deterministic; the LLM judgment is the prose pick, not a reranker

`suggest-projects` ranks on **structured, discrete signals** (status class, association
count, recency timestamp), so ranking is a **deterministic sort** — reproducible, testable,
cheap, and run inside the fact-gathering step that is designed *not* to decide. No reranker
LLM belongs in the script: the LLM "rerank" already exists one layer up as the agent's prose
pick, which has the user's full intent that the ranker lacks. (Fuzzy Tier-2 "which related
efforts?" discovery, if added, is qmd's semantic rank followed by the agent's judgment —
still not a bespoke reranker.)

A deterministic sort requires a **strict, ordinal status type**. The existing status
vocabulary is informal and contradictory (see Problem), so it must be **formalized and
reconciled into a closed `WorkStatus` enum** — e.g. `open` → `in-progress` →
`paused`/`blocked` → `done`/`shipped`/`cancelled`/`superseded` — defined once in
`memory_bank.py` (mirroring the existing `WORK_TYPES`), **validated on write** by
`new-work`/`update`/close, and surfaced in `work/index.md`. The enum supplies the ordinal
the ranker sorts on; "in-progress" becomes a *positive* enum value rather than a negative
over an open set. Default sort precedence: `(status ordinal, association, recency)`.

`Phase` (`design|specification|implementation|verification|handoff`, plus reconciling the
script's stray `setup`) is a **separate, non-ranking enum** — kept distinct so "status" is
not re-overloaded with workflow phase. Association (count) and recency (timestamp) need no
enum; they sort on their natural types.

## Orchestration & Packaging

- **Trigger:** the harness loads the skill via `SKILL.md` frontmatter (`description`); the
  Claude Code adapter additionally exposes `memory-resume` as a user-invocable slash command
  (`disable-model-invocation: true`), mapping `$ARGUMENTS` to the explicit-signal branch.
- **Mechanism vs. judgment:** deterministic fact-gathering and ranking live in
  `memory_bank.py` (one `suggest-projects` call); selection/confirm/hydrate judgment lives in
  `references/workflows.md`. Minimizing the multi-step sequence the agent must follow in prose
  is deliberate — prose sequencing is the least reliable part of a skill.
- **No new skill.** Resume is the existing `memory.resume` canonical workflow; we deepen it
  in `references/workflows.md` and upgrade its script helper. The thin Claude Code wrapper
  (`memory-resume → memory.resume`) is logic-free and needs **no change** — reinstall only.

## Validation notes (dogfooding)

Observed while initializing this very effort's memory bank (`mb-agent-skills`) with the
current, pre-redesign script:

- **`init-project` does not register the collection with qmd — it only *prints*
  suggestions.** The `qmd collection add` / `qmd context add` commands are emitted as text
  (`scripts/memory_bank.py:305-308`) for a human to run. So `collections.yaml` (which the
  redesign makes the source of truth, Decision 6) and qmd's actual index can silently
  drift: the config can claim a collection that qmd never indexed. The redesigned
  `init-project` should *invoke* registration (or `doctor` should detect config-vs-qmd
  drift), closing the "config written but qmd never told" gap.
- **The suggested `qmd context add` command is wrong on both arguments.** The script prints
  `qmd context add <project> <readme-path>` (`:308`), but the real CLI is
  `qmd context add [path] "summary text"` — a virtual/collection path plus a human-written
  summary string. Run verbatim it fails (qmd reads the project name as a filesystem path)
  and, even corrected, attaches a *file path* where prose belongs. The registration step,
  once `init-project` owns it, must use `qmd context add qmd://<collection>/ "<summary>"`
  with a generic collection-level description (not an effort-specific one).

These reinforce Decision 6 (centralized config as source of truth) and the Scope item
folding registration into the script.

## Scope

- Schema (`collections.yaml`): `repo:` → `repos:` list; add `description`, optional
  `domain`/tags; remove the `kind: global` umbrella entry.
- Parser: replace hand-rolled `parse_collections`/`write_collections` with a
  comment-preserving YAML library.
- `init-project`: accept `--description`, optional repeated `--repo`, optional `--domain`;
  *invoke* qmd registration (`qmd collection add`, then `qmd context add qmd://<collection>/
  "<summary>"`) rather than only printing it, so `collections.yaml` and qmd's index cannot
  drift (see Validation notes).
- `new-work`: accrete the work item's repo into the project's `repos:` association list;
  write an enum-valid initial `WorkStatus` (`open`) instead of the current ad-hoc `active`.
- Status types: add a strict `WorkStatus` enum and a separate `Phase` enum to
  `memory_bank.py`; validate on write in `new-work`/`update`/close; reconcile the existing
  `active`/`open`/`setup` contradictions across the script and references.
- `resolve-project` → `suggest-projects`: return ranked candidates joined with `work/index.md`
  status, sorted deterministically by `(WorkStatus ordinal, association, recency)`; no hard
  exit on multiplicity.
- Remove `registry.md` generation and the per-project `.memory-bank/collection.yaml` manifest.
- `doctor`: stop requiring `repo` (repo-less is legitimate); drop the invariant/no-nesting
  and registry-sync checks; warn on `repos:` entries pointing at vanished paths.
- `references/workflows.md`: expand `memory.resume` with the selection/confirm/hydrate
  judgment; SKILL.md keeps its slim pointers and adds the Tier 2–3 escalation ladder + the
  Tier 3 handoff seam.

## Non-Goals

- Do not build the domain-knowledge or technical-knowledge skills here (issue #14).
- Do not define the cross-skill handoff contract before #14 specifies it.
- Do not introduce semantic ranking into project *selection* (retrieval may be semantic).
- Do not reintroduce location-as-identity: no subpath partitioning, no per-location
  ownership, no repo-local pointer.
- Do not change the "never use filesystem tools to explore or search the memory bank" rule;
  reading `collections.yaml` / known entrypoints by exact path is deterministic access, not
  the tree-exploration the rule prevents.

## Deferred Decisions

Each item names the open question, why it is deferred rather than decided now, and what it
blocks. The structural decisions above stand without these; these are tuning and integration
details that need real data or an external spec to settle well.

- **`suggest-projects` ranking weights and the auto-proceed threshold.** Decision 9 fixes the
  sort *precedence* — `(WorkStatus ordinal, association, recency)` — but not how the three
  combine when they disagree (e.g. does a stale `in-progress` outrank a fresh `open`?), nor
  the confidence bar at which the prose layer resumes a top candidate silently vs. asks.
  *Deferred* because sensible weights need observed candidate sets to tune against; guessing
  now risks a ranker that looks principled but mis-orders real banks. *Blocks* nothing
  structural — the script returns ranked candidates regardless; this only tunes their order
  and the announce-vs-ask cutoff in Decision 2.

- **`description`/`domain` schema shape, and how the agent uses it to pick a Tier 2 fan-out
  set.** Decision 7 says `description` is pre-query routing input read from `collections.yaml`
  to choose *which* sibling collections to query at Tier 2, but not the field's structure
  (free prose? tags? a `domain` taxonomy?) nor the matching procedure (LLM reads all
  descriptions and judges? string/tag overlap with the task?). *Deferred* because the right
  shape depends on how many projects a real bank accumulates — a handful needs nothing,
  dozens may need tags. *Blocks* Tier 2 fan-out quality (selection-side, not whether Tier 2
  works); pairs with the next item.

- **Whether `suggest-projects` itself scores semantic similarity, or Tier 2 discovery is left
  entirely to prose.** Two ways to find related projects: have the *script* embed/score the
  task against project descriptions and return similarity-ranked candidates, or have the
  *agent* read descriptions and judge in prose (Decision 7's current stance). The first is
  reproducible and cheap but pulls a semantic step into the deterministic spine that Decision
  9 deliberately keeps judgment-free; the second keeps the spine clean but leans on prose
  reliability. *Deferred* because it trades off against the schema item above (tags make prose
  matching viable; their absence pushes toward scripted similarity) and shouldn't be settled
  before that. *Blocks* the `suggest-projects` contract for Tier 2 (the resume/selection-side
  use needs no similarity).

- **The Tier 3 knowledge-base handoff contract.** Decision 8 commits to a *named seam*
  ("delegate to a knowledge-base skill if available") but not the call shape: how tmb
  discovers the sibling skill, what intent/context it passes, and what it gets back. *Deferred*
  because [issue #14](https://github.com/jackys-95/agent-skills/issues/14) has not specified
  the domain-/technical-knowledge skills yet; defining a contract against an unbuilt
  counterpart would hardcode assumptions likely to be wrong. *Blocks* only Tier 3 (Tiers 0–2
  are self-contained); the seam lets the rest ship without it.

- **Migration of existing single-string `repo:` entries to `repos:` lists.** The schema change
  in Scope (`repo:` → `repos:`) needs a one-time conversion for any bank already on disk.
  *Deferred* because it is mechanical and low-risk, and its shape depends on whether we also
  migrate the dropped `registry.md`/`collection.yaml` in the same pass. *Blocks* nothing in
  the design; it is an implementation-time chore, noted so it is not forgotten. (This bank,
  `mb-agent-skills`, is itself a single-string-`repo:` instance that will need migrating.)
