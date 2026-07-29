# Task Memory Bank reindex — hook-driven, marker-based design

**Status:** implemented — hooks + installer wiring + `reindex --collection` landed, unit-tested;
live end-to-end verification pending
**Date:** 2026-07-02
**Component:** claude-code adapter (`adapters/claude-code/hooks/`);
interacts with the Zed adapter's per-turn diff hooks (`adapters/zed/`)

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
| `PostToolUse` | `Edit\|Write` | If the edited path is under a tracked collection root, write a **dirty marker** for that collection. **No reindex** — nothing fires during the review window. |
| `UserPromptSubmit` | — | For each dirty marker: reindex that collection (detached, silent), then clear the marker. Covers every turn *except the last*; fires at the start of turn N+1, after turn N's review window closed. |
| `SessionEnd` | — | Same as above. Covers the **final turn** of a session (which has no turn N+1). |
| `SessionStart` | — | Same as above. In a clean session the marker was already cleared, so this **no-ops**; it only does work when a prior session was **hard-killed** (SIGKILL) after a write, leaving the marker on disk. Crash-recovery net. |

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
  with the collection name in the path (e.g. `/tmp/cc_tmb_dirty_<collection>`); contents hold the
  collection name for the reindexer to read. `/tmp` is intentional — it clears on reboot, and a
  reboot implies no pending session to reindex, so a lost marker is never a lost update.
- **Tracked roots come from qmd's config file directly — no hardcoded paths, no subprocess, no
  dependency on query-kb's git-ignored `registry.yaml`.** qmd keeps a single human-readable registry
  at **`~/.config/qmd/index.yml`** listing *every* collection with its `path` and `pattern`:

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

- **tmb** collections: `init-project` only *prints* `qmd collection add` today (auto-registration is
  backlog under [#21](https://github.com/jackys-95/agent-skills/issues/21)).
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

### 4.2 Two artifacts, two homes

This design writes two kinds of scratch state, and they do **not** belong in the same place:

| Artifact | Nature | Home | Why |
|---|---|---|---|
| **dirty markers** | per-session, ephemeral — "this session wrote collection X and hasn't reindexed" | **`/tmp`** | A reboot ends the session, so a marker has no meaning afterward. Losing it on reboot is *correct*, not just tolerable. |
| **root-map cache** | machine-global, derived — a read-through cache of qmd's collection→path map | **stable per-user cache dir** (`~/.cache/cc-tmb-reindex/` or under `~/.claude/`) | Identical across every session and repo; nothing session-scoped to discard. `/tmp` would throw it away every reboot and force a needless rebuild-from-qmd on the next session's first write. Living beside qmd's config also makes mtime-invalidation (§4.1 option 1) a clean two-stable-paths comparison. |

The root-map cache *tolerates* `/tmp` (a lost cache is cheap to rebuild — a couple of `qmd` calls),
but "cheap to rebuild" argues it survives loss, not that it belongs in ephemeral storage. Only the
markers have a positive reason to be ephemeral.

## 5. Placement

> **Superseded on 2026-07-03 — see the amendment banner.** The "logic belongs to the
> skill" conclusion below missed that the scripts themselves are CC-specific; they now live in
> `adapters/claude-code/hooks/`. The installer-separation analysis remains valid.

Separate the hook's **logic** from its **registration**:

- **Logic (the hook scripts) belongs to the task-memory-bank skill** — reindex is a memory-bank
  concern with nothing Zed-specific, and the scripts sit naturally beside `memory_bank.py`.
- **Registration belongs to the CC installer** (`scripts/install_claude_code.py`) — these are
  Claude Code hook *events* (`PostToolUse`, `UserPromptSubmit`, `SessionEnd`, `SessionStart`),
  wired into `~/.claude/settings.json`. That is CC-harness config, so it rides with the CC install,
  not the editor-agnostic skill copy.

**Two installers stay separate — CC hooks and Zed hooks must not be coupled.** A user who runs CC
without Zed must be able to install the reindex hooks without pulling in *any* Zed adapter code, and
vice-versa. So:

- The **reindex hooks** are registered by the CC installer (`scripts/install_claude_code.py`).
- The **Zed diff hooks** stay registered by `adapters/zed/install.py`.
- Neither installer imports the other, and neither is a prerequisite for the other.

**Caveat — the CC installer cannot register hooks today.** `scripts/install_claude_code.py`
currently installs skills, the qmd skill, and CLAUDE.md blocks only; it has **no** `settings.json`
hook-registration code. The only such machinery is `adapters/zed/install.py`'s idempotent
`install_claude_hook()` (matcher-merge + duplicate-guard). Reusing it must **not** be done by
importing from `adapters/zed/` — that would make CC-only installs depend on the Zed adapter, the
exact coupling we're avoiding. Instead, lift `install_claude_hook()` into a **neutral shared module**
(e.g. `scripts/hook_install.py`) that *both* installers import independently.

| Option | Verdict |
|---|---|
| **Separate installers, neutral shared helper** (chosen) | ✅ CC-only and Zed-only installs are each self-contained. Shared matcher-merge logic lives in a neutral module both import — no adapter→adapter dependency. |
| **CC installer imports the Zed helper** | ❌ Makes a CC-only user depend on Zed adapter code. Rejected. |
| **Fold reindex into the Zed adapter** (`reset_zed_turn.py`) | ❌ Couples a tmb concern to Zed and only fires inside Zed. Rejected. |

The Zed adapter and this reindexer are independent hook sets that happen to share the
`UserPromptSubmit` boundary; they must not assume each other's presence or installer.

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
- **Installers → separate, no coupling.** CC reindex hooks register via
  `scripts/install_claude_code.py`; Zed diff hooks via `adapters/zed/install.py`. A CC-only user
  never pulls in Zed code, and vice-versa. Hook *scripts* live with the tmb skill (§5).

**Open:**

> **Stale as of 2026-07-03: both items below landed** — `scripts/hook_install.py`
> exists and both installers import it; `reindex --collection` shipped with the hooks.

- **Neutral shared hook-install helper:** the CC installer has no `settings.json` hook-registration
  code today; the only copy is in `adapters/zed/install.py`. Lift `install_claude_hook()` into a
  **neutral** module (e.g. `scripts/hook_install.py`) that both installers import — **not** an import
  from `adapters/zed/` (that would recouple CC installs to the Zed adapter). This is the main build
  prerequisite.
- **Add `memory_bank.py reindex --collection <name>`:** today `reindex` scopes `embed` only by
  resolving the current git repo → collection (via `--memory-root` + cwd), which is wrong for this
  hook — at `SessionStart`/`SessionEnd`/`UserPromptSubmit` the cwd may not be (or map to) the dirty
  collection, and KB collections have no git repo at all. Add a `--collection <name>` argument that
  scopes `qmd embed -c <name>` directly, bypassing cwd resolution; the hook reads the collection name
  straight from the dirty marker and passes it. Keep the existing repo-resolution path as the
  fallback when `--collection` is omitted.

## 8. Non-goals (inherited from the watcher note)

- Do not parse markdown, cache contents, or maintain checksums.
- Do not reimplement qmd indexing outside qmd.
- Do not require the hooks for correctness — explicit `memory_bank.py reindex` must still work.
