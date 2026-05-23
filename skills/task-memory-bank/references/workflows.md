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

```text
collection: mb-<project>
intent: resume <work item title>
lex: <id> <key terms>
vec: what context is needed to resume <work item>
hyde: The active.md for <work item> describes the current state, next actions, and any open questions needed to continue.
```

## New Work

Create the smallest useful work item.

**Before assigning an ID, check existing IDs.** Run `memory_bank.py new-work` — it reads existing directories and picks the next safe ID automatically. If scaffolding manually, list the relevant work type directory (`work/tasks/`, `work/stories/`, etc.) and use the highest existing number + 1. Never guess or reuse an ID; collisions silently corrupt history.

Always create:

```text
README.md
active.md
history/
```

Do not create `designs/`, `specs/`, `decisions.md`, or `attempts/` unless the work already needs them.

## Update

At the end of a meaningful session, **write history first, then update active.md**:

1. Write `history/YYYY-MM-DD-session-NNN.md` **inside the work item directory** (e.g., `work/tasks/TASK-0042-fix-foo/history/`). Include what happened, decisions made, and outcomes. Close with a `## Previous` link to the prior session file (or omit if this is the first session). Do not put this detail anywhere else.
2. Rewrite the work item's `active.md` to reflect only the current resumable state — phase, focus, next actions, environment, and resume query. Do not copy session detail from step 1 into `active.md`.
3. Set `## Last Updated` in `active.md` to a markdown link to the new session file: `[YYYY-MM-DD-session-NNN](history/YYYY-MM-DD-session-NNN.md)`. This is the only session reference `active.md` needs.
4. Update checklist/progress in the work item `README.md` if needed.
5. Link any new design/spec/decision docs.
6. Run `python3 <skill-dir>/scripts/memory_bank.py reindex`. Treat this as mandatory — run it at every session end, not conditional on watcher state.

History is a reverse linked-list: `active.md` → latest session → previous session → ... Reading `active.md` plus one session file gives full context for the current state without loading the whole chain.

History should be append-only. Active context should be compact and replaceable.

**End-of-session checklist:**
- [ ] `history/YYYY-MM-DD-session-NNN.md` written
- [ ] `active.md` rewritten to current resumable state only
- [ ] `## Last Updated` in `active.md` links to the new session file
- [ ] Work item `README.md` updated if status or progress changed
- [ ] `reindex` run

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
4. Run `python3 <skill-dir>/scripts/memory_bank.py reindex`.
