# Structure Reference

Use this reference when creating or revising task memory bank folders and templates.

## Root

```text
task-memory-bank/
  registry.md
  .memory-bank/
    collections.yaml
  projects/
```

`registry.md` is a compact cross-project index. Keep it human-readable and link to project entrypoints.

`.memory-bank/collections.yaml` at the memory-bank root records intended qmd collections across projects. It is not a replacement for `qmd collection add`; it is source-of-truth config for setup, repo-to-project resolution, doctor checks, and future watcher/reindexer workflows.

Each project collection must record the git repo it belongs to so agents can resolve the current repository to the right memory context:

```yaml
collections:
  task-memory-bank:
    path: ~/memory/task-memory-bank
    mode: recursive
    kind: global

  mb-example-project:
    path: ~/memory/task-memory-bank/projects/example_project
    mode: recursive
    kind: project
    project: example_project
    repo: ~/work/example-project
    context: example_project
```

Agents should prefer this mapping over inferring from folder names.

The root `collections.yaml` is the single source of truth for collection metadata. There is no per-project `.memory-bank/collection.yaml` manifest: a detached copy would carry a stale association snapshot, and config is centralized (design Decision 6).

## Project

```text
projects/<project>/
  README.md
  active.md
  overviews/
    product.md
    architecture.md
    delivery.md
    decisions.md
  domains/
  work/
    index.md
    epics/
    stories/
    tasks/
    spikes/
```

`README.md` is the stable entrypoint: project name, repo path, purpose, qmd collection, and where to go next.

`active.md` is the short current-state file an agent can always load before resuming. Keep it under roughly 150 lines. It must not contain session summaries, outcomes, or historical detail — those go in history files first.

`overviews/product.md` routes to product surfaces, user workflows, and feature docs.

`overviews/architecture.md` routes to domain architecture docs and cross-domain flows.

`overviews/delivery.md` routes to milestones, release plans, active epics, testing strategy, and deployment notes.

`work/index.md` is a table of every work item (ID, type, status, title, date), ordered by resume priority — the most-resumable work (in-progress, then paused, then blocked, then open, then closed) first. It is the first place an agent should look when asking "what work exists?" — one `get` is faster than a broad keyword search across session history. `new-work` appends a row on creation; `memory_bank.py regen-index --project <p>` rebuilds the whole table from each work item's `## Status`, re-sorted, and is the way to refresh it after hand-editing a status. (The table is generated, so a hand edit to a row is fine but will be normalized on the next regen.)

A work item's **status** is a closed, ordinal vocabulary — `open`, `in-progress`, `blocked`, `paused`, `done`, `shipped`, `cancelled`, `superseded` — defined once in `selection.py` (`WORK_STATUSES`, imported by `memory_bank.py`) and validated on write by `new-work`. It is distinct from **phase** (below): status is lifecycle position and the signal the resume ranker sorts on; phase is where inside a single active item's workflow the work sits. `paused` is a status, never a phase. The four terminal statuses (`done`/`shipped`/`cancelled`/`superseded`) mean the item is closed.

`overviews/decisions.md` routes to decision logs. Prefer linking to domain/work-item decisions instead of duplicating them.

`domains/<domain>/README.md` is the entrypoint for a stable product/system slice. Add architecture, decisions, specs, and examples inside a domain only when needed.

## Work Item

Minimal task:

```text
work/tasks/TASK-0001-fix-saved-filter-state/
  README.md
  active.md
  history/
```

Larger epic:

```text
work/epics/EPIC-0003-account-settings/
  README.md
  active.md
  overviews/
    design.md
    specification.md
  designs/
  specs/
  decisions.md
  tasks/
  history/
  attempts/
```

Use `designs/` for exploratory reasoning and options.

Use `specs/` for agreed behavior, contracts, acceptance criteria, and implementation boundaries.

Use `decisions.md` when choices accumulate and need durable rationale.

Use `attempts/` only for meaningfully divergent implementation or planning approaches.

## Active Context Template

```md
# Active Context

## Objective

One paragraph.

## Current Phase

planned | design | specification | implementation | verification | handoff

## Current Attempt

main

## Repo State

- Repo:
- Branch:
- Worktree:
- Relevant files:

## Known Facts

- ...

## Decisions In Force

- ...

## Open Questions

- ...

## Next Actions

1. ...

## Resume Query

Suggested qmd query.

## Last Updated

[YYYY-MM-DD-session-NNN](history/YYYY-MM-DD-session-NNN.md)
```

## Session History File Template

```md
# Session YYYY-MM-DD-NNN

## What Happened

Narrative recap of the session: what was attempted, what was completed, decisions made, outcomes.

## Previous

[YYYY-MM-DD-session-NNN](YYYY-MM-DD-session-NNN.md)
```

`active.md` links only to the latest session file. Each session file links to its predecessor. This reverse linked-list lets agents reconstruct history without loading the full chain upfront.

## Naming

Project folder names should be stable slugs, usually matching the repo name with hyphens converted consistently. If the user already has a name like `example_project`, preserve it.

Work item directories should be:

```text
PREFIX-0001-short-slug
```

Use prefixes:

- `EPIC`
- `STORY`
- `TASK`
- `SPIKE`
