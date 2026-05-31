# agent-skills

A set of reusable agent skills and workflow notes.

## Platform Support

macOS is the primary supported platform. Linux support is planned but not yet implemented. For Zed users, Windows is out of scope until Zed ships a Windows release.

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

## Install For Claude Code

This repository includes Claude Code adapter source under:

```text
adapters/claude-code/
```

Install the canonical skill plus generated `/memory-*` wrappers with:

```bash
python3 scripts/install_claude_code.py
```

The installer copies `skills/task-memory-bank` and renders wrapper skills from
the adapter manifest. The core skill remains the source of truth.

## Zed Integration

The skill installer (`scripts/install_claude_code.py`) only installs skills — it does not configure how Zed connects to Claude Code.

### Connecting Zed to Claude Code

**Terminal Thread — recommended for Claude Pro/Max subscribers:**
Runs CC inside a Zed terminal pane and uses your Claude subscription directly.

1. In the agent panel, click **+** → **Terminal**
2. Type `claude` and press Enter

`CC_ZED_HOOK=1` is set in `terminal.env` in `~/.config/zed/settings.json` — hooks (snapshot, diff view, revert) work automatically.

**ACP external agent:**
Configured via `agent_servers."claude-acp"` in `~/.config/zed/settings.json`. Starting 2026-06-15, ACP usage is billed at API rates separately from Claude Pro/Max subscriptions. See [Anthropic's subscription changes](https://zed.dev/blog/anthropic-subscription-changes).

## Notes

- [Task memory bank adapter notes](docs/task-memory-bank-adapters/README.md)
- [Task memory bank watcher/reindexer plan](docs/task-memory-bank-watcher.md)
- [Task memory bank implementation order](docs/task-memory-bank-implementation-order.md)
