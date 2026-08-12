# Codex Adapter

Installs this repository's skills into Codex's local skills directory without packaging them as a Codex plugin.

```bash
python3 scripts/install_codex.py
```

The installer copies the canonical skills from `skills/`, renders short `memory-*` wrapper skills from `wrappers.toml`, and optionally installs/checks the qmd dependency. It also upserts tagged Codex guidance from `AGENTS.md` into `~/.codex/AGENTS.md` and packages the external-root permission helper under `memory-init-project` and `memory-doctor`.

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

It does not install memory-bank reindex hooks yet; use the `memory-reindex` wrapper as the manual fallback after memory-bank edits.

For optional turn-batched Zed diff/revert hooks, also run:

```bash
python3 adapters/zed/install_codex.py
```

That installer uses `~/.codex/hooks.json`, leaves `config.toml` untouched, and requires review through `/hooks`.

Use `--dry-run` to preview writes, or `--target <dir>` to install somewhere other than `~/.agents/skills`. Use `--skip-agents` to leave `~/.codex/AGENTS.md` untouched.
