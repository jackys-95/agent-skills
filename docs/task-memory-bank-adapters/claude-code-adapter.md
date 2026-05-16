# Claude Code Adapter

Use Claude Code user-invocable skills for deterministic memory-bank workflows. For workflows with side effects, add:

```yaml
disable-model-invocation: true
```

Example `~/.claude/skills/memory-resume/SKILL.md`:

```md
---
name: memory-resume
description: Resume a qmd-backed task memory bank work item.
disable-model-invocation: true
argument-hint: "[project] [work-id]"
---

Resume memory-bank work for $ARGUMENTS:

1. Read the project README and active context.
2. Read the work item README and active context if a work id is provided.
3. Use qmd for targeted supporting context.
4. Summarize objective, current state, next action, and missing context.
```

Use hooks/events only for lightweight coordination such as prompting an update or reindex after a session. Do not hide memory-bank mutations inside hooks unless the user has explicitly opted into that behavior.
