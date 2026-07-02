# agent-skills

A set of reusable agent skills and workflow notes.

## Platform Support

macOS is the primary supported platform. Linux support is planned but not yet implemented. For Zed users, Windows is out of scope until Zed ships a Windows release.

## Skills

- [task-memory-bank](skills/task-memory-bank/SKILL.md): qmd-backed project/task memory bank workflows.
- [query-kb](skills/query-kb/SKILL.md): qmd-backed knowledge base retrieval (knowledge files + learning primers); delegates task scope to task-memory-bank.

## Install For Codex

This repository is the source of truth for authored skills. To make a skill
available to Codex locally, install it into the shared local agent skills
directory:

```bash
mkdir -p ~/.agents/skills/task-memory-bank
cp -R skills/task-memory-bank/. ~/.agents/skills/task-memory-bank/
```

Codex discovers installed skills from:

```text
~/.agents/skills/<skill-name>/SKILL.md
```

This is a local Codex/agent convention, not a cross-agent standard. Keep
canonical skill content in this repository, then adapt or copy it into each
agent's native skill or command location.

## Install For Claude Code

This repository includes Claude Code adapter source under:

```text
adapters/claude-code/
```

Install the skills plus generated `/memory-*` wrappers with:

```bash
python3 scripts/install_claude_code.py
```

The installer copies `skills/task-memory-bank`, renders wrapper skills from the adapter manifest, copies plain skills listed in the manifest (`skills/query-kb`), installs the qmd skill (installing qmd itself first if it is not already present), and installs the qmd reindex hooks from `adapters/claude-code/hooks/` — copied to `~/.claude/hooks/` and registered in `~/.claude/settings.json` so memory-bank edits are reindexed automatically at turn boundaries. The core skills remain the source of truth.

**query-kb setup:** query-kb reads a git-ignored `registry.yaml` at its skill root listing the knowledge/learning collections to search. After installing, copy the template and fill in your real collection names:

```bash
cp ~/.claude/skills/query-kb/assets/registry.example.yaml ~/.claude/skills/query-kb/registry.yaml
```

**Prerequisite:** qmd is required for task-memory-bank to work. The installer handles this automatically; if you prefer to install manually:

```bash
bun install -g @tobilu/qmd   # or: npm install -g @tobilu/qmd
```

## Zed Integrations

You can use these agent skills with parallel agent harnesses of your choice (e.g., Claude Code, Codex) with Zed as the "meta-harness". Currently these agent skills currently supports Zed and Claude Code (CC)

**zed-cc** is a Zed + CC pairing. It requires two adapters: the CC adapter (skills and wrappers) and the Zed adapter (diff view hooks).

```bash
# 1. CC adapter — installs skills, /memory-* wrappers, and reindex hooks
python3 scripts/install_claude_code.py

# 2. Zed adapter — installs diff view hooks, updates settings and CLAUDE.md
python3 adapters/zed/install.py
```

See [adapters/zed/README.md](adapters/zed/README.md) for how to enable the hooks inside Zed (terminal thread or ACP).

## Notes

- [Task memory bank adapter notes](docs/task-memory-bank-adapters/README.md)
- [Task memory bank watcher/reindexer plan](docs/task-memory-bank-watcher.md)
- [Task memory bank implementation order](docs/task-memory-bank-implementation-order.md)
