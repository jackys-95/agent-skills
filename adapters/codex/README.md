# Codex Adapter

Installs this repository's skills into Codex's local skills directory without
packaging them as a Codex plugin.

```bash
python3 scripts/install_codex.py
```

The installer copies the canonical skills from `skills/`, renders short
`memory-*` wrapper skills from `wrappers.toml`, and optionally installs/checks
the qmd dependency. It also upserts tagged Codex guidance from `AGENTS.md` into
`~/.codex/AGENTS.md`.

It does not install Codex hooks yet; use the `memory-reindex` wrapper as the
manual fallback after memory-bank edits.

Use `--dry-run` to preview writes, or `--target <dir>` to install somewhere
other than `~/.agents/skills`. Use `--skip-agents` to leave
`~/.codex/AGENTS.md` untouched.
