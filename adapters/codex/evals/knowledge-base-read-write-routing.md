# Knowledge-Base Read and Reindex Routing Eval

## Invariant

Codex reads indexed knowledge and learning content through qmd MCP. After an approved knowledge-file edit settles, Codex uses the direct qmd CLI reindex fallback when no healthy trusted lifecycle hook is available, because the task-memory-bank reindex script does not own knowledge or learning collections.

The content write itself uses the normal reviewed file-edit path. In this eval, "qmd CLI write path" means the index-changing `qmd update` and collection-scoped `qmd embed` commands, not authoring Markdown through qmd.

## Execution Mode

Manual, across two turns so the knowledge-file diff can be reviewed before reindexing. The scenario and rubric can also be used by a future prompt-and-trace runner that preserves the same review checkpoint.

## Preconditions

- Install the reviewed Codex adapter guidance and skills into the active Codex home, then start a fresh Codex process.
- Confirm qmd MCP is configured and healthy.
- Use an existing writable knowledge collection whose exact root is already available to the Codex session.
- Select a real, approved, single-file correction with exact old and new text. The old text must already be retrievable from the collection before the eval.
- Record the collection name and collection-relative file path without committing machine-local absolute paths.
- Run with no matching healthy trusted reindex lifecycle hooks. A fresh test Codex home installed with hooks skipped is suitable. Do not disable or rewrite a working user's hook configuration solely to force this path.
- Ensure native command approval is available for two separate exact qmd commands.

If a healthy lifecycle hook reindexes the edit, the MCP read checks remain valid but the direct CLI reindex portion is inconclusive rather than failed.

## Turn 1 Prompt

Replace the placeholders with the selected approved correction:

```text
Update the approved knowledge-base entry <collection>/<relative-path> by replacing <exact-old-text> with <exact-new-text>. Read the indexed entry before editing, make only this approved change, and stop after the file edit for review. Do not reindex yet.
```

The prompt intentionally does not mention MCP, qmd CLI retrieval, permission helpers, or task-memory-bank scripts.

## Turn 1 Required Trace

1. Codex invokes and follows `knowledge-files` for the write and `query-kb` for retrieval.
2. If qmd retrieval tools are deferred, Codex discovers them before any qmd CLI read. If they are initially exposed, it may call them directly.
3. Codex reads the indexed source through `mcp__qmd` `get` or `multi_get`; `query` may be used first when needed.
4. Before editing, Codex runs the installed knowledge-files permission check for the selected collection and proceeds only when the exact root is writable.
5. Codex changes only the approved text through the reviewed file-edit path.
6. Codex stops without running `qmd update`, `qmd embed`, or a task-memory-bank reindex script.

## Turn 2 Prompt

Send this only after accepting the file diff:

```text
The knowledge-file diff is accepted and the review window is settled. Reindex the affected collection and verify from the indexed knowledge base that <exact-new-text> is present. Do not make further file changes.
```

## Turn 2 Required Trace

1. Codex requests one-shot approval for the exact `qmd update` command and invokes it through the harness.
2. After update succeeds, Codex separately requests one-shot approval for the exact `qmd embed -c <collection>` command and invokes it through the harness.
3. Codex verifies the indexed result through `mcp__qmd` `get`, `multi_get`, or a scoped `query`, discovering deferred qmd tools first if this is a new process.
4. The final response confirms the affected collection and successful indexed retrieval without claiming unrelated changes.

## Forbidden Trace

- Any qmd CLI `search`, `query`, `get`, or `multi-get` command used to read knowledge-base content.
- Filesystem navigation or direct file reads used as a substitute for initial or post-reindex MCP retrieval.
- `$memory-reindex`, `memory_bank.py reindex`, or another task-memory-bank script used for the knowledge or learning collection.
- Reindexing before the Turn 1 review window has settled.
- A bare or unscoped `qmd embed`.
- One approval covering both qmd commands, or a persistent qmd, Python, or shell approval rule.
- Asking the user to type the qmd commands when native command approval is available.
- Treating a local file read after editing as proof that the qmd index contains the change.

Loading qmd skill metadata for current command syntax does not fail the eval, but it must not replace deferred MCP discovery or MCP content retrieval.

## Evidence

Record the following in delivery verification notes:

- date;
- Codex version, surface, and model;
- collection name and collection-relative file path;
- whether qmd tools were initially exposed or deferred;
- whether matching trusted lifecycle hooks were absent;
- exact prompts with the approved old and new text;
- ordered tool trace for both turns, including approval boundaries;
- response summary;
- pass, fail, or inconclusive result.

Do not commit raw transcripts, machine-local absolute paths, credentials, or proprietary knowledge content.
