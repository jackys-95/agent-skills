# qmd Reference

Domain inputs that task-memory-bank passes to qmd. For retrieval mechanics, query syntax, and MCP call shape, invoke the qmd skill (`/qmd` or `qmd skill show`).

## Collection Naming

Collections follow the `mb-<project>` convention. Resolve the current repo to its collection before searching:

```bash
python3 <skill-dir>/scripts/memory_bank.py resolve-project --root ~/memory/task-memory-bank --repo "$(git rev-parse --show-toplevel)" --json
```

The response includes `collection` (use for qmd searches), `memory_path`, and `read_first` (entrypoint files to read before broad search).

## Path Format for `get`

Search results return paths relative to their collection. The `get` tool and CLI require the collection-prefixed path:

```text
<collection>/<path-from-search-result>
```

Example — if a search result shows `path: projects/agent-skills/work/tasks/TASK-0042/README.md` in collection `mb-agent-skills`, call `get` with:

```text
mb-agent-skills/projects/agent-skills/work/tasks/TASK-0042/README.md
```

Bare paths silently return "Document not found" with no hint about the missing prefix. Alternatively, use the `docid` (`#abc123`) from search results — docids work without a prefix.

## Resume Query Shape

When resuming work, pass this structured block to qmd:

```text
collection: mb-<project>
intent: <one-sentence description of what you're resuming>
lex: <work item IDs, filenames, branch names, exact domain terms>
vec: <natural-language resume question or conceptual context need>
known paths: <active.md path and any other files already in context>
```

Example:

```text
collection: mb-agent-skills
intent: resume the saved filter state task
lex: TASK-0042 saved filter state
vec: what context is needed to resume the saved filter state task
known paths: projects/agent-skills/work/tasks/TASK-0042-fix-saved-filter-state/active.md
```

## Reindex

After structured writes, route through `memory_bank.py` — do not call `qmd embed` directly:

```bash
python3 <skill-dir>/scripts/memory_bank.py reindex
```

This resolves the project collection from `collections.yaml` and scopes embedding to the current project, avoiding a full rebuild. If reindex fails, keep the markdown writes and report the failure.
