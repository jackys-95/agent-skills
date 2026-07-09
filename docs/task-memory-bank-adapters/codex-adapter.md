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
`adapters/codex/AGENTS.md` into `~/.codex/AGENTS.md`. Use `--dry-run` to preview
writes, `--target <dir>` to install somewhere other than `~/.agents/skills`, or
`--skip-agents` to leave Codex guidance untouched.

Treat `~/.agents/skills` as the local installed-skill target, not the source of truth. Keep authored skill content in the repository and copy or package it into the active Codex skills directory when installing.

Recommended mapping:

```text
$task-memory-bank for agent-selected behavior
$memory-resume or equivalent generated wrapper skill for deterministic user invocation
```

If custom slash prompt support is unavailable in the current Codex surface, use explicit natural-language commands:

```text
Use $task-memory-bank to resume example_project TASK-0042.
```

Codex reindex hooks are intentionally out of scope for the first installer.
After memory-bank edits, use `$memory-reindex` or run the task-memory-bank
reindex script manually. Add Codex hooks only after validating Codex's real edit
hook payload and matcher behavior.

Codex automations can support scheduled or delayed maintenance workflows, such as reminding the current thread to update memory or running a periodic reindex job. Keep automations explicit and user-approved.
