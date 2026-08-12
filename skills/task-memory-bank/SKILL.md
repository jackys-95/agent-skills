---
name: task-memory-bank
description: Build, maintain, and resume qmd-backed task memory banks for software projects. Use when creating project memory structure, starting epics/stories/tasks/spikes, resuming active work, writing handoffs, or updating active context/history across agents.
compatibility: Requires the qmd CLI (`@tobilu/qmd`) with the memory-bank collections indexed; qmd MCP tools recommended for retrieval.
---

# Task Memory Bank

Use a qmd-backed markdown memory bank to keep project and work-item context slim, searchable, and resumable across agents.

## Core Rules

- Keep the memory bank outside app repos unless the user asks otherwise.
- Separate projects by folder and qmd collection/context.
- Load only entrypoint files first: project `README.md`, project `active.md`, work item `README.md`, and work item `active.md`. The bank-root `.memory-bank/collections.yaml` is the source-of-truth config (there is no per-project manifest).
- **Never use filesystem tools to explore or search the memory bank.** Use qmd MCP tools (`query`, `get`, `multi_get`) or the qmd CLI. Filesystem tools miss embeddings, bypass collection scoping, and encourage loading entire trees.
- Use qmd search for supporting context instead of reading whole trees.
- Treat `active.md` as current resumable state, not historical record. It must not contain session summaries, outcomes, or historical detail.
- **Write history first, then update active.md.** Session detail goes in `history/YYYY-MM-DD-session-NNN.md` before `active.md` is rewritten. `active.md` links only to the latest session file; each session file links to its predecessor (reverse linked-list).
- Create designs, specs, decisions, and attempts only when the work warrants them.
- **Soft-wrap prose — one line per paragraph, never hard-wrap mid-sentence.** Hard wraps render as stray newlines and break phrase/link greps.
- **Work in phase checkpoints.** Plan before editing — and persist the plan into the work item,
  so implementation can resume cold in another session or model — and close out memory separately
  from implementation. See the Phase Checkpoints workflow in
  [references/workflows.md](references/workflows.md). Harness adapters may bind checkpoints to
  turn boundaries.
- **Reindex only settled state.** The index must never capture a write that is still
  provisional — e.g. still revertible in an editor's diff-review window. If the environment lets
  the user revert writes after the fact, defer reindexing past that window. Harness automation may
  handle reindexing for you (see your harness's adapter docs); otherwise reindex at the end of the
  work, never between writes.

## Start Here

For deterministic scaffolding, use:

```bash
python3 <skill-dir>/scripts/memory_bank.py init-project --root ~/memory/task-memory-bank --project example_project --repo ~/work/example-project
python3 <skill-dir>/scripts/memory_bank.py new-work --root ~/memory/task-memory-bank --project example_project --type task --title "Fix saved filter state"
python3 <skill-dir>/scripts/memory_bank.py suggest-projects --root ~/memory/task-memory-bank --repo "$(git rev-parse --show-toplevel)" --json
```

`<skill-dir>` is this skill's own directory — resolve the script path relative to it.

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

Before searching qmd from a repo, gather candidate projects for the repo:

```bash
python3 <skill-dir>/scripts/memory_bank.py suggest-projects --root ~/memory/task-memory-bank --repo "$(git rev-parse --show-toplevel)" --json
```

This returns ranked `candidates` (across every bank qmd knows about), each with `collection`, `memory_path`, and `read_first`. Selection is a declaration: take the top candidate when unambiguous, otherwise choose from the shortlist. Do not guess collection names when `.memory-bank/collections.yaml` is available.

**`get` path format:** Search results return paths relative to their collection. Prepend the collection name before calling `get`: `mb-<project>/path/from/search`. Bare paths return "Document not found" with no hint about the missing prefix. Alternatively, use the `docid` (`#abc123`) from search results — docids work without a prefix.

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

**Read/write asymmetry:** reads go to qmd directly (MCP tools or CLI — idempotent, safe anytime);
writes, structure changes, and indexing go through `memory_bank.py` only.

Reindexing after memory-bank writes may be automated by your harness (see its adapter docs) — in
that case you do **not** run it yourself. Otherwise, run this at the **end** of the work, never
between writes (see the settled-state rule in Core Rules):

```bash
python3 <skill-dir>/scripts/memory_bank.py reindex --collection <name>
```

`--collection <name>` scopes the embed to one collection and may be repeated;
omit it to fall back to git-repo resolution, or run with neither to rebuild all collections. If qmd is unavailable or
unhealthy, still update markdown files and tell the user reindexing could not be completed.

See [references/qmd.md](references/qmd.md) for collection naming, repo resolution, and reindex routing.

The qmd skill must be installed separately (`qmd skill install --global --yes` or via `scripts/install_claude_code.py`). For retrieval mechanics — query modes, CLI syntax, MCP call shape — invoke `/qmd` or run `qmd skill show`.
