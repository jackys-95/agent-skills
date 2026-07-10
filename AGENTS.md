# agent-skills — contributor guidance

## GitHub hygiene: keep task-memory-bank identifiers local

This repo is developed with a local, private [task-memory-bank](skills/task-memory-bank/SKILL.md)
(tmb). tmb identifiers and terminology are **local metadata** — they live only in the memory bank
on the developer's machine and must never leak into anything GitHub-facing.

**Never put these in a branch name, commit message, PR title/body, or issue:**

- Work-item IDs: `TASK-####`, `EPIC-####`, `STORY-####`, `SPIKE-####`
- tmb-internal file paths (`work/tasks/...`, `active.md`, `history/...`) or the phrase
  "task memory bank" as a reference to a specific local item

**Use public identifiers instead:**

- The GitHub **issue number** (`#14`) and human-readable descriptions
- Branch names: `<issue>-<short-kebab-description>`, e.g. `14-query-kb-retrieval-skill`
- Commit/PR text: describe the change and reference the issue (`#14`), not the local task

Rationale: the memory bank is a private, machine-local planning layer. GitHub is the shared,
public record. A reader of the repo history should never need — or be exposed to — the local
planning vocabulary. One epic often spans several local tasks; naming a branch after the issue
keeps the mapping public-side clean.
