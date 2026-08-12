# qmd Reference

Domain inputs that task-memory-bank passes to qmd. For retrieval mechanics, query syntax, and MCP call shape, invoke the qmd skill (`/qmd` or `qmd skill show`).

## Collection Naming

Collections follow the `mb-<project>` convention. Gather candidate projects for the current repo before searching:

```bash
python3 <skill-dir>/scripts/memory_bank.py suggest-projects --root ~/memory/task-memory-bank --repo "$(git rev-parse --show-toplevel)" --json
```

The response includes ranked `candidates`, each with `collection` (use for qmd searches), `memory_path`, and `read_first` (entrypoint files to read before broad search). Pick the selected candidate's `collection`.

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

**Reindex only settled state** — never index a write that is still provisional (e.g. still
revertible in an editor's diff-review window). Your harness may automate reindexing at safe
boundaries (see its adapter docs); in that case do not reindex yourself.

Otherwise, route through `memory_bank.py` at the **end** of the work, never between writes — do not
call `qmd embed` directly:

```bash
python3 <skill-dir>/scripts/memory_bank.py reindex --collection <name>
```

`--collection <name>` scopes `qmd embed -c <name>` directly and may be repeated;
all requested embeds share one initial `qmd update`. Omitting it falls back to
resolving the collection from the current git repo; with neither, all
collections rebuild globally. `qmd update` always runs first (it has no
per-collection flag, but it is a cheap change-scan). If reindex fails, keep the
markdown writes and report the failure.
