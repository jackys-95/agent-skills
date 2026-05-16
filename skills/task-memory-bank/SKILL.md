---
name: task-memory-bank
description: Build, maintain, and resume qmd-backed task memory banks for software projects. Use when creating project memory structure, starting epics/stories/tasks/spikes, resuming active work, writing handoffs, updating active context/history, or designing portable slash-command workflows across Claude, Codex, Gemini, Zed, Cline, and similar coding agents.
---

# Task Memory Bank

Use a qmd-backed markdown memory bank to keep project and work-item context slim, searchable, and resumable across agents.

## Core Rules

- Keep the memory bank outside app repos unless the user asks otherwise.
- Separate projects by folder and qmd collection/context.
- Load only entrypoint files first: project `README.md`, project `active.md`, work item `README.md`, and work item `active.md`.
- Use qmd search for supporting context instead of reading whole trees.
- Treat `active.md` as current resumable state, not historical record.
- Append session history instead of bloating active context.
- Create designs, specs, decisions, and attempts only when the work warrants them.
- Reindex qmd after structured writes when the watcher is not known to be running.

## Start Here

For deterministic scaffolding, use:

```bash
python3 ${CODEX_SKILL_DIR}/scripts/memory_bank.py init-project --root ~/github/task-memory-bank --project candidate_profile_hub --repo ~/github/candidate-profile-hub
python3 ${CODEX_SKILL_DIR}/scripts/memory_bank.py new-work --root ~/github/task-memory-bank --project candidate_profile_hub --type task --title "Fix empty avatar"
python3 ${CODEX_SKILL_DIR}/scripts/memory_bank.py resolve-project --root ~/github/task-memory-bank --repo "$(git rev-parse --show-toplevel)" --json
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

Use `domains/` for stable product/system slices such as ingestion, auth, profile-ui, matching, search, deployment, or observability.

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
python3 ${CODEX_SKILL_DIR}/scripts/memory_bank.py resolve-project --root ~/github/task-memory-bank --repo "$(git rev-parse --show-toplevel)" --json
```

Use the returned `collection`, `memory_path`, and `read_first` files. Do not guess collection names when `.memory-bank/collections.yaml` is available.

This skill owns the memory-bank workflow: project resolution, entrypoint files, active context, history, and handoff shape. For qmd retrieval mechanics, use the dedicated qmd skill or qmd MCP tools when available. Let that integration choose MCP or CLI; pass it the resolved collection, known paths, and search intent.

When resuming work, ask qmd for targeted supporting context:

```text
collection: mb-candidate-profile-hub
lex: TASK-0042 empty avatar
vec: what context is needed to resume the empty avatar task
known paths: projects/candidate_profile_hub/work/tasks/TASK-0042-fix-empty-avatar/active.md
```

Fallback CLI pattern when no qmd skill or MCP tools are available:

```bash
qmd query -c mb-candidate-profile-hub $'lex: TASK-0042 empty avatar\nvec: what context is needed to resume the empty avatar task'
qmd get projects/candidate_profile_hub/work/tasks/TASK-0042-fix-empty-avatar/active.md
qmd multi-get "projects/candidate_profile_hub/overviews/*.md" -l 80
```

After memory-bank writes, reindex through the qmd skill if available, or run:

```bash
qmd update
qmd embed
```

If qmd is unavailable or unhealthy, still update markdown files and tell the user reindexing could not be completed.

See [references/qmd.md](references/qmd.md) for collection naming, integration modes, and search habits.

## Slash Command Adapters

Keep workflow definitions portable. The canonical workflow names are:

```text
memory.init-project
memory.new-work
memory.resume
memory.update
memory.branch
memory.handoff
memory.reindex
memory.doctor
```

Expose them through platform adapters:

- Claude: user-invocable skills, often with `disable-model-invocation: true`.
- Gemini CLI: `.gemini/commands/memory/*.toml`.
- Codex: skills and slash/menu exposure where available.
- Zed: external-agent native commands or extension slash commands.
- Cline: slash workflow commands or custom instructions.

See [references/adapters.md](references/adapters.md) for adapter templates.

## Implementation Order

1. Initialize the memory bank and project folders.
2. Add qmd collection/context registration instructions or run them when appropriate.
3. Create work items only when there is actual work to track.
4. Resume by reading active files first, then searching qmd.
5. Update by appending history and rewriting slim active context.
6. Park watcher/reindexer implementation until the basic memory workflows are stable.
