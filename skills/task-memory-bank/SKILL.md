---
name: task-memory-bank
description: Build, maintain, and resume qmd-backed task memory banks for software projects. Use when creating project memory structure, starting epics/stories/tasks/spikes, resuming active work, writing handoffs, or updating active context/history across agents.
---

# Task Memory Bank

Use a qmd-backed markdown memory bank to keep project and work-item context slim, searchable, and resumable across agents.

## Core Rules

- Keep the memory bank outside app repos unless the user asks otherwise.
- Separate projects by folder and qmd collection/context.
- Load only entrypoint files first: project `.memory-bank/collection.yaml`, project `README.md`, project `active.md`, work item `README.md`, and work item `active.md`.
- **Never use filesystem tools to explore or search the memory bank.** Use qmd MCP tools (`query`, `get`, `multi_get`) or the qmd CLI. Filesystem tools miss embeddings, bypass collection scoping, and encourage loading entire trees.
- Use qmd search for supporting context instead of reading whole trees.
- Treat `active.md` as current resumable state, not historical record. It must not contain session summaries, outcomes, or historical detail.
- **Write history first, then update active.md.** Session detail goes in `history/YYYY-MM-DD-session-NNN.md` before `active.md` is rewritten. `active.md` links only to the latest session file; each session file links to its predecessor (reverse linked-list).
- Create designs, specs, decisions, and attempts only when the work warrants them.
- Reindex qmd after structured writes when the watcher is not known to be running.

## Start Here

For deterministic scaffolding, use:

```bash
python3 ${CODEX_SKILL_DIR}/scripts/memory_bank.py init-project --root ~/memory/task-memory-bank --project example_project --repo ~/work/example-project
python3 ${CODEX_SKILL_DIR}/scripts/memory_bank.py new-work --root ~/memory/task-memory-bank --project example_project --type task --title "Fix saved filter state"
python3 ${CODEX_SKILL_DIR}/scripts/memory_bank.py resolve-project --root ~/memory/task-memory-bank --repo "$(git rev-parse --show-toplevel)" --json
```

If `${CODEX_SKILL_DIR}` is unavailable in the current agent, resolve the script relative to this skill directory.

For first-time setup examples and direct CLI usage, see [references/quickstart.md](references/quickstart.md).

## Structure

Use this project shape:

```text
task-memory-bank/
  registry.md
  .memory-bank/
    collections.yaml
  projects/
    <project>/
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

Use `domains/` for stable product/system slices such as auth, billing, search, deployment, data-sync, or observability.

Use `overviews/` for short routing docs. They summarize the system shape and link to deeper docs; they are not giant canonical specs.

See [references/structure.md](references/structure.md) for file purposes and templates.

## Work Items

Every active work item should have:

```text
README.md
active.md
history/
```

Add these only when needed:

```text
designs/
specs/
decisions.md
attempts/
```

Use work item types by intent:

- `epic`: larger body of work with multiple stories/tasks.
- `story`: user-visible behavior or coherent delivery slice.
- `task`: concrete implementation/fix/refactor step.
- `spike`: investigation or uncertainty reduction.

See [references/workflows.md](references/workflows.md) for resume, update, handoff, and branching workflows.

## qmd Usage

Before searching qmd from a repo, resolve the repo to its memory project:

```bash
python3 ${CODEX_SKILL_DIR}/scripts/memory_bank.py resolve-project --root ~/memory/task-memory-bank --repo "$(git rev-parse --show-toplevel)" --json
```

Use the returned `collection`, `memory_path`, and `read_first` files. Do not guess collection names when `.memory-bank/collections.yaml` is available.

This skill owns the memory-bank workflow: project resolution, entrypoint files, active context, history, and handoff shape. For qmd retrieval mechanics, use the dedicated qmd skill or qmd MCP tools when available. Let that integration choose MCP or CLI; pass it the resolved collection, known paths, and search intent.

When resuming work, ask qmd for targeted supporting context:

```text
collection: mb-example-project
intent: resume the saved filter state task
lex: TASK-0042 saved filter state
vec: what context is needed to resume the saved filter state task
hyde: The active.md for TASK-0042 describes the current state, next actions, and any open questions needed to continue.
known paths: projects/example_project/work/tasks/TASK-0042-fix-saved-filter-state/active.md
```

After memory-bank writes, reindex through the qmd skill if available, or run:

```bash
python3 ${CODEX_SKILL_DIR}/scripts/memory_bank.py reindex
```

If qmd is unavailable or unhealthy, still update markdown files and tell the user reindexing could not be completed.

See [references/qmd.md](references/qmd.md) for collection naming, integration modes, and search habits.
