# Codex Adapter

Prefer Codex skills for reusable agent behavior. Expose user-invocable workflows through available slash/menu surfaces when supported by the active Codex surface.

Install local Codex skills under:

```text
~/.agents/skills/<skill-name>/SKILL.md
```

For this repository:

```bash
mkdir -p ~/.agents/skills/task-memory-bank
cp -R skills/task-memory-bank/. ~/.agents/skills/task-memory-bank/
```

Treat `~/.agents/skills` as the local installed-skill target, not the source of truth. Keep authored skill content in the repository and copy or package it into the active Codex skills directory when installing.

Recommended mapping:

```text
$task-memory-bank for agent-selected behavior
/memory-resume or equivalent prompt shortcut for deterministic user invocation
```

If custom slash prompt support is unavailable in the current Codex surface, use explicit natural-language commands:

```text
Use $task-memory-bank to resume example_project TASK-0042.
```

Codex automations can support scheduled or delayed maintenance workflows, such as reminding the current thread to update memory or running a periodic reindex job. Keep automations explicit and user-approved.
