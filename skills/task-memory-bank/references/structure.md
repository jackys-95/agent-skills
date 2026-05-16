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

`.memory-bank/collections.yaml` records intended qmd collections. It is not a replacement for `qmd collection add`; it is source-of-truth config for setup, doctor checks, and future watcher/reindexer workflows.

Each project collection must record the git repo it belongs to so agents can resolve the current repository to the right memory context:

```yaml
collections:
  task-memory-bank:
    path: ~/github/task-memory-bank
    mode: recursive
    kind: global

  mb-candidate-profile-hub:
    path: ~/github/task-memory-bank/projects/candidate_profile_hub
    mode: recursive
    kind: project
    project: candidate_profile_hub
    repo: ~/github/candidate-profile-hub
    context: candidate_profile_hub
```

Agents should prefer this mapping over inferring from folder names.

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
    epics/
    stories/
    tasks/
    spikes/
```

`README.md` is the stable entrypoint: project name, repo path, purpose, qmd collection, and where to go next.

`active.md` is the short current-state file an agent can always load before resuming. Keep it under roughly 150 lines.

`overviews/product.md` routes to product surfaces, user workflows, and feature docs.

`overviews/architecture.md` routes to domain architecture docs and cross-domain flows.

`overviews/delivery.md` routes to milestones, release plans, active epics, testing strategy, and deployment notes.

`overviews/decisions.md` routes to decision logs. Prefer linking to domain/work-item decisions instead of duplicating them.

`domains/<domain>/README.md` is the entrypoint for a stable product/system slice. Add architecture, decisions, specs, and examples inside a domain only when needed.

## Work Item

Minimal task:

```text
work/tasks/TASK-0001-fix-empty-avatar/
  README.md
  active.md
  history/
```

Larger epic:

```text
work/epics/EPIC-0003-candidate-import/
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

YYYY-MM-DD by agent/user
```

## Naming

Project folder names should be stable slugs, usually matching the repo name with hyphens converted consistently. If the user already has a name like `candidate_profile_hub`, preserve it.

Work item directories should be:

```text
PREFIX-0001-short-slug
```

Use prefixes:

- `EPIC`
- `STORY`
- `TASK`
- `SPIKE`
