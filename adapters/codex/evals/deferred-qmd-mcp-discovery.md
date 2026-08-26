# Deferred qmd MCP Discovery Eval

## Invariant

When qmd MCP retrieval tools are configured but their schemas are deferred, Codex discovers and uses those tools before considering a qmd CLI read.

## Execution Mode

Manual. The scenario and rubric are independent of execution mode so a future non-interactive Codex runner can drive the same case.

## Preconditions

- Install the reviewed Codex adapter guidance into the active Codex home.
- Start a fresh Codex process after installation.
- Confirm qmd MCP is configured and healthy.
- Use a session where qmd `query`, `get`, and `multi_get` are not initially exposed. If they are already exposed, a direct MCP call is correct but does not exercise deferred discovery, so record the run as inconclusive.
- Choose a repository with an indexed task-memory-bank project and an existing saved work item that can be identified by a public issue, another non-private reference, or a unique human-readable title.
- Record the expected saved objective, current phase, and next action before starting the eval.

## Prompt

Replace the placeholders with the selected repository and work reference:

```text
In the <repository-name> repository, resume the saved task-memory-bank work for <work-reference>. Read the saved context and report only the objective, current phase, and next action. Do not modify files.
```

The prompt intentionally does not mention MCP, deferred tools, qmd CLI behavior, collection names, or machine-local paths.

## Required Trace

1. Codex searches deferred tools for qmd retrieval capabilities before invoking any qmd CLI read.
2. Codex calls discovered `mcp__qmd` `query` and then `get` or `multi_get` as needed.
3. The final response accurately reports the saved objective, phase, and next action.

## Forbidden Trace

- An `exec_command` call that invokes qmd for reading before deferred discovery.
- `qmd skill show` as a substitute for deferred MCP discovery.
- Filesystem exploration or search of the memory bank.
- A claim that qmd MCP is unavailable solely because its tools were absent from the initially exposed list.

Any forbidden trace fails the eval even if lexical retrieval eventually returns the correct document.

## Evidence

Record the following in delivery verification notes:

- date;
- Codex version and surface;
- model;
- repository name and non-private work reference;
- expected saved objective, phase, and next action;
- whether qmd tools were initially exposed;
- exact prompt;
- ordered tool trace;
- response summary;
- pass, fail, or inconclusive result.

Do not commit raw transcripts or captures that may contain prompts, credentials, or machine-local paths.
