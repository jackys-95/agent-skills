# qmd Reference

Use qmd as the retrieval layer for the memory bank. Avoid loading entire project memory trees.

## Collection Naming

Use:

```text
task-memory-bank
mb-<project>
```

Examples:

```text
task-memory-bank
mb-example-project
mb-another-project
```

Preserve a human/project context name separately when useful:

```text
example_project
another-project
```

## Repo Resolution

When an agent starts inside a git repo, resolve the repo to the qmd collection before searching:

```bash
repo="$(git rev-parse --show-toplevel)"
python3 <skill-dir>/scripts/memory_bank.py resolve-project --root ~/memory/task-memory-bank --repo "$repo" --json
```

The command returns:

```json
{
  "project": "example_project",
  "collection": "mb-example-project",
  "memory_path": "/Users/example/memory/task-memory-bank/projects/example_project",
  "repo": "/Users/example/work/example-project",
  "context": "example_project",
  "read_first": [
    "/Users/example/memory/task-memory-bank/projects/example_project/README.md",
    "/Users/example/memory/task-memory-bank/projects/example_project/active.md"
  ]
}
```

Use `collection` for qmd searches. Read `read_first` before loading other memory files.

The root `.memory-bank/collections.yaml` exists for cross-project lookup. Each project collection also carries `projects/<project>/.memory-bank/collection.yaml`, with `path: .`, so collection metadata lives inside the collection and can be indexed when qmd includes YAML files.

## Setup Commands

```bash
qmd collection add ~/memory/task-memory-bank --name task-memory-bank
qmd collection add ~/memory/task-memory-bank/projects/example_project --name mb-example-project
qmd embed
```

If using qmd contexts:

```bash
qmd context add example_project ~/memory/task-memory-bank/projects/example_project/README.md
```

## Integration Modes

Prefer the dedicated qmd skill or qmd MCP tools when the agent has them. The task-memory-bank skill should supply domain-specific inputs, not duplicate transport details:

- `collection`: resolved from `.memory-bank/collections.yaml`.
- `read_first`: entrypoint files to read before broad search.
- `lex`: work ids, filenames, exact domain terms, branch names, and error strings.
- `vec`: natural-language resume questions and conceptual context needs.
- `known paths`: active files, overview files, specs, designs, or decisions already referenced by entrypoints.

Use qmd MCP for retrieval when available:

```json
{
  "searches": [
    { "type": "lex", "query": "TASK-0042 saved filter state" },
    { "type": "vec", "query": "what context is needed to resume the saved filter state task" },
    { "type": "hyde", "query": "The active.md for the saved filter state task describes current progress, next steps, and any open blockers." }
  ],
  "intent": "Resume the saved filter state task — load current state and next actions.",
  "collections": ["mb-example-project"],
  "limit": 10
}
```

Use CLI as the portable fallback:

```bash
qmd query -c mb-example-project --json $'intent: resume saved filter state task\nlex: TASK-0042 saved filter state\nvec: what context is needed to resume the saved filter state task'
qmd get projects/example_project/work/tasks/TASK-0042-fix-saved-filter-state/active.md
qmd multi-get "projects/example_project/overviews/*.md" -l 80
```

Reserve the qmd SDK for a future memory-bank service, watcher, or richer doctor command. Do not require it for normal skill workflows.

## Search Pattern

Use lexical search for ids, filenames, and exact terms. Use vector search for conceptual recall. Use both when resuming work. Put the strongest exact query first so qmd fusion weights it highly.

## Retrieval Discipline

**Never use filesystem tools to explore or search the memory bank.** The qmd interface is canonical: it scopes by collection, leverages embeddings, and avoids loading whole directory trees. Filesystem tools load raw files without collection context and encourage unbounded tree reads.

- Prefer `qmd get` for known files.
- Prefer `qmd multi-get` for a small set of entrypoints.
- Prefer `qmd query` for discovery.
- Keep `-l` line limits low when scanning.
- Load specs/designs only after active context points to them or qmd finds them.

## Reindex

After structured writes:

```bash
python3 <skill-dir>/scripts/memory_bank.py reindex
```

If that fails, keep the markdown writes and report the qmd failure.
