# qmd Reference

Use qmd as the retrieval layer for the memory bank. Avoid loading entire project memory trees.

## Collection Naming

Use:

```text
task-memory-bank
mb-<project>
```

Examples:

```text
task-memory-bank
mb-candidate-profile-hub
mb-inference-poc
```

Preserve a human/project context name separately when useful:

```text
candidate_profile_hub
inference-poc
```

## Repo Resolution

When an agent starts inside a git repo, resolve the repo to the qmd collection before searching:

```bash
repo="$(git rev-parse --show-toplevel)"
python3 <skill-dir>/scripts/memory_bank.py resolve-project --root ~/github/task-memory-bank --repo "$repo" --json
```

The command returns:

```json
{
  "project": "candidate_profile_hub",
  "collection": "mb-candidate-profile-hub",
  "memory_path": "/Users/jacky/github/task-memory-bank/projects/candidate_profile_hub",
  "repo": "/Users/jacky/github/candidate-profile-hub",
  "context": "candidate_profile_hub",
  "read_first": [
    "/Users/jacky/github/task-memory-bank/projects/candidate_profile_hub/README.md",
    "/Users/jacky/github/task-memory-bank/projects/candidate_profile_hub/active.md"
  ]
}
```

Use `collection` for qmd searches. Read `read_first` before loading other memory files.

## Setup Commands

```bash
qmd collection add ~/github/task-memory-bank --name task-memory-bank
qmd collection add ~/github/task-memory-bank/projects/candidate_profile_hub --name mb-candidate-profile-hub
qmd embed
```

If using qmd contexts:

```bash
qmd context add candidate_profile_hub ~/github/task-memory-bank/projects/candidate_profile_hub/README.md
```

## Search Pattern

Use lexical search for ids, filenames, and exact terms:

```bash
qmd query -c mb-candidate-profile-hub $'lex: TASK-0042 avatar'
```

Use vector search for conceptual recall:

```bash
qmd query -c mb-candidate-profile-hub $'vec: how does the profile UI represent missing avatar images'
```

Use both when resuming:

```bash
qmd query -c mb-candidate-profile-hub $'lex: TASK-0042 empty avatar\nvec: what context is needed to resume the empty avatar task'
```

## Retrieval Discipline

- Prefer `qmd get` for known files.
- Prefer `qmd multi-get` for a small set of entrypoints.
- Prefer `qmd query` for discovery.
- Keep `-l` line limits low when scanning.
- Load specs/designs only after active context points to them or qmd finds them.

## Reindex

After structured writes:

```bash
qmd update
qmd embed
```

If that fails, keep the markdown writes and report the qmd failure.
