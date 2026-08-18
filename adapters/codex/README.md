# Codex Adapter

Installs this repository's skills into Codex's local skills directory without packaging them as a Codex plugin.

```bash
python3 scripts/install_codex.py
```

The installer copies the canonical skills from `skills/`, renders short `memory-*` wrapper skills from `wrappers.toml`, and installs/checks the qmd dependency. It also configures the qmd MCP read path, upserts tagged Codex guidance from `AGENTS.md` into `~/.codex/AGENTS.md`, packages the external-root permission helper under `memory-init-project` and `memory-doctor`, and optionally installs deferred qmd reindex hooks.

For qmd reads, the installer appends the supported STDIO entry below to `$CODEX_HOME/config.toml` only when `mcp_servers.qmd` is absent. It parses the complete TOML before writing, preserves all existing text, and verifies compatible existing entries without rewriting them. An existing enabled streamable-HTTP qmd entry is also preserved; the installer does not start another daemon. A malformed, disabled, filtered, or conflicting qmd entry fails before installation writes begin.

```toml
[mcp_servers.qmd]
command = "qmd"
args = ["mcp"]
```

Start a new Codex session and use `/mcp` to confirm that qmd exposes `query`, `get`, and `multi_get`. Installing the qmd CLI or skill alone does not prove MCP availability. Use `--skip-qmd` to omit the CLI/skill check and MCP setup together.

The generated init and doctor wrappers separately check external write roots. Their read-only `check` mode does not rewrite configuration; persistent permission repair requires the explicit `backfill` subcommand, creates a backup, and requires a new Codex process plus `/status` verification. For a one-off session, prefer repeatable `codex --add-dir <path>` arguments. See [the Codex adapter permission model](../../docs/task-memory-bank-adapters/codex-adapter.md#external-write-permissions).

Run the checker once for a bank root:

```bash
HELPER=~/.agents/skills/memory-doctor/scripts/codex_memory_permissions.py
MEMORY_ROOT=/path/to/task-memory-bank

python3 "$HELPER" check --memory-root "$MEMORY_ROOT"
```

If it reports missing persistent roots, start a one-off session with scoped launch grants:

```bash
codex \
  --add-dir "$MEMORY_ROOT" \
  --add-dir "${XDG_CACHE_HOME:-$HOME/.cache}/qmd" \
  --add-dir "${XDG_CONFIG_HOME:-$HOME/.config}/qmd"
```

Then run `/status` in the new session. The checker reads configuration files, so rerunning it cannot verify launch-only `--add-dir` flags.

For persistent setup instead, backfill the config and start a new process:

```bash
python3 "$HELPER" backfill --memory-root "$MEMORY_ROOT"
codex
```

Run `/status` in that new session before using the external roots.

Reindex runtime files are installed under `~/.codex/hooks/agent-skills/` and four hooks are merged into `~/.codex/hooks.json`:

- `PostToolUse ^apply_patch$` marks qmd collections touched by direct edits.
- `UserPromptSubmit` reindexes settled changes at the next turn.
- `SessionEnd` covers the final turn of a clean session.
- `SessionStart` on startup/resume/clear recovers markers left by an interrupted session; mid-turn compaction is excluded.

Hook installation requires explicit consent. In a terminal, the installer explains that trusted hooks can run qmd with host user permissions and prompts before writing them. Non-interactive installs must pass `--enable-hooks` or `--skip-hooks`; a dry run with neither flag plans no hook installation. `--skip-hooks` leaves hook registration unchanged rather than uninstalling or disabling existing definitions. Installation consent does not trust the hooks.

When a complete matching managed hook installation exists, the installer composes an adapter-owned entrypoint over the preserved canonical task-memory-bank script so successful deterministic writes emit dirty markers without parsing Codex Bash payloads. A fresh `--skip-hooks` install leaves the canonical script untouched, while a skipped reinstall preserves complete existing hook definitions and runtime files and recomposes their adapter entrypoint without rewriting hook configuration. A partial installation must be repaired with `--enable-hooks`; conflicting managed commands fail safely for manual inspection. Reindexing runs detached and silently; `qmd update` runs once per flush and `qmd embed -c` runs for each dirty collection. Start a new Codex session after installing or updating hooks and use `/hooks` to review and trust the definitions as a separate step. Current Codex builds have been observed to execute trusted hooks outside the spawned-command sandbox, but that placement is not an official guarantee and remains a live regression target.

If no matching hooks are installed, or installed hooks are disabled, untrusted, interrupted, or fail, `memory-reindex` runs one `qmd update` after writes settle, then requests one-shot approval for each exact `qmd embed -c <collection>` command. Do not approve bare `qmd embed`, broad qmd/Python/shell prefixes, or `danger-full-access`.

For optional turn-batched Zed diff/revert hooks, also run:

```bash
python3 adapters/zed/install_codex.py
```

Both installers merge their own definitions into `~/.codex/hooks.json` and preserve each other's hooks. The base Codex adapter owns only the qmd MCP entry in `config.toml`; the ZedCodex installer leaves that file untouched. Changed hook definitions require another review through `/hooks`.

Use `--dry-run` to preview writes, or `--target <skills-dir>` to select the Codex skills installation root referenced by the reindex hooks. Use `--skip-agents` to leave `~/.codex/AGENTS.md` untouched, `--skip-qmd` to omit qmd installation and MCP setup, `--enable-hooks` to install or repair managed hooks, `--skip-hooks` to preserve current hook registration without installing updates, or `--codex-home <dir>` to select the home containing Codex configuration and managed hook runtime.
