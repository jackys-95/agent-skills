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
- Do not explore or search the memory bank with filesystem tools. Use qmd tools, qmd CLI, or the task-memory-bank script's deterministic entry points.
- Keep memory-bank edits separate from implementation edits when the user needs a clean review window.
- Reindex only after memory-bank writes are settled. The adapter's lifecycle hooks normally handle this; use `$memory-reindex` or the shared `memory_bank.py reindex` command if hooks are skipped, disabled, untrusted, or interrupted.

## Codex Surface Notes

These instructions assume Codex can read local skills from `~/.agents/skills`. Avoid depending on product-specific desktop UI behavior in the skill workflow.

- For non-CLI surfaces, confirm the active surface's current local-file, writable-root, and review behavior before relying on external memory-bank writes.
- If a surface cannot review external memory-bank diffs directly, keep those memory edits in a separate phase and report the files changed explicitly.
<!-- codex-agent-skills -->
