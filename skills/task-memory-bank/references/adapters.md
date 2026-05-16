# Slash Command Adapter Reference

Keep memory-bank workflows canonical and generate platform-specific wrappers around them.

## Canonical Workflow Names

```text
memory.init-project
memory.new-work
memory.resume
memory.update
memory.branch
memory.handoff
memory.reindex
memory.doctor
```

## Claude Code

Use user-invocable skills for deterministic workflows. For workflows with side effects, add:

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

## Gemini CLI

Use TOML command files.

Path:

```text
.gemini/commands/memory/resume.toml
```

Command:

```text
/memory:resume
```

Example:

```toml
description = "Resume a qmd-backed task memory bank work item."
prompt = """
Resume memory-bank work for: {{args}}

1. Read the project README and active context.
2. Read the work item README and active context if a work id is provided.
3. Use qmd for targeted supporting context.
4. Summarize objective, current state, next action, and missing context.
"""
```

## Codex

Prefer Codex skills for reusable agent behavior. Expose user-invocable workflows through available slash/menu surfaces when supported by the active Codex surface.

Recommended mapping:

```text
$task-memory-bank for agent-selected behavior
/memory-resume or equivalent prompt shortcut for deterministic user invocation
```

If custom slash prompt support is unavailable in the current Codex surface, use explicit natural-language commands:

```text
Use $task-memory-bank to resume candidate_profile_hub TASK-0042.
```

## Zed

For Zed external agents, prefer the external agent's native command system:

- Claude Agent: Claude skills/custom commands.
- Gemini CLI: Gemini TOML commands.
- Codex: Codex skills/commands where available.

For Zed Text Threads, slash commands can add context but are not agentic. Use them for prompt/context insertion rather than memory-bank mutation.

## Cline

Use Cline slash workflow commands or custom instructions that call the same canonical workflow names. Keep command bodies thin and point to the memory-bank skill/workflow docs.
