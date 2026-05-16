# agent-skills

A set of reusable agent skills and workflow notes.

## Skills

- [task-memory-bank](skills/task-memory-bank/SKILL.md): qmd-backed project/task memory bank workflows.

## Install For Codex

This repository is the source of truth for authored skills. For the Codex app,
install the composed Codex app variant instead of copying the source skill
verbatim:

```bash
python3 skills/task-memory-bank/scripts/install.py codex-app --clean
```

Codex discovers installed skills from:

```text
~/.agents/skills/<skill-name>/SKILL.md
```

The installer writes a Codex-app-specific `SKILL.md` by composing the portable
base skill with the Codex app adapter appendix. This keeps the repository's
canonical skill content compact while still giving Codex app users the local
sandbox and review-pane instructions they need.

This is a local Codex/agent convention, not a cross-agent standard. Keep
canonical skill content in this repository, then install an adapter-specific
variant into each agent's native skill or command location.

## Notes

- [Task memory bank adapter notes](docs/task-memory-bank-adapters/README.md)
- [Task memory bank watcher/reindexer plan](docs/task-memory-bank-watcher.md)
- [Task memory bank implementation order](docs/task-memory-bank-implementation-order.md)
