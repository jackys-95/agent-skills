# agent-skills

A set of reusable agent skills and workflow notes.

## Skills

- [task-memory-bank](skills/task-memory-bank/SKILL.md): qmd-backed project/task memory bank workflows.

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

## Notes

- [Task memory bank adapter notes](docs/task-memory-bank-adapters/README.md)
- [Task memory bank watcher/reindexer plan](docs/task-memory-bank-watcher.md)
- [Task memory bank implementation order](docs/task-memory-bank-implementation-order.md)
