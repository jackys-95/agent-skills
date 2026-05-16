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
mb-candidate-profile-hub
mb-inference-poc
```

Preserve a human/project context name separately when useful:

```text
candidate_profile_hub
inference-poc
```

## Repo Resolution

When an agent starts inside a git repo, resolve the repo to the qmd collection before searching:

```bash
repo="$(git rev-parse --show-toplevel)"
python3 <skill-dir>/scripts/memory_bank.py resolve-project --root ~/github/task-memory-bank --repo "$repo" --json
```

The command returns:

```json
{
  "project": "candidate_profile_hub",
  "collection": "mb-candidate-profile-hub",
  "memory_path": "/Users/jacky/github/task-memory-bank/projects/candidate_profile_hub",
  "repo": "/Users/jacky/github/candidate-profile-hub",
  "context": "candidate_profile_hub",
  "read_first": [
    "/Users/jacky/github/task-memory-bank/projects/candidate_profile_hub/README.md",
    "/Users/jacky/github/task-memory-bank/projects/candidate_profile_hub/active.md"
  ]
}
```

Use `collection` for qmd searches. Read `read_first` before loading other memory files.

## Setup Commands

```bash
qmd collection add ~/github/task-memory-bank --name task-memory-bank
qmd collection add ~/github/task-memory-bank/projects/candidate_profile_hub --name mb-candidate-profile-hub
qmd embed
```

If using qmd contexts:

```bash
qmd context add candidate_profile_hub ~/github/task-memory-bank/projects/candidate_profile_hub/README.md
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
    { "type": "lex", "query": "TASK-0042 empty avatar" },
    { "type": "vec", "query": "what context is needed to resume the empty avatar task" }
  ],
  "collections": ["mb-candidate-profile-hub"],
  "limit": 10
}
```

Use CLI as the portable fallback. Prefer structured or JSON-friendly commands when scripting:

```bash
qmd query -c mb-candidate-profile-hub --json $'lex: TASK-0042 empty avatar\nvec: what context is needed to resume the empty avatar task'
qmd get projects/candidate_profile_hub/work/tasks/TASK-0042-fix-empty-avatar/active.md
qmd multi-get "projects/candidate_profile_hub/overviews/*.md" -l 80
```

Reserve the qmd SDK for a future memory-bank service, watcher, or richer doctor command. Do not require it for normal skill workflows.

## Search Pattern

Use lexical search for ids, filenames, and exact terms. Use vector search for conceptual recall. Use both when resuming work. Put the strongest exact query first so qmd fusion weights it highly.

## Retrieval Discipline

- Prefer `qmd get` for known files.
- Prefer `qmd multi-get` for a small set of entrypoints.
- Prefer `qmd query` for discovery.
- Keep `-l` line limits low when scanning.
- Load specs/designs only after active context points to them or qmd finds them.

## Reindex

After structured writes:

```bash
qmd update
qmd embed
```

If that fails, keep the markdown writes and report the qmd failure.
