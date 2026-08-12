# Claude Code Adapter

Use generated Claude Code skill wrappers for user-invocable memory workflows. The wrappers are built from adapter source under `adapters/claude-code/` and installed into Claude Code's skills directory.

Do not create a separate Claude-only memory-bank structure or duplicate the workflow rules in generated wrappers. The wrappers exist to provide slash-command ergonomics; the core skill remains the source of truth.

## Source To Install

```text
skills/task-memory-bank/              # canonical workflow source
adapters/claude-code/wrappers.toml    # Claude wrapper manifest
adapters/claude-code/templates/       # wrapper templates
scripts/install_claude_code.py        # installer/generator
~/.claude/skills/                     # default install target
```

Run the installer from the repository root:

```bash
python3 scripts/install_claude_code.py
```

Use `--dry-run` to preview writes or `--target <dir>` to install into another Claude Code skills directory.

## Implemented Wrappers

```text
memory-init-project -> memory.init-project
memory-new-work -> memory.new-work
memory-resume -> memory.resume
memory-update -> memory.update
memory-branch -> memory.branch
memory-handoff -> memory.handoff
memory-reindex -> memory.reindex
memory-doctor -> memory.doctor
```

Each generated wrapper uses:

```yaml
disable-model-invocation: true
```

This keeps side-effecting workflows user-invocable rather than model-triggered.

Example generated wrapper shape:

```md
---
name: memory-resume
description: Resume a qmd-backed task memory bank work item.
disable-model-invocation: true
argument-hint: "[project] [work-id]"
---

Run canonical task-memory-bank workflow `memory.resume` for $ARGUMENTS.

First read and follow `task-memory-bank/SKILL.md`. Resolve the project, read the entrypoint files first, and use qmd only for targeted supporting context. Do not create a Claude-specific memory format.
```

The generated wrappers should stay short. If behavior changes, update `skills/task-memory-bank/SKILL.md`, its references, `memory_bank.py`, or the adapter manifest/template first, then reinstall.

## Reindex Hooks

The adapter owns Claude Code path extraction and native hook registration
(design: `docs/task-memory-bank-reindex-hooks.md`). Shared marker and flush
runtime lives in `adapters/core/`; the installer copies it with the
Claude-specific detector to `~/.claude/hooks/` and registers events in
`~/.claude/settings.json` via `scripts/hook_install.py`.

| Event | Matcher | Script | Action |
|---|---|---|---|
| `PostToolUse` | `Edit\|Write` | `post_edit_mark_dirty.py` | If the edited path is under a tracked collection root (from `${XDG_CONFIG_HOME:-~/.config}/qmd/index.yml`), drop a dirty marker `/tmp/tmb_qmd_dirty_<collection>`. Never reindexes. |
| `UserPromptSubmit` | — | `reindex_dirty_collections.py` | Flush dirty collections detached and silent: one `qmd update`, then one scoped embed per collection. |
| `SessionEnd` | — | `reindex_dirty_collections.py` | Same flush — covers the final turn of a clean session. |
| `SessionStart` | — | `reindex_dirty_collections.py` | Same flush — crash-recovery net for hard-killed sessions; no-ops otherwise. |

This is the adapter's implementation of the skill's settled-state invariant ("reindex only settled
state"): all flush events fire after the turn's diff-review window has closed, so the index never
captures a write the user is about to revert. The installer records the deployed
`memory_bank.py` path in each lifecycle-hook command, including non-default skill targets.
That installed entrypoint is an adapter-owned facade over a preserved canonical
`_memory_bank.py`; it marks successful deterministic writes through the same
shared state module. A direct canonical skill installation remains unmodified.

Side-effect boundary: the hooks only write `/tmp` markers and invoke `memory_bank.py reindex` —
they never modify memory-bank markdown. Manual fallback when the hooks aren't installed:
`memory-reindex` wrapper or `memory_bank.py reindex --collection <name>`.

## Side Effects And Permissions

Memory roots commonly live outside the app repository, for example `~/memory/task-memory-bank`. Claude Code must have filesystem permission to read and write that root before init, update, handoff, or reindex workflows can succeed.

When qmd is unavailable or the reindex hooks are not installed, the skill should still update markdown files and report that `qmd update` and `qmd embed` need to run.

Use hooks/events only for lightweight coordination such as prompting an update or reindex after a session. Do not hide memory-bank mutations inside hooks unless the user has explicitly opted into that behavior.
