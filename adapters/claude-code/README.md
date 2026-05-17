# Claude Code Adapter Source

This directory contains the source for generating Claude Code skill wrappers.

The canonical workflow implementation remains in:

```text
skills/task-memory-bank/
```

The wrapper manifest is:

```text
wrappers.toml
```

The installer renders each wrapper with:

```text
templates/wrapper.SKILL.md.tmpl
```

Install into Claude Code's skill directory with:

```bash
python3 scripts/install_claude_code.py
```

Use `--dry-run` to preview writes, or `--target <dir>` to install somewhere other than `~/.claude/skills`.
