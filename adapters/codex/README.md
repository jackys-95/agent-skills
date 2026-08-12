# Codex Adapter

Installs this repository's skills into Codex's local skills directory without packaging them as a Codex plugin.

```bash
python3 scripts/install_codex.py
```

The installer copies the canonical skills from `skills/`, renders short `memory-*` wrapper skills from `wrappers.toml`, and optionally installs/checks the qmd dependency. It also upserts tagged Codex guidance from `AGENTS.md` into `~/.codex/AGENTS.md`, packages the external-root permission helper under `memory-init-project` and `memory-doctor`, and installs deferred qmd reindex hooks.

The installer never modifies `~/.codex/config.toml`. The generated init and doctor wrappers run the helper in read-only `check` mode for roots they are asked to inspect; normal sessions do not repeat the check after setup. Persistent repair requires the explicit `backfill` subcommand, creates a backup, and requires a new Codex process plus `/status` verification. For a one-off session, prefer repeatable `codex --add-dir <path>` arguments. See [the Codex adapter permission model](../../docs/task-memory-bank-adapters/codex-adapter.md#external-write-permissions).

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

Reindex runtime files are installed under `~/.codex/hooks/agent-skills/` and
four hooks are merged into `~/.codex/hooks.json`:

- `PostToolUse ^apply_patch$` marks qmd collections touched by direct edits.
- `UserPromptSubmit` reindexes settled changes at the next turn.
- `SessionEnd` covers the final turn of a clean session.
- `SessionStart` on startup/resume/clear recovers markers left by an interrupted
  session; mid-turn compaction is excluded.

Deterministic task-memory-bank script writes emit the same dirty marker
directly, because Codex Bash hook payloads do not provide canonical changed
paths. Reindexing runs detached and silently; `qmd update` runs once per flush
and `qmd embed -c` runs for each dirty collection. Start a new Codex session
after installation and use `/hooks` to review and trust the definitions. Use
`--skip-hooks` to omit them; `memory-reindex` remains the manual fallback.

For optional turn-batched Zed diff/revert hooks, also run:

```bash
python3 adapters/zed/install_codex.py
```

Both installers merge their own definitions into `~/.codex/hooks.json`, leave
`config.toml` untouched, and preserve each other's hooks. Changed definitions
require another review through `/hooks`.

Use `--dry-run` to preview writes, or `--target <dir>` to install somewhere other than `~/.agents/skills`. Use `--skip-agents` to leave `~/.codex/AGENTS.md` untouched, `--skip-hooks` to omit reindex automation, or `--codex-home <dir>` to select an alternate Codex home.
