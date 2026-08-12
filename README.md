# agent-skills

A set of reusable agent skills and workflow notes.

## Platform Support

macOS and Linux are both supported. For Zed users, Windows is out of scope until Zed ships a Windows release.

## Skills

- [task-memory-bank](skills/task-memory-bank/SKILL.md): qmd-backed project/task memory bank workflows.
- [query-kb](skills/query-kb/SKILL.md): qmd-backed knowledge base retrieval (knowledge files + learning primers); delegates task scope to task-memory-bank.
- [knowledge-files](skills/knowledge-files/SKILL.md): qmd-backed knowledge file authoring (classify, split into per-entity files, cross-reference, promote learning → knowledge); the write side of the knowledge base.

## Tests

Run installer unit tests with:

```bash
python3 -m unittest discover -s scripts -p 'test_*.py'
```

## Install For Codex

This repository is the source of truth for authored skills. Install the Codex
adapter into the shared local agent skills directory with:

```bash
python3 scripts/install_codex.py
```

Codex discovers installed skills from:

```text
~/.agents/skills/<skill-name>/SKILL.md
```

The installer copies `skills/task-memory-bank`, renders `memory-*` wrapper
skills from the Codex adapter manifest, copies plain skills listed in the
manifest (`skills/query-kb`, `skills/knowledge-files`), and installs the qmd
skill dependency when possible. It also upserts tagged Codex guidance into
`~/.codex/AGENTS.md`. It does not install Codex hooks yet; use the
`memory-reindex` wrapper as the manual fallback after memory-bank edits.

**query-kb setup:** query-kb reads a `registry.yaml` listing the knowledge/learning collections to search. It lives at a **harness-neutral** path beside qmd's own config — `${XDG_CONFIG_HOME:-~/.config}/qmd/registry.yaml` — so every harness's skill copy reads one shared file. It is normally created and grown by the `knowledge-files` authoring skill when you add a collection; to bootstrap by hand, copy the schema reference and fill in your collection names:

```bash
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/qmd"
cp ~/.agents/skills/query-kb/assets/registry.example.yaml "${XDG_CONFIG_HOME:-$HOME/.config}/qmd/registry.yaml"
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

The installer copies `skills/task-memory-bank`, renders wrapper skills from the adapter manifest, copies plain skills listed in the manifest (`skills/query-kb`, `skills/knowledge-files`), installs the qmd skill (installing qmd itself first if it is not already present), and installs the qmd reindex hooks from `adapters/claude-code/hooks/` — copied to `~/.claude/hooks/` and registered in `~/.claude/settings.json` so memory-bank edits are reindexed automatically at turn boundaries. The core skills remain the source of truth.

**query-kb setup:** query-kb reads a `registry.yaml` listing the knowledge/learning collections to search. It lives at a **harness-neutral** path beside qmd's own config — `${XDG_CONFIG_HOME:-~/.config}/qmd/registry.yaml` — so every harness's skill copy reads one shared file. It is normally created and grown by the `knowledge-files` authoring skill when you add a collection; to bootstrap by hand, copy the schema reference and fill in your collection names:

```bash
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/qmd"
cp ~/.claude/skills/query-kb/assets/registry.example.yaml "${XDG_CONFIG_HOME:-$HOME/.config}/qmd/registry.yaml"
```

**Prerequisite:** qmd is required for task-memory-bank to work. The installer handles this automatically; if you prefer to install manually:

```bash
bun install -g @tobilu/qmd   # or: npm install -g @tobilu/qmd
```

## Zed Integrations

You can use these agent skills with Claude Code or Codex while Zed provides the
editor-side review surface.

**zed-cc** is a Zed + CC pairing. It requires two adapters: the CC adapter (skills and wrappers) and the Zed adapter (diff view hooks).

```bash
# 1. CC adapter — installs skills, /memory-* wrappers, and reindex hooks
python3 scripts/install_claude_code.py

# 2. Zed adapter — installs diff view hooks, updates settings and CLAUDE.md
python3 adapters/zed/install.py
```

**ZedCodex** pairs Zed with Codex CLI:

```bash
# 1. Codex adapter — installs skills, wrappers, and AGENTS.md guidance
python3 scripts/install_codex.py

# 2. ZedCodex hooks — installs turn-batched diff/revert behavior
python3 adapters/zed/install_codex.py
```

See [adapters/zed/README.md](adapters/zed/README.md) for activation and hook
trust steps.

## Notes

- [Task memory bank adapter notes](docs/task-memory-bank-adapters/README.md)
- [Task memory bank watcher/reindexer plan](docs/task-memory-bank-watcher.md)
- [Task memory bank implementation order](docs/task-memory-bank-implementation-order.md)
