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

## Harness And Meta-Harness Boundary

Put behavior at the lowest layer that can define it once without assuming capabilities that are
not universal:

- The canonical skill owns portable workflow semantics: phase names, checkpoint invariants,
  memory-bank data shape, operation ordering, and fallback behavior.
- A harness adapter owns mechanics native to one agent harness: skill discovery, command wrappers,
  hook payloads, permission setup, and harness-specific reindex automation.
- A meta-harness or pairing adapter owns behavior created by composing a harness with another
  surface: editor review windows, turn batching, and the binding of canonical checkpoints to turn
  boundaries.
- Pairing-specific instructions belong to the pairing adapter and are installed only by its
  installer. A bare harness install must not gain assumptions about an editor or outer host.

For Zed pairings, the canonical task-memory-bank skill defines the resume/plan, implement, verify,
and memory close-out checkpoints. `adapters/zed/phase-turns.md` only binds those checkpoints to
Zed's turn-scoped diff and revert lifecycle. The Claude Code and Codex sources under
`adapters/zed/` deliver pairing-specific instructions through their native global instruction
files.

These files are intentionally outside `skills/task-memory-bank/` because they are about authoring and packaging harness integrations, not core skill context.
