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
- Reindex only after memory-bank writes are settled. Codex reindex hooks are not installed by this adapter yet; use `$memory-reindex` or the shared `memory_bank.py reindex` command as the manual fallback.

## Codex Surface Notes

These instructions assume Codex can read local skills from `~/.agents/skills`. Avoid depending on product-specific desktop UI behavior in the skill workflow.

- For CLI sessions, external memory-bank paths can be granted with command-line writable roots such as `--add-dir`, or with persistent config.
- For non-CLI surfaces, confirm the active surface's current local-file, writable-root, and review behavior before relying on external memory-bank writes.
- If a surface cannot review external memory-bank diffs directly, keep those memory edits in a separate phase and report the files changed explicitly.
<!-- codex-agent-skills -->

<!-- zed-codex-adapter -->
# ZedCodex Review Behavior

When `CODEX_ZED_HOOK=1` is present, `apply_patch` changes are collected into one Zed multi-diff at the end of the turn. The review is non-blocking.

- After each successful `apply_patch`, surface every hook-provided `reply 'r <file>' to revert` instruction as a standalone line.
- When the user replies `r <file>`, run `python3 ~/.codex/hooks/zedcodex/revert_codex_zed_snapshot.py <file>` and then ask what they want instead.
- For `revert all`, run the same command once for every file changed in the reviewed turn.
- Prefer `apply_patch` for file mutation while this adapter is active. Shell redirection, `sed -i`, move commands, and scripts that write files bypass the current review detector and will not get a Zed diff or revert snapshot.
- Do not narrate the diff contents or ask for acceptance. Silence means the user accepted the files on disk.

Reverting restores each file to its first pre-edit state from the turn. A file created during the turn is deleted when reverted.

## When the user saves in the diff view

A save in Zed (Cmd+S on macOS, Ctrl+S on Linux) keeps the user's version on disk and discards yours for that file — but **nothing notifies this session**. There is no watcher echoing the saved delta back, so the file on disk can differ from what you last wrote with no signal in the conversation.

- Re-read a file before editing it again if the user may have saved it, and re-read it whenever they mention editing, saving, or keeping their own version. Do not assume your last written content is still current.
- Do not treat silence as confirmation that your version survived. Silence means the user did not ask for a revert; it does not mean they did not edit the file themselves.
<!-- zed-codex-adapter -->
