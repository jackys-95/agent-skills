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

The installer copies the canonical `task-memory-bank` skill, generates short
`memory-*` wrapper skills from `adapters/codex/wrappers.toml`, copies
`query-kb` and `knowledge-files`, and installs/checks the qmd skill dependency
when possible. It also upserts tagged Codex guidance from
`adapters/codex/AGENTS.md` into `~/.codex/AGENTS.md` and installs deferred qmd
reindex hooks in `~/.codex/hooks.json`. Use `--dry-run` to preview writes,
`--target <dir>` to install somewhere other than `~/.agents/skills`,
`--skip-agents` to leave Codex guidance untouched, or `--skip-hooks` to omit
reindex automation.

## External Write Permissions

Memory banks, knowledge collections, and qmd state usually live outside the active repository. Codex's workspace sandbox needs explicit writable roots for those paths:

- Task-memory-bank changes require the selected bank root.
- Knowledge-file authoring requires the selected knowledge or learning root.
- `qmd update` and `qmd embed` require `${XDG_CACHE_HOME:-~/.cache}/qmd` and may update `${XDG_CONFIG_HOME:-~/.config}/qmd`.
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

Codex supports `PostToolUse`, `UserPromptSubmit`, `SessionStart`, and
`SessionEnd` command hooks in user-level `~/.codex/hooks.json`; see the
[official Codex hooks documentation](https://developers.openai.com/codex/hooks/).
The installer uses those events to preserve the settled-state invariant:

- Successful `apply_patch` calls are parsed for Add, Update, Delete, and Move
  paths. Registered qmd collections containing those paths are marked dirty.
- When hooks are enabled, the installer composes an adapter-owned
  `memory_bank.py` facade over the preserved canonical script. The facade marks
  successful deterministic writes without trying to infer changed files from a
  Bash payload that contains only the command. `--skip-hooks` leaves the
  canonical entrypoint untouched.
- `UserPromptSubmit` flushes settled changes at the next turn, `SessionEnd`
  covers the final clean turn, and `SessionStart` on startup/resume/clear
  recovers markers left by an interrupted session. The matcher excludes
  `source: compact`, which Codex may emit mid-turn.

The shared marker and flush runtime lives in `adapters/core/`; only changed-path
extraction is harness-specific. Reindex work is detached and silent. One
`qmd update` runs per flush, followed by `qmd embed -c <collection>` for each
dirty collection.

Non-managed Codex hooks require explicit trust. After installation, start a new
Codex session and use `/hooks` to review the definitions. If hooks are skipped,
disabled, untrusted, interrupted, or fail, use `$memory-reindex` or run the
task-memory-bank reindex script manually.

Codex automations can support scheduled or delayed maintenance workflows, such as reminding the current thread to update memory or running a periodic reindex job. Keep automations explicit and user-approved.
