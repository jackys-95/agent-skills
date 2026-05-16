# Codex Adapter

Prefer Codex skills for reusable agent behavior. For deterministic user invocation, use explicit skill invocation instead of relying on the model to infer the skill from natural language.

OpenAI's Codex skills documentation says Codex can activate a skill either by explicit invocation or by implicit description matching. In CLI/IDE, run `/skills` or type `$` to mention a skill. The Codex app commands documentation also says enabled skills appear in the slash command list, so app users can invoke the task memory bank from `/` when it appears there.

Install local Codex skills under:

```text
~/.agents/skills/<skill-name>/SKILL.md
```

For the Codex app, install a composed skill variant instead of copying the source skill verbatim:

```bash
python3 skills/task-memory-bank/scripts/install.py codex-app --clean
```

The installer copies the skill support files and writes an installed `SKILL.md` from the portable base skill plus `skills/task-memory-bank/adapters/codex-app.md`. Treat `~/.agents/skills` as the local installed-skill target, not the source of truth.

Recommended mapping:

```text
$task-memory-bank for explicit skill invocation in text
/Task Memory Bank or equivalent enabled-skill slash entry for deterministic app invocation
/skills, then task-memory-bank, for CLI/IDE skill selection
```

If the slash skill entry is unavailable in the current Codex surface, use explicit skill mention:

```text
Use $task-memory-bank to resume example_project TASK-0042.
```

## Sandbox Access

The task memory bank is intentionally outside app repos by default, usually at `~/memory/task-memory-bank`. Codex default permissions use `workspace-write`, which lets Codex edit the current workspace and asks before it goes beyond that boundary. That means a default Codex session may read the repo while failing or asking for approval when it tries to update the memory bank.

For a stable local setup, add the memory root as an extra writable root in `~/.codex/config.toml`:

```toml
sandbox_mode = "workspace-write"

[sandbox_workspace_write]
writable_roots = ["~/memory/task-memory-bank"]
```

Then use `/status` to confirm the writable roots for the active session. If a user does not want to grant persistent access, keep the root external and let Codex request approval for specific memory-bank writes.

Run qmd maintenance through `scripts/memory_bank.py`, not raw `qmd` commands. In the Codex app, use `memory_bank.py reindex --embed-optional` after external memory writes so qmd update failures remain visible while local embedding/runtime failures can be reported as warnings.

## Codex App Memory Review

In the Codex app, external memory-bank edits must produce a repo-local review mirror. The app review pane is based on the current repository or worktree Git diff; `sandbox_workspace_write.writable_roots` makes external memory files writable, but it does not make those files appear as first-class review-pane changes.

Before writing external memory files from the Codex app:

1. Resolve the repo's memory project path.
2. Snapshot that memory project to a temporary directory.
3. Apply the memory-bank edits.
4. Write a review mirror inside the repo under `.task-memory-review/`.

Example:

```bash
memory_path="/Users/jacky/memory/task-memory-bank/projects/agent-skills"
snapshot_dir="$(mktemp -d)/agent-skills-memory-before"

cp -R "$memory_path" "$snapshot_dir"

# Apply memory-bank edits here.

python3 skills/task-memory-bank/scripts/memory_bank.py review-mirror \
  --before "$snapshot_dir" \
  --memory-path "$memory_path" \
  --mirror-dir ".task-memory-review" \
  --clean-empty
```

The generated mirror files are not the source of truth; they are Codex-app review aids. The script maps long memory paths to compact repo-local paths such as `.task-memory-review/memory/TASK-0002/active.md`, stages the before snapshot for changed existing files, and leaves the working tree at the after state so the app review pane can show a normal red/green diff. Keep canonical memory updates in the external memory bank, and update or remove stale mirror artifacts as part of the same task workflow.

Do not write generated review artifacts under `.codex/`; that directory is for Codex project configuration and may be protected from runtime writes.

Symlinks from the repo to the external memory folder are acceptable navigation shortcuts, but they are not a review solution. Git reports the symlink itself, not normal file diffs for the target directory contents.

Codex automations can support scheduled or delayed maintenance workflows, such as reminding the current thread to update memory or running a periodic reindex job. Keep automations explicit and user-approved.
