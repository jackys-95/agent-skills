# Task Memory Bank reindex — hook-driven, marker-based design

**Status:** implemented for Claude Code and Codex; installer and hook tests pass,
with live Codex end-to-end verification pending
**Date:** 2026-07-02
**Component:** shared adapter runtime (`adapters/core/`) plus harness-specific
detectors and installers

> **Amended 2026-08-11** Codex parity is now implemented. Collection discovery,
> dirty-marker state, and deferred flushing live in `adapters/core/`. Claude Code
> reads `tool_input.file_path`; Codex parses successful `apply_patch` bodies.
> Deterministic `memory_bank.py` writes emit the same marker directly because
> Codex Bash payloads do not expose canonical changed paths. Both installers
> register `PostToolUse`, `UserPromptSubmit`, `SessionEnd`, and `SessionStart`
> hooks in their native configuration.

> **Amended 2026-07-03** Two changes to this record:
>
> 1. **§5 "Placement" is superseded.** §5 asked "is this Zed-specific?" but never "is this
>    CC-specific?" — the hooks are CC-specific three ways (CC event names, CC stdin payload schema,
>    `~/.claude` deployment path), so they violate the repo's "Core Skill Remains Canonical"
>    decision when placed inside the skill. The hook scripts now live in
>    `adapters/claude-code/hooks/`, registered by the same CC installer. §5's installer-separation
>    reasoning (CC hooks vs. Zed hooks, neutral shared helper) still stands.
> 2. **§1's Requirement is promoted into skill canon.** The settled-state invariant ("the index
>    reflects only settled state, never provisional writes") originated here as a one-adapter design
>    requirement derived from the Zed diff-review scenario; we promote it into
>    `SKILL.md` Core Rules in harness-neutral wording. "Never reindex mid-turn" is this adapter's
>    *implementation* of the invariant, not the invariant itself.

> **Supersedes the daemon direction in [`task-memory-bank-watcher.md`](task-memory-bank-watcher.md).**
> That note proposed a long-running `chokidar` filesystem watcher with debounce windows. A watcher
> reindexes the instant a file changes — i.e. *during* the Zed diff review window, before the user
> has accepted, reverted, or edited — which is the exact failure this design exists to avoid (§2).
> The watcher note's *goal* (keep qmd fresh on tmb writes) and its **non-goals** (don't parse
> markdown, don't reimplement qmd indexing, reindex = `qmd update` + `qmd embed`) still hold; only
> the trigger mechanism changes from a daemon to lifecycle hooks.

---

## 1. Problem

The task-memory-bank skill tells agents to reindex qmd "after structured writes when the watcher is
not known to be running." With no watcher running (the common case), the naive reading is "run
`memory_bank.py reindex` inline, mid-turn, right after writing the markdown." Two things go wrong:

1. **Churn before the content under review.** The Zed adapter batches diffs to the `Stop` hook — an
   inline reindex runs its visible `qmd update` / `qmd embed` pass *before* the diffs the user is
   about to review even open.
2. **Indexing an about-to-be-undone state (the crux).** Memory-bank files are out-of-project edits,
   so they appear in the Zed diff exactly like code and are equally revertible (`r <file>`) or
   editable (Cmd+S). Reindexing at write time — or at `Stop`, when the review window *opens* —
   captures content the user may immediately revert or change. The index then reflects a disk state
   that no longer exists until something re-triggers a reindex.

**Requirement:** reindex only *settled* memory-bank state — after the user's revert/edit window for
that turn has closed — while never running a visible reindex mid-turn, and never running one at all
when the bank did not change.

## 2. Why not a watcher / daemon

| Trigger | Freshness | Indexes about-to-be-reverted state? | Runtime cost |
|---|---|---|---|
| **`PostToolUse` reindex** (immediate on write) | immediate | **Yes** — worst timing; fires before the diff even opens | none |
| **Filesystem watcher / daemon** (the old note) | seconds | **Yes** — fires on write, mid-review; needs window-awareness to fix | long-lived process, lifecycle, PID/scoping |
| **Deferred lifecycle hooks** (this design) | one turn behind | **No** — only settled state | none (short hook invocations) |

A watcher does not solve the timing problem; it hard-codes the worst timing. Making it correct means
teaching it to *wait* for the review window to close — at which point it has re-implemented the
deferred-trigger logic below, but as a daemon with lifecycle to manage. `qmd` has **no native watch
command** (confirmed against the installed binary: `Maintenance` is only `update` / `embed` /
`cleanup`). So the choice is deferred hooks vs. building+running a daemon; deferred hooks win on
correctness *and* simplicity.

## 3. Design: mark on write, reindex on lifecycle boundaries

Split detection from execution. A `PostToolUse` hook only **marks** that a tracked location changed;
the actual reindex runs at lifecycle boundaries that are guaranteed to be *after* the review window.

| Event | Matcher | Action |
|---|---|---|
| `PostToolUse` | CC: `Edit\|Write`; Codex: `^apply_patch$` | Extract changed paths using the harness payload, then mark every containing collection dirty. **No reindex** runs during the review window. |
| `UserPromptSubmit` | — | For each dirty marker: reindex that collection (detached, silent), then clear the marker. Covers every turn *except the last*; fires at the start of turn N+1, after turn N's review window closed. |
| `SessionEnd` | — | Same as above. Covers the **final turn** of a session (which has no turn N+1). |
| `SessionStart` | CC: —; Codex: `startup\|resume\|clear` | Same as above. In a clean session the marker was already cleared, so this **no-ops**; it only does work when a prior session was interrupted after a write. Codex excludes `compact` because that source can occur mid-turn. |

`memory_bank.py` commands that write task-memory-bank files mark their known
project collection directly. This is a write notification only; lifecycle hooks
still own the deferred reindex. It avoids unreliable shell-command parsing while
keeping direct knowledge-file and hand-edited memory writes covered by tool hooks.

### Why the marker is the keystone

The marker unifies all three reindex triggers and makes each one cheap and non-redundant:

- **No wasted passes.** A turn (or whole session) that never touches the bank leaves no marker, so
  every trigger no-ops. Reindex runs *only* when the bank actually changed.
- **`SessionStart` becomes precise.** Without the marker, reindexing on every session start is a
  blind extra pass. With it, `SessionStart` fires only in exactly the gap the other two events miss
  — a hard kill that skipped `SessionEnd` — and costs nothing otherwise.
- **Idempotent clearing.** Whichever of `UserPromptSubmit` / `SessionEnd` / `SessionStart` fires
  first clears the marker; the rest see nothing. No double reindex.

### Coverage argument

- Normal turn → `PostToolUse` marks → next `UserPromptSubmit` reindexes settled state. ✓
- Last turn of a clean session → `SessionEnd` reindexes. ✓
- Hard kill (no `SessionEnd`) → marker survives → next `SessionStart` reindexes. ✓
- Turn/session that never writes the bank → no marker → all triggers no-op. ✓
- **Nothing ever reindexes mid-review** — `PostToolUse` only marks. ✓ (satisfies §1's crux)

## 4. Marker protocol

- **One marker file per dirty collection**, so reindex is collection-scoped: a knowledge-base edit
  does not force a re-embed of a tmb project collection, and vice-versa. Marker lives in **`/tmp`**
  with the collection name in the path (e.g. `/tmp/tmb_qmd_dirty_<collection>`); contents hold the
  collection name for the reindexer to read. `/tmp` is intentional — it clears on reboot, and a
  reboot implies no pending session to reindex, so a lost marker is never a lost update.
- **Tracked roots come from qmd's config file directly — no hardcoded paths, no subprocess, no
  dependency on query-kb's git-ignored `registry.yaml`.** qmd keeps a single human-readable registry
  at **`${XDG_CONFIG_HOME:-~/.config}/qmd/index.yml`** listing *every* collection
  with its `path` and `pattern`:

  ```yaml
  collections:
    mb-agent-skills:
      path: /Users/example/memory/task-memory-bank/projects/agent_skills
      pattern: "**/*.md"
    example-knowledge:
      path: /Users/example/Documents/knowledge
      pattern: "**/*.md"
    # … tmb + KB collections, all in one file
  ```

  The `PostToolUse` hook reads this one ~1 KB YAML and maps the edited path to a collection by
  longest matching `path` prefix; a path under no collection root is ignored (fast no-op — the common
  case for ordinary code edits). This covers **every** indexed location the user has registered — tmb
  project collections *and* KB collections (e.g. `example-knowledge`) — with no per-machine config.
  - **No cache — read `index.yml` per hook (decided).** `PostToolUse` fires on *every* `Edit|Write`,
    but reading + parsing a ~1 KB YAML has no process-spawn cost (unlike `qmd collection list`/`show`),
    so no cache is warranted. Reading the file directly also means freshness is automatic — the file
    *is* the source of truth, so every hook sees current roots with zero staleness and no invalidation
    logic. (Distinct from qmd's *derived* index at `~/.cache/qmd/index.sqlite`, which is what `qmd
    update`/`embed` rebuild — never read by this hook.)

### 4.1 Why `index.yml` is the right source (not a skill registry)

Three registries exist, and **none** is the path source of truth — that is `~/.config/qmd/index.yml`
alone:

| Registry | Owner | Holds | Does NOT hold |
|---|---|---|---|
| `~/memory/task-memory-bank/.memory-bank/collections.yaml` | tmb skill | tmb **project** collections + paths | KB collections |
| `~/.config/qmd/registry.yaml` | query-kb skill | KB **classification** (`contains`/`domain`) | paths/patterns (delegates to qmd); tmb collections |
| **`~/.config/qmd/index.yml`** | qmd | **every** collection's `path` + `pattern` | classification |

Reading a *skill* registry instead would be wrong on two counts. First, neither skill registry holds
paths for *all* collections — `collections.yaml` omits KB, query-kb's `registry.yaml` omits paths
entirely (it delegates them to qmd). Second, registration is **asymmetric** and partly manual:

- **tmb** collections: `init-project` writes the bank registry and invokes
  `qmd collection add` plus `qmd context add`.
- **knowledge** collections: registered by the `knowledge-files` authoring skill, whose new-collection workflow appends a `contains`/`domain` entry to query-kb's registry (at `~/.config/qmd/registry.yaml`) alongside a `qmd collection add` for the path. A human `qmd collection add` plus a hand-edited registry line also works.

A human `qmd collection add` bypasses any skill anyway — but every path **rewrites
`~/.config/qmd/index.yml`**. So reading `index.yml` directly is the one source that stays correct
across all registration routes, present and future, with no per-skill wiring. (This is also why, if a
cache were ever reintroduced, its invalidation would key on `index.yml`'s mtime — but per §4 there is
no cache.)
- **Reindex = `qmd update` then `qmd embed -c <collection>`**, run **detached with output
  suppressed** (`Popen(..., stdout=DEVNULL, stderr=DEVNULL)`) so it never churns the pane regardless
  of when it fires.
  - **`update` cannot be scoped; `embed` can — and `embed` is the cost that matters.** `qmd update`
    takes no collection flag (`qmd update [--pull]`), so it always re-scans *all* collections — but
    that is only a cheap change-scan. `qmd embed` takes `-c <name>` (`qmd embed [-f] [-c <name>]`),
    the expensive model/embedding pass. So scope `embed` to the modified collection; accept the
    unavoidable global `update`. Net effect: only the modified collection is actually re-embedded.
  - **Multiple dirty collections at one boundary:** run `qmd update` **once**, then `qmd embed -c`
    **per dirty collection** — never `update` per marker.

### 4.2 Ephemeral state

Dirty markers are the only scratch state. They live in the platform temporary
directory (`tempfile.gettempdir()`, normally `/tmp`) and can be redirected with
`TMB_REINDEX_MARKER_DIR` for tests. Collection roots are read directly from
qmd's configuration on each detector invocation, so there is no root-map cache
or cache invalidation lifecycle.

## 5. Placement

The implementation has three ownership layers:

- `adapters/core/reindex_state.py` owns qmd collection lookup and the neutral
  marker protocol.
- `adapters/core/reindex_dirty_collections.py` owns detached, collection-scoped
  flushing.
- Harness adapters own payload extraction and native registration. Claude Code
  uses `adapters/claude-code/hooks/post_edit_mark_dirty.py` and
  `~/.claude/settings.json`; Codex uses
  `adapters/codex/hooks/post_apply_patch_mark_dirty.py` and
  `~/.codex/hooks.json`.

The canonical memory script emits only the dirty signal for deterministic writes;
it does not contain lifecycle or hook-payload logic. Claude Code, Codex, and Zed
installers remain independent and merge their own definitions without importing
another adapter.

## 6. Skill guidance change

> **Wording superseded on 2026-07-03.** The replacement text below leaks CC event names
> and "mid-turn" into the canonical skill; `SKILL.md` now states the neutral settled-state
> invariant instead, and event mechanics live only in this doc and the adapter docs.

Replace the current instruction in `skills/task-memory-bank/SKILL.md`
("Reindex qmd after structured writes when the watcher is not known to be running") and the inline
`memory_bank.py reindex` snippet with:

- Reindex is handled by lifecycle hooks (`PostToolUse` mark → `UserPromptSubmit` / `SessionEnd` /
  `SessionStart` reindex). **Do not run `reindex` inline mid-turn** — it churns the pane and can
  index an about-to-be-reverted memory-bank edit.
- If the hooks are not installed on a given machine, defer any manual reindex to the very end of the
  response (never mid-turn), and note if qmd is unavailable.

## 7. Resolved & open decisions

**Resolved:**

- **Marker location → `/tmp`.** Cleared on reboot, which is fine: a reboot implies no pending
  session to reindex, so a lost marker is never a lost update. Avoids polluting/ignoring the bank.
- **Collection roots → read directly from `~/.config/qmd/index.yml`** (one YAML listing every
  collection's `path` + `pattern`), not from `qmd` subprocesses, `collections.yaml`, or query-kb's
  `registry.yaml`. Covers tmb and KB collections uniformly with zero per-machine config (§4). No
  subprocess on the hot path, so a cache is optional.
- **No cache.** Read `index.yml` directly per hook — a ~1 KB YAML parse with no subprocess. Freshness
  is then automatic (the file is the source of truth) and there's no invalidation logic to maintain.
- **Reindex scope → global `update`, per-collection `embed`.** `qmd update` has no `-c` flag so it
  always re-scans all collections (cheap change-scan); `qmd embed -c <name>` scopes the expensive
  pass to the modified collection. Multiple dirty collections at one boundary: `update` **once**,
  then `embed -c` per collection (§4).
- **Shared runtime, separate registration.** Reindex state and flushing live in
  `adapters/core/`; Claude Code and Codex each provide their own detector and
  installer wiring. Zed review hooks remain independent.

**Open:**

- Live Codex verification should confirm install, `/hooks` trust, direct
  `apply_patch` marking, next-turn flush, final-session flush, and coexistence
  with the ZedCodex hook set.

## 8. Non-goals (inherited from the watcher note)

- Do not parse markdown, cache contents, or maintain checksums.
- Do not reimplement qmd indexing outside qmd.
- Do not require the hooks for correctness — explicit `memory_bank.py reindex` must still work.
