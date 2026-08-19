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

The installer copies the canonical `task-memory-bank` skill, generates short `memory-*` wrapper skills from `adapters/codex/wrappers.toml`, copies `query-kb` and `knowledge-files`, installs/checks qmd, and configures the qmd MCP read path. It also upserts tagged Codex guidance from `adapters/codex/AGENTS.md` into `~/.codex/AGENTS.md`, packages the external-write permission helper under the memory init/doctor wrappers and `knowledge-files`, and optionally installs deferred qmd reindex hooks in `~/.codex/hooks.json`. Use `--dry-run` to preview writes, `--target <skills-dir>` to select the Codex skills installation root referenced by reindex hooks, `--skip-agents` to leave Codex guidance untouched, or `--skip-qmd` to omit both qmd setup steps.

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

Repeat `--add-dir` for each exact knowledge or learning child root the current session will write. Do not grant a broad shared parent. This keeps the sandbox in place; do not use full-access or sandbox-bypass modes merely to reach external workflow state.

The installer packages `codex_memory_permissions.py` under the generated `memory-init-project` and `memory-doctor` skills and under the installed `knowledge-files` skill. Init checks the intended bank root before canonical scaffolding writes anything; doctor provides the same check for an existing bank. Before each write to an existing knowledge or learning collection, the Codex-specific section added to the installed `knowledge-files` skill automatically checks the selected collection. Run the installed helper directly when needed:

```bash
python3 ~/.agents/skills/memory-doctor/scripts/codex_memory_permissions.py \
  check --memory-root /path/to/task-memory-bank

python3 ~/.agents/skills/memory-doctor/scripts/codex_memory_permissions.py \
  add-roots --memory-root /path/to/task-memory-bank

python3 ~/.agents/skills/knowledge-files/scripts/codex_memory_permissions.py \
  check --collection example-product-knowledge

python3 ~/.agents/skills/knowledge-files/scripts/codex_memory_permissions.py \
  add-roots \
  --collection example-product-knowledge \
  --expected-root example-product-knowledge /exact/path/reported/by/check

python3 ~/.agents/skills/knowledge-files/scripts/codex_memory_permissions.py \
  resolve-knowledge-learning-pair --collection example-product-knowledge

python3 ~/.agents/skills/knowledge-files/scripts/codex_memory_permissions.py \
  plan-new-collection \
  --collection example-product-learning \
  --expected-root example-product-learning /exact/planned/example-product/learning \
  --contains learning \
  --domain example-product
```

Use `--memory-root <path>` for a memory bank and repeatable `--collection <name>` arguments for registered knowledge or learning collections. Collection mode reads classification from `${XDG_CONFIG_HOME:-~/.config}/qmd/registry.yaml` and resolves the physical directory through `qmd collection show`, so neither the user nor the harness has to remember or duplicate its path. A collection-based `add-roots` command also requires one `--expected-root <collection> <approved-path>` argument per collection; the harness gets that path from `check` or the pair resolver rather than asking the user to remember it. `plan-new-collection` accepts the authoring workflow's proposed name, exact path, classification, and domain before registration and returns path-bound setup arguments. Unknown classifications and inconsistent registry or qmd state fail closed.

Memory-bank operations and pre-registration collection setup include the qmd state roots they maintain. Checks, bound checks, and persistent grants for already registered knowledge or learning collections include only the resolved collection roots; trusted lifecycle hooks or exact host-side fallback commands own subsequent indexing.

`check` never writes. When it finds the required roots in persistent configuration, the harness continues without a permission prompt. If roots are missing and `/status` does not already confirm them for the current process, the harness stops before writing, shows the resolved exact child path, and offers two choices:

- For session-only access: restart with native `codex --add-dir <exact-path>`, repeated only for roots required by the actual write, then use `/status` to verify the effective roots. Session-only access never expands to a related collection.
- Persistent: first run `resolve-knowledge-learning-pair --collection <name>`. The helper, not the harness, deterministically selects one knowledge and one learning collection in the same explicit registry domain, resolves both paths through qmd, and returns a stable knowledge-first result. The harness shows both collection names and exact paths in one approval request without inferring names or paths. On approval it runs the resolver's exact path-bound `add-roots --collection <knowledge-collection> --expected-root <knowledge-collection> <knowledge-path> --collection <learning-collection> --expected-root <learning-collection> <learning-path>` arguments.

If the opposite-classification counterpart is absent or ambiguous, the resolver fails without returning a pair. The persistent flow then offers only the selected collection with `add-roots --collection <name> --expected-root <name> <exact-path-shown-by-check>`; no root is inferred or broadened.

The helper reads persistent files and cannot verify launch-only flags. An exact session grant already confirmed by `/status` is therefore effective even if a later config-only check still reports that path absent. Before collection-based mutation, `add-roots` re-resolves each collection and compares it with the approved expected-root binding. A mismatch requires a fresh preflight and approval and fails before config parsing, backup creation, or mutation. Otherwise, the command previews required roots, validates the complete TOML document, preserves unrelated settings, creates a sibling backup when changing an existing file, validates the result, and atomically replaces the target. It defaults to `$CODEX_HOME/config.toml`; use `--config <path>` for an alternate config or selected profile file.

For a new knowledge or learning collection, `$knowledge-files` selects the name, exact child path, classification, and domain, then runs `plan-new-collection` before creating the root or changing qmd, the shared registry, or Codex config. The planner requires the name to be absent from both catalogs and checks the new root plus the qmd state roots needed for registration. If persistent configuration already covers them, the harness asks no setup question and verifies the running process with `/status`. Otherwise, it shows the planner's exact session-only restart and exact persistent command. The persistent command includes one existing opposite-classification counterpart only when the same explicit registry domain has exactly one; absent or ambiguous counterparts keep it scoped to the planned collection. The harness requests approval once and relays the selected command without inferring a name or path. Declining before a session grant leaves the root, both catalogs, and Codex config unchanged.

After the planned roots are effective, the harness creates the root, registers both catalogs, and runs `check --collection <new-collection> --expected-root <new-collection> <planned-exact-path>`. A changed qmd path fails before content writes and requires a fresh plan and approval. If the path binding is unchanged and the check reports only persistent roots already confirmed by `/status`, the exact session grant remains effective. A persistent config change requires a new Codex process plus `/status` before registration.

`add-roots` supports:

- Legacy or unset configuration through `sandbox_mode = "workspace-write"` and `sandbox_workspace_write.writable_roots`.
- An explicitly selected custom `default_permissions` profile through its `workspace_roots` table.

It fails closed instead of guessing when configuration is malformed, mixes legacy and profile models, selects a built-in permission profile, selects an external profile layer, or otherwise cannot identify one safe mutation target. It does not alter approval policy, network access, managed requirements, or unrelated sandbox settings.

Codex reads persistent configuration at process startup. After `add-roots` changes the config, start a new Codex process and use `/status` to confirm that the expected roots are effective. Launch flags, project config, selected profiles, and managed requirements can override the edited file, so `/status` remains authoritative for the running process.

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

If no matching hooks are installed, or installed hooks are disabled, untrusted, interrupted, or fail, use `$memory-reindex` after memory-bank writes settle. The Codex wrapper runs one `qmd update`, then requests one-shot approval for each exact `qmd embed -c <collection>` command.

Knowledge and learning authoring must not route through `$memory-reindex` or `memory_bank.py reindex`. After the editor review window settles, request one-shot approval for the exact `qmd update` command outside the spawned-command sandbox. After it succeeds, request separate one-shot approval for the exact `qmd embed -c <collection>` command outside that sandbox, then verify retrieval through qmd MCP. The harness invokes both commands; manual execution is only a fallback when native approval is unavailable. Neither fallback may first hide either command in a nested sandboxed Python process, request bare `qmd embed`, create broad qmd, Python, or shell command rules, or select `danger-full-access`.

Codex automations can support scheduled or delayed maintenance workflows, such as reminding the current thread to update memory or running a periodic reindex job. Keep automations explicit and user-approved.
