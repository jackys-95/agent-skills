# Adapter Reference

Use these maintainer notes when making task-memory-bank installable or more ergonomic in a specific agentic harness. Slash commands are one adapter surface; hooks, events, menu commands, prompt shortcuts, and background jobs may also belong here when the harness supports them.

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

## Harness References

- [claude-code-adapter.md](claude-code-adapter.md): Claude Code skills, command wrappers, and hooks.
- [codex-adapter.md](codex-adapter.md): Codex skills, local install target, slash/menu exposure, and automations.
- [gemini-cli-adapter.md](gemini-cli-adapter.md): Gemini CLI command files and related harness behavior.
- [zed-adapter.md](zed-adapter.md): Zed external agents and text-thread command surfaces.
- [cline-adapter.md](cline-adapter.md): Cline slash workflows and custom instructions.

Keep adapter bodies thin. They should map harness-specific invocation into the shared memory-bank workflows, then let the task-memory-bank skill handle project resolution, entrypoint reads, qmd retrieval, and markdown updates.

These files are intentionally outside `skills/task-memory-bank/` because they are about authoring and packaging harness integrations, not core skill context.
