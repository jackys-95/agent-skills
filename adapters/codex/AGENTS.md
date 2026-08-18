<!-- codex-agent-skills -->
# agent-skills Codex Adapter

These local skills are installed from the `agent-skills` repository. The repository remains the source of truth; installed copies under `~/.agents/skills`
are generated artifacts.

## Invocation

Use explicit skill mentions for deterministic workflows:

- `$task-memory-bank` for the canonical memory-bank workflow.
- `$memory-resume`, `$memory-update`, `$memory-handoff`, `$memory-reindex`, and related generated wrappers for direct workflow entry points.
- `$query-kb` for knowledge-base retrieval.
- `$knowledge-files` for approved knowledge-file authoring and promotion.

If a slash/menu entry is available in the active Codex surface, it is fine to use that entry instead of typing the skill mention.

## Memory Bank Discipline

- Do not create a Codex-specific memory format. Use the canonical task-memory-bank structure and scripts.
- Do not explore or search the memory bank with filesystem tools. Prefer the qmd MCP `query`, `get`, and `multi_get` tools. If MCP is unavailable, use lexical `qmd search` as the degraded read path; do not default to model-backed qmd CLI reads under the macOS command sandbox.
- Keep memory-bank edits separate from implementation edits when the user needs a clean review window.
- Reindex only after memory-bank writes are settled. The adapter's trusted lifecycle hooks normally handle this. If hooks are unavailable, use `$memory-reindex`: run one `qmd update`, then request one-shot approval for each exact `qmd embed -c <collection>` command.

## Codex Surface Notes

These instructions assume Codex can read local skills from `~/.agents/skills`. Avoid depending on product-specific desktop UI behavior in the skill workflow.

- For non-CLI surfaces, confirm the active surface's current local-file, writable-root, and review behavior before relying on external memory-bank writes.
- If a surface cannot review external memory-bank diffs directly, keep those memory edits in a separate phase and report the files changed explicitly.
- Writable roots grant filesystem access, not Metal device access. Do not respond to model-backed qmd CLI failures by selecting `danger-full-access` or allowing broad qmd, Python, or shell command prefixes.
<!-- codex-agent-skills -->
