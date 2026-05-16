# Workflow Reference

Use this reference for memory-bank operations beyond initial scaffolding.

## Resume

1. Resolve the current git repo to a memory project using `.memory-bank/collections.yaml` or `memory_bank.py resolve-project`.
2. Read project `README.md`.
3. Read project `active.md`.
4. If a work item is specified, read its `README.md` and `active.md`.
5. Use qmd to retrieve supporting context only when needed.
6. State the current objective, next action, and any missing context before changing files.

Good resume query:

```bash
qmd query -c mb-<project> $'lex: <id> <key terms>\nvec: what context is needed to resume <work item>'
```

## New Work

Create the smallest useful work item.

Always create:

```text
README.md
active.md
history/
```

Do not create `designs/`, `specs/`, `decisions.md`, or `attempts/` unless the work already needs them.

## Update

At the end of a meaningful session:

1. Append a dated `history/YYYY-MM-DD-session-NNN.md`.
2. Rewrite `active.md` to reflect the current resumable state.
3. Update checklist/progress in the work item `README.md` if needed.
4. Link any new design/spec/decision docs.
5. Run `qmd update` and `qmd embed` if the watcher is not known to be active.

History should be append-only. Active context should be compact and replaceable.

## Branch

Use attempts for divergent plans:

```text
attempts/
  main/
    notes.md
  server-side-normalization/
    notes.md
```

When an attempt is superseded, mark it:

```md
## Status

superseded

## Reason

Why this approach was abandoned.

## Superseded By

../new-attempt/
```

Update `active.md` with the new current attempt.

## Handoff

A handoff should fit in one screen when possible:

- Objective
- Current state
- Decisions in force
- Files touched or relevant
- Tests/verification status
- Open questions
- Next action

Write handoff details into history, then compact `active.md` to the same shape.

## Archive

When work is done:

1. Set status to `done`, `shipped`, `cancelled`, or `superseded`.
2. Move remaining useful context out of `active.md` into README/history/decisions.
3. Leave `active.md` as a short terminal state summary.
4. Reindex qmd.
