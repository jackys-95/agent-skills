# Task Memory Bank Watcher/Reindexer Plan

This note parks the watcher/reindexer design so the first implementation pass can focus on the task memory bank structure and skills.

## Goal

Keep qmd collections fresh when task memory bank markdown files are created, modified, renamed, or deleted.

The watcher should be a small companion process around qmd, not a second indexer. It should observe filesystem events, coalesce them, run qmd maintenance commands, and then forget the event details.

If qmd gains native watcher support, prefer qmd's native implementation over maintaining a separate memory-bank watcher. Track these upstream PRs before implementing local watching:

- <https://github.com/tobi/qmd/pull/646>
- <https://github.com/tobi/qmd/pull/514>

The local watcher should remain a fallback only if qmd does not provide the needed file create/update/delete behavior for tracked collections.

## Initial Scope

- Watch the task memory bank root, such as `~/memory/task-memory-bank`.
- React to markdown-oriented files: `.md`, `.mdx`, and optionally `.txt`.
- Ignore noisy paths such as `.git`, `node_modules`, `.DS_Store`, temporary files, swap files, and editor backup files.
- Debounce bursts of file events.
- Run `qmd update` quickly after edits settle.
- Run `qmd embed` more slowly after a longer quiet period.
- Serialize qmd commands so `qmd update` and `qmd embed` do not run concurrently.

## Non-Goals

- Do not parse markdown.
- Do not cache document contents.
- Do not maintain checksums.
- Do not keep a full file inventory in memory.
- Do not implement qmd indexing logic outside qmd.
- Do not require the watcher for correctness; memory-bank skills should still be able to run explicit reindex commands after structured writes.

## Collection Config

Use a small declarative config to record tracked qmd collections:

```yaml
collections:
  task-memory-bank:
    path: ~/memory/task-memory-bank
    mode: recursive

  mb-example-project:
    path: ~/memory/task-memory-bank/projects/example_project
    mode: recursive
    context: example_project

  mb-another-project:
    path: ~/memory/task-memory-bank/projects/another-project
    mode: recursive
    context: another-project
```

The first implementation can use this only to find watch roots and affected collection names. If qmd later supports collection-scoped update/embed commands, the same config can drive narrower reindexing.

Each project collection should also carry its own `.memory-bank/collection.yaml` manifest with `path: .`. The root config is for cross-project lookup and watcher routing; the project-local manifest is for collection-local metadata that can travel with the project memory and be indexed when qmd includes YAML files.

## Memory-Efficient Runtime Model

Use one watcher on the smallest common root when collection paths overlap.

Keep only tiny runtime state:

```ts
type DirtyState = {
  dirtyCollections: Set<string>;
  recentPathsSample: string[];
  updateTimer?: NodeJS.Timeout;
  embedTimer?: NodeJS.Timeout;
  running: Promise<void>;
  rerunRequested: boolean;
};
```

`recentPathsSample` should be capped, for example at 20 paths, and used only for logs.

## Event Flow

```text
filesystem event
  -> ignore noise
  -> ensure extension is tracked
  -> map path to affected collection names by prefix
  -> add collection names to dirtyCollections
  -> schedule qmd update after a short quiet period
  -> schedule qmd embed after a longer quiet period
```

Suggested debounce windows:

- `qmd update`: 2 seconds after the last relevant event.
- `qmd embed`: 20-30 seconds after the last relevant event.

This keeps lexical search fresh quickly while avoiding constant embedding during active editing.

## Command Queue

All qmd commands should run through a single queue:

```text
enqueue(update)
enqueue(embed)
```

If new file events arrive while qmd is running, mark `rerunRequested = true`. After the current command finishes, run one additional pass if needed rather than starting overlapping processes.

Initial command behavior:

```bash
qmd update
qmd embed
```

If qmd supports scoped collection maintenance later, prefer affected collections:

```bash
qmd update --collection mb-example-project
qmd embed --collection mb-example-project
```

## CLI Shape

The watcher can live behind a small CLI:

```bash
memory-bank watch
memory-bank reindex
memory-bank doctor
```

`watch` starts the long-running watcher.

`reindex` runs a one-shot `qmd update` and `qmd embed`.

`doctor` checks qmd health, collection config, missing paths, and whether expected qmd collections are registered.

## Skill Integration

Memory-bank skills should treat the watcher as a safety net. Structured write workflows should still explicitly reindex after important changes through the qmd skill when available, or through the CLI fallback:

```bash
qmd update
qmd embed
```

That keeps deterministic agent workflows reliable even when the watcher is not running.

qmd's MCP server is a retrieval integration, not a filesystem watcher. For long-running agent sessions, `qmd mcp --http --daemon` can avoid repeated model loading, but markdown edits still need `qmd update` and `qmd embed` unless qmd adds native watch behavior.

## Implementation Preference

First check whether the installed qmd version has native watch/reindex support. If it does, wire `memory-bank watch` to qmd's native watcher or document the qmd command directly.

Only build a local watcher if qmd still lacks the needed filesystem watch behavior. In that fallback case, use Node with `chokidar`:

- Works well on macOS.
- Handles add/change/unlink events cleanly.
- Can use native filesystem events.
- Avoid polling unless required by the filesystem.

Recommended watcher options:

```js
{
  ignoreInitial: true,
  awaitWriteFinish: {
    stabilityThreshold: 500,
    pollInterval: 100
  }
}
```

Avoid `usePolling: true` by default because it scales worse for large memory banks.

## Deferred Decisions

- Whether qmd PRs <https://github.com/tobi/qmd/pull/646> or <https://github.com/tobi/qmd/pull/514> make this watcher unnecessary.
- Whether the watcher should be installed as a macOS LaunchAgent.
- Whether collection config belongs under `.memory-bank/` or in a skill/plugin config directory.
- Whether embeddings should always run after updates or only when changed files are likely to affect vector search.
- Whether project-specific qmd contexts should be created and updated automatically.
