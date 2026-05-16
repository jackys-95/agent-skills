# Codex App Adapter

Use this appendix only for Codex app installations of the task-memory-bank skill. Keep the base `SKILL.md` harness-neutral; the installer appends this file when building the local Codex app skill.

## Invocation

Prefer deterministic invocation in the Codex app:

```text
$task-memory-bank
/Task Memory Bank or equivalent enabled-skill slash entry
```

If the slash skill entry is unavailable in the current Codex app surface, ask the user to invoke the skill explicitly with `$task-memory-bank`.

## Sandbox Access

The task memory bank is intentionally outside app repos by default, usually at `~/memory/task-memory-bank`. Codex app default permissions commonly use `workspace-write`, which lets Codex edit the current workspace and asks before it goes beyond that boundary.

For a stable local setup, add the repo-specific memory project path as an extra writable root in the repo's `.codex/config.toml`:

```toml
sandbox_mode = "workspace-write"
approval_policy = "on-request"

[sandbox_workspace_write]
writable_roots = [
  "/absolute/path/to/memory/task-memory-bank/projects/<project>",
]
```

Use `/status` in a fresh or reloaded Codex app session to confirm the active writable roots. If persistent access is not configured, request approval for the specific external memory-bank write.

Run qmd maintenance through `scripts/memory_bank.py`, not raw `qmd` commands. In the Codex app, use `memory_bank.py reindex --embed-optional` after external memory writes so qmd update failures remain visible while local embedding/runtime failures can be reported as warnings.

## Mandatory Memory Review Mirror

When the Codex app writes external memory-bank files, it must also create or update a repo-local review mirror. The app review pane is based on the current repository or worktree Git diff; `sandbox_workspace_write.writable_roots` makes external memory files writable, but it does not make those files appear as first-class review-pane changes.

Before writing external memory files:

1. Resolve the repo's memory project path.
2. Snapshot that memory project to a temporary directory.
3. Apply the memory-bank edits.
4. Write a review mirror inside the repo under `.task-memory-review/`.

Example:

```bash
memory_path="/absolute/path/to/memory/task-memory-bank/projects/<project>"
snapshot_dir="$(mktemp -d)/memory-before"

cp -R "$memory_path" "$snapshot_dir"

# Apply memory-bank edits here.

python3 <skill-dir>/scripts/memory_bank.py review-mirror \
  --before "$snapshot_dir" \
  --memory-path "$memory_path" \
  --mirror-dir ".task-memory-review" \
  --clean-empty
```

The generated mirror files are Codex app review aids, not the source of truth. The script maps long memory paths to compact repo-local paths such as `.task-memory-review/memory/TASK-0002/active.md`, stages the before snapshot for changed existing files, and leaves the working tree at the after state so the app review pane can show a normal red/green diff. Keep canonical memory updates in the external memory bank, and update or remove stale mirror artifacts as part of the same task workflow.

Do not write generated review artifacts under `.codex/`; that directory is for Codex project configuration and may be protected from runtime writes.

Symlinks from the repo to the external memory folder are acceptable navigation shortcuts, but they are not a review solution. Git reports the symlink itself, not normal file diffs for the target directory contents.
