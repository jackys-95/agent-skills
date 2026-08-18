# Codex Adapter

Prefer Codex skills for reusable agent behavior. Expose user-invocable workflows through explicit skill invocation and available slash/menu surfaces when supported by the active Codex surface.

Install local Codex skills under:

```text
~/.agents/skills/<skill-name>/SKILL.md
```

For this repository, install the Codex adapter with:

```bash
python3 scripts/install_codex.py
```

The installer copies the canonical `task-memory-bank` skill, generates short `memory-*` wrapper skills from `adapters/codex/wrappers.toml`, copies `query-kb` and `knowledge-files`, installs/checks qmd, and configures the qmd MCP read path. It also upserts tagged Codex guidance from `adapters/codex/AGENTS.md` into `~/.codex/AGENTS.md` and optionally installs deferred qmd reindex hooks in `~/.codex/hooks.json`. Use `--dry-run` to preview writes, `--target <skills-dir>` to select the Codex skills installation root referenced by reindex hooks, `--skip-agents` to leave Codex guidance untouched, or `--skip-qmd` to omit both qmd setup steps.

Hook installation requires a separate choice. Interactive installs explain the execution boundary and prompt; non-interactive installs must pass `--enable-hooks` or `--skip-hooks`. With neither flag, a dry run does not prompt and plans no hook installation. `--skip-hooks` preserves existing hook registration rather than uninstalling or disabling definitions.

## MCP Read Path

Codex officially supports local STDIO MCP servers through `[mcp_servers.<name>]` in `config.toml` and through `codex mcp`; see the [Codex MCP documentation](https://learn.chatgpt.com/docs/extend/mcp). The installer uses the equivalent supported configuration:

```toml
[mcp_servers.qmd]
command = "qmd"
args = ["mcp"]
```

The installer parses the complete `$CODEX_HOME/config.toml` before writing and appends this table only when `mcp_servers.qmd` is absent. It preserves unrelated MCP, provider, project, permission, and comment text. An existing compatible qmd STDIO entry is verified without a rewrite. An existing enabled streamable-HTTP qmd entry is also preserved; the installer does not start another qmd daemon. A malformed document, conflicting STDIO command or arguments, disabled server, mixed transport, or tool filter that removes `query`, `get`, or `multi_get` fails before any installation writes; the installer does not silently replace user-owned qmd configuration.

After installation, restart Codex and use `/mcp` to verify that the qmd server starts and exposes `query`, `get`, and `multi_get`. These are distinct checks:

- A qmd executable proves only that the CLI is installed.
- A qmd skill proves only that agent instructions are installed.
- A valid MCP table proves only that Codex has connection configuration.
- `/mcp` showing the tools proves that the current client initialized the server.

Codex agents should prefer MCP `query`, `get`, and `multi_get` for reads. Lexical `qmd search` is the degraded CLI fallback when MCP is unavailable. Model-backed CLI query, vector search, and reranking are not the default on macOS because spawned commands can fail while initializing Metal under the Seatbelt sandbox.

Writable roots extend filesystem access; they do not grant Metal device or API access. This distinction follows the [Codex sandbox model](https://learn.chatgpt.com/docs/sandboxing?surface=cli). The general Metal/MLX/CoreML limitation remains tracked in [openai/codex#16931](https://github.com/openai/codex/issues/16931) and [openai/codex#17644](https://github.com/openai/codex/issues/17644). This adapter does not weaken the sandbox to work around it.

The qmd CLI and MCP server resolve the same cached GGUF model files, so MCP-first reads do not create another on-disk model copy. They are separate processes, however, and a direct embed subprocess can load its own in-memory embedding context while the MCP server holds query-time contexts. HyDE is a retrieval strategy, not another model file.

## External Write Permissions

Memory banks, knowledge collections, and qmd state usually live outside the active repository. Codex's workspace sandbox needs explicit writable roots for those paths:

- Task-memory-bank changes require the selected bank root.
- Knowledge-file authoring requires the selected knowledge or learning root.
- `qmd update` and `qmd embed` require `${XDG_CACHE_HOME:-~/.cache}/qmd` and may update `${XDG_CONFIG_HOME:-~/.config}/qmd`; those roots do not make Metal available to a sandboxed embed process.
- Successful qmd MCP retrieval is read-only evidence and does not establish write access for markdown or qmd CLI maintenance.

For one CLI session, grant only the roots that workflow needs:

```bash
codex \
  --add-dir /path/to/task-memory-bank \
  --add-dir "${XDG_CACHE_HOME:-$HOME/.cache}/qmd" \
  --add-dir "${XDG_CONFIG_HOME:-$HOME/.config}/qmd"
```

Repeat `--add-dir` for a selected knowledge or learning root when authoring there. This keeps the sandbox in place; do not use full-access or sandbox-bypass modes merely to reach external workflow state.

The installer packages `codex_memory_permissions.py` under the generated `memory-init-project` and `memory-doctor` skills. Init checks the intended bank root before canonical scaffolding writes anything; doctor provides the same check for an existing bank. Run the installed helper directly when needed:

```bash
python3 ~/.agents/skills/memory-doctor/scripts/codex_memory_permissions.py \
  check --memory-root /path/to/task-memory-bank

python3 ~/.agents/skills/memory-doctor/scripts/codex_memory_permissions.py \
  backfill --memory-root /path/to/task-memory-bank
```

Add repeatable `--knowledge-root <path>` arguments when the workflow will author knowledge files. `check` never writes. The explicit `backfill` command previews required roots, validates the complete TOML document, preserves unrelated settings, creates a sibling backup when changing an existing file, validates the result, and atomically replaces the target. It defaults to `$CODEX_HOME/config.toml`; use `--config <path>` for an alternate config or selected profile file.

Backfill supports:

- Legacy or unset configuration through `sandbox_mode = "workspace-write"` and `sandbox_workspace_write.writable_roots`.
- An explicitly selected custom `default_permissions` profile through its `workspace_roots` table.

It fails closed instead of guessing when configuration is malformed, mixes legacy and profile models, selects a built-in permission profile, selects an external profile layer, or otherwise cannot identify one safe mutation target. It does not alter approval policy, network access, managed requirements, or unrelated sandbox settings.

Codex reads persistent configuration at process startup. After a changed backfill, start a new Codex process and use `/status` to confirm that the expected roots are effective. Launch flags, project config, selected profiles, and managed requirements can override the edited file, so `/status` remains authoritative for the running process.

Treat `~/.agents/skills` as the local installed-skill target, not the source of truth. Keep authored skill content in the repository and copy or package it into the active Codex skills directory when installing.

Recommended mapping:

```text
$task-memory-bank for agent-selected behavior
$memory-resume or equivalent generated wrapper skill for deterministic user invocation
```

If custom slash prompt support is unavailable in the current Codex surface, use explicit natural-language commands:

```text
Use $task-memory-bank to resume the saved-filter task in example_project.
```

## Deferred Reindex Hooks

Codex supports `PostToolUse`, `UserPromptSubmit`, `SessionStart`, and `SessionEnd` command hooks in user-level `~/.codex/hooks.json`; see the [official Codex hooks documentation](https://developers.openai.com/codex/hooks/). The installer uses those events to preserve the settled-state invariant:

- Successful `apply_patch` calls are parsed for Add, Update, Delete, and Move paths. Registered qmd collections containing those paths are marked dirty.
- When a complete matching managed hook installation exists, the installer composes an adapter-owned `memory_bank.py` facade over the preserved canonical script. The facade marks successful deterministic writes without trying to infer changed files from a Bash payload that contains only the command. A fresh `--skip-hooks` install remains canonical; a skipped reinstall preserves complete existing hook definitions and runtime files and recomposes their facade without rewriting hook configuration. Partial installations require `--enable-hooks` repair, while conflicting managed commands fail for inspection.
- `UserPromptSubmit` flushes settled changes at the next turn, `SessionEnd` covers the final clean turn, and `SessionStart` on startup/resume/clear recovers markers left by an interrupted session. The matcher excludes `source: compact`, which Codex may emit mid-turn.

The shared marker and flush runtime lives in `adapters/core/`; only changed-path extraction is harness-specific. Reindex work is detached and silent. One `qmd update` runs per flush, followed by `qmd embed -c <collection>` for each dirty collection.

Consent has two independent stages:

1. The installer asks whether it may write hooks that can perform qmd inference with host user permissions. `--enable-hooks` records an explicit yes; `--skip-hooks` records an instruction not to install or update hooks during this run while preserving a complete matching managed hook installation.
2. Non-managed Codex hooks remain disabled until a new session reviews and trusts their exact definitions through `/hooks`.

Current Codex builds have been observed to execute trusted command hooks outside the spawned-command sandbox, allowing the deferred collection embed to use Metal. Official hook documentation specifies review and hash-bound trust but does not guarantee this execution placement. Bare Codex and ZedCodex write-to-marker-to-embed-to-MCP retrieval smoke tests therefore remain required regression coverage.

If no matching hooks are installed, or installed hooks are disabled, untrusted, interrupted, or fail, use `$memory-reindex` after writes settle. The Codex wrapper runs one `qmd update`, then requests one-shot approval for each exact `qmd embed -c <collection>` command. It must not first hide the embed in a nested sandboxed Python process, request bare `qmd embed`, create broad qmd, Python, or shell command rules, or select `danger-full-access`.

Codex automations can support scheduled or delayed maintenance workflows, such as reminding the current thread to update memory or running a periodic reindex job. Keep automations explicit and user-approved.
