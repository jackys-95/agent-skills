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

Each project collection should also include a local manifest at `projects/<project>/.memory-bank/collection.yaml`:

```yaml
collection:
  name: mb-example-project
  kind: project
  project: example_project
  repo: ~/work/example-project
  context: example_project
  path: .
  mode: recursive
```

The root registry enables global lookup across projects. The project-local manifest keeps collection metadata inside the collection itself so it can travel with, and be indexed alongside, the project memory.

## Project

```text
projects/<project>/
  .memory-bank/
    collection.yaml
  README.md
  active.md
  overviews/
    product.md
    architecture.md
    delivery.md
    decisions.md
  domains/
  work/
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

design | specification | implementation | verification | handoff | paused

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
