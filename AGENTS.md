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

## Commit and PR shape: short commit, long PR

Keep the commit message short; put the detailed explanation in the PR description.

- **Commit message** — a concise subject line (the what), optionally a line or two of the most
  essential why, and the issue reference (`Closes #NN`). Do not enumerate every file or restate
  the full rationale.
- **PR description** — the long form: problem, root cause, what changed and why, alternatives
  considered, verification, and any follow-ups. This is where a reviewer (and future reader) gets
  the full story.

Rationale: `git log` stays scannable while the reasoning lives in the PR, where it is threaded
with review discussion and easy to find from the issue.
