# Task Memory Bank Quickstart

Use this when setting up or exercising the task memory bank CLI directly.

## Purpose

`task-memory-bank` helps agents keep project context slim, searchable, and resumable across tools. It uses a folder-based memory bank indexed by qmd, with one project folder per repo and deterministic metadata that maps git repos to qmd collections.

## Recommended Shape

```text
task-memory-bank/
  registry.md
  .memory-bank/
    collections.yaml
  projects/
    example_project/
      .memory-bank/
        collection.yaml
      README.md
      active.md
      overviews/
      domains/
      work/
```

## Initialize Project Memory

```bash
python3 skills/task-memory-bank/scripts/memory_bank.py init-project \
  --root ~/memory/task-memory-bank \
  --project example_project \
  --repo ~/work/example-project
```

## Create A Work Item

```bash
python3 skills/task-memory-bank/scripts/memory_bank.py new-work \
  --root ~/memory/task-memory-bank \
  --project example_project \
  --type task \
  --title "Fix saved filter state"
```

## Resolve Current Repo

Resolve the current git repo to its memory project and qmd collection:

```bash
python3 skills/task-memory-bank/scripts/memory_bank.py resolve-project \
  --root ~/memory/task-memory-bank \
  --repo "$(git rev-parse --show-toplevel)" \
  --json
```

The resolver reads `.memory-bank/collections.yaml`, so agents do not need to guess which qmd collection belongs to the current repo.

Each initialized project also gets `projects/<project>/.memory-bank/collection.yaml`. That project-local manifest travels with the collection and can be indexed with the rest of the collection when qmd includes YAML files.

## Check Structure

```bash
python3 skills/task-memory-bank/scripts/memory_bank.py doctor \
  --root ~/memory/task-memory-bank
```
