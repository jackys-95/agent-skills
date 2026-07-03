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

## Phase Checkpoints

Work on a memory-banked item proceeds in phases. Each boundary is a **checkpoint**: a point where the work so far is coherent, reviewable, and safe to pause.

1. **Resume/plan** — load entrypoint context, state the objective, the planned changes, and any
   missing context. **Write the plan into the work item**: planned changes and next actions go in
   its `active.md` (set phase to `planned`); a substantial plan gets a `designs/` doc that
   `active.md` links to. **No repo/product file edits in this phase.** The plan must survive
   outside the conversation — so the user can pause after planning, resume in a fresh session, or
   hand implementation to a different (cheaper) model that reads the plan cold from the bank.
2. **Implement** — the code/content changes, and nothing else.
3. **Verify** — run tests or otherwise exercise the change; report results faithfully.
4. **Memory close-out** — the Update workflow (history → active.md → index/README), as its own phase, never mixed into implementation.

At each boundary, stop at the checkpoint before continuing. If your harness adapter defines a checkpoint mechanism (e.g., ending your turn — see the adapter docs), use it; otherwise treat the boundary as the moment to summarize state to the user.

**Collapsing phases:** for a small, low-risk change (roughly: ≤2 files, no design decisions taken), implement and verify may share a checkpoint. Two boundaries are never collapsed: the plan checkpoint before the first file edit, and the boundary before memory close-out.

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

After scaffolding, add a row to `work/index.md` with the ID, type, status (`open`), title, and creation date. If `work/index.md` does not exist yet, create it with a header row before adding the entry.

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
- [ ] `work/index.md` updated if a work item was created or its status changed
- [ ] `reindex` run

## When to Reindex

Reindex only in two situations:

1. **Parallelizing** — another agent or session needs to see your recent memory-bank writes before you're done.
2. **Substantial progress checkpoint** — you've completed a meaningful chunk of work and want a stable, searchable snapshot.

The end-of-session reindex in the Update checklist covers case 2 for the normal case. Do not reindex after every individual file write mid-session.

**Revert does not require reindex.** Running `revert_zed_snapshot.py` undoes a file-system change but the reverted content was never indexed — the index was correct before the write and is correct again after the revert. Only reindex after a revert if the reverted file was a memory-bank write that already crossed a checkpoint boundary (i.e., you had already reindexed it in this session).

## History Scope

Every work item has a `history/` directory. Use it. Project-level history is for cross-cutting events only.

**Write inside the work item** when the session touched primarily one item:

```text
work/tasks/TASK-0042-fix-foo/history/YYYY-MM-DD-session-NNN.md
```

Include: what happened, decisions made, what was tried, blockers, outcomes. This is the canonical record for resuming that item cold.

**Write a project-level session file** (`projects/<project>/history/YYYY-MM-DD-session-NNN.md`) only for:

- Sessions that open or close multiple work items with no single natural home
- Planning or discovery work that predates any work item
- Architecture or cross-cutting decisions that don't belong to one item

**Sessions that touch multiple items**: write a task-level entry per item touched; add a one-liner link-out in a project-level file if the cross-item context is worth preserving.

```text
# Session 2026-05-31-009

- TASK-0020: done — see [TASK-0020/history/2026-05-31-session-009.md](../work/tasks/TASK-0020-.../history/2026-05-31-session-009.md)
- TASK-0022: done — see [TASK-0022/history/...]
```

**Rule of thumb**: if someone resuming TASK-0042 cold would want the detail, it belongs in TASK-0042's history, not the project session file. Project session files should be navigational, not authoritative.

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
4. Update the status field in `work/index.md` for this item.
5. Run `python3 <skill-dir>/scripts/memory_bank.py reindex`.
