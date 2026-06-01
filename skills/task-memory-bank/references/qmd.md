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

## Integration

When passing search context to qmd (via skill or MCP tool), supply these workflow-owned inputs:

- `collection`: resolved from `.memory-bank/collections.yaml`
- `read_first`: entrypoint files to read before broad search
- `lex`: work ids, filenames, exact domain terms, branch names, and error strings
- `vec`: natural-language resume questions and conceptual context needs
- `known paths`: active files, overview files, specs, designs, or decisions already referenced by entrypoints

For retrieval mechanics — query modes, CLI syntax, MCP call shape — defer to the bundled `qmd` skill:

```bash
qmd skills get qmd
```

## Reindex

After structured writes, route through the `memory_bank.py` script — do not call `qmd embed` directly:

```bash
python3 <skill-dir>/scripts/memory_bank.py reindex
```

When run from inside a git repo with `--memory-root`, the script resolves the project collection from `collections.yaml` and calls:

```bash
qmd embed -c <resolved-collection>
```

This scopes embedding to the current project and avoids rebuilding unrelated collections. Without `--memory-root`, it falls back to global `qmd embed`. If reindex fails, keep the markdown writes and report the failure.

## Diagnostics

If search results seem stale or embeddings appear out of sync, run:

```bash
qmd doctor
```

This checks SQLite versions, embedding fingerprint freshness, and mixed-fingerprint detection. Use it as the first step before manually reindexing.

## qmd Skills

qmd bundles versioned skill instructions for retrieval mechanics. List or fetch them with:

```bash
qmd skills list
qmd skills get qmd
qmd skills path qmd
```

Install stable discovery stubs to prevent skill staleness after upgrades:

```bash
qmd skill install qmd
```

The bundled `qmd` skill covers query modes, CLI syntax, and MCP call shape — not duplicated here.

## Retrieval Discipline

**Never use filesystem tools to explore or search the memory bank.** The qmd interface is canonical: it scopes by collection, leverages embeddings, and avoids loading whole directory trees.

### Path Format for `get`

Search results return paths **relative to their collection**. The `get` tool and CLI require the **collection-prefixed path**:

```text
<collection>/<path-from-search-result>
```

Example — if a search result shows:

```text
path: projects/agent-skills/work/tasks/TASK-0042/README.md
collection: mb-agent-skills
```

Call `get` with:

```text
mb-agent-skills/projects/agent-skills/work/tasks/TASK-0042/README.md
```

**Bare paths silently return "Document not found" with no hint about the missing prefix.** Always prepend the collection name, or use the `docid` (`#abc123`) from search results — docids don't need a prefix.

Snippet line numbers in qmd results are absolute (source-file positions). Pass them directly to `qmd get` with the `:from:count` suffix:

```bash
qmd get "mb-example-project/projects/example_project/work/tasks/TASK-0042/README.md:120:40"
```
