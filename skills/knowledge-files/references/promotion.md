# Promotion: learning → knowledge

How a WIP primer in the `learning` tier graduates into approved `knowledge`. This is a **manual,
doc-guided** step (no script in this MVP). The skill owns the *obligation* to reindex after the
write and review window are settled; it delegates the *mechanic* to the qmd skill.

## Why a promotion step exists

`learning` is lower-confidence, in-progress staging; `knowledge` is approved/merged only. The
approved-vs-WIP boundary is the whole reason they are separate tiers. Promotion is the explicit
act of vetting and restructuring WIP prose into authoritative atoms — it is not a file move.

## Steps

1. **Decompose the primer into atoms.** A learning primer is usually dense (a God-doc). Identify
   the *entities* (nouns) inside it. Each becomes a candidate atom. Relationships between them
   become candidate composed docs only if durable (see
   [authoring-principles.md](authoring-principles.md)).

2. **Classify and place each atom.** Domain vs Technical; name it; tag `domain:`. See
   [classification.md](classification.md). Respect scope boundaries — do not absorb content owned
   by another system; link to it.

3. **Write each atom to the contract.** Use the entity-atom skeleton. Fill `Definition`,
   `Boundaries`, `Key properties`, `Relationships`. The `Definition` is now the single source of
   truth — the learning prose is raw material, not the deliverable.

4. **Insert bidirectional cross-references.** Every new atom links out to related atoms, and each
   related atom links back. Never inline another atom's content (DIP).

5. **Record provenance.** In `Provenance & confidence`, note the source primer and promotion date,
   and mark it vetted. This is how a reader distinguishes a promoted fact from WIP.

6. **Decide the primer's fate.** Either (a) leave the primer in `learning` as study material and
   note it's been superseded by the knowledge atom(s), or (b) trim it to a pointer. Do **not**
   delete study context silently. Default: leave it, add a "promoted to" note.

7. **Settle and reindex so the new file is discoverable.** *This skill owns this obligation* — a
   knowledge file that isn't indexed cannot be retrieved. Wait until the write and editor review
   window are settled. Then let a healthy harness lifecycle integration flush the affected
   collection, or invoke qmd directly for that collection.

## Reindex — obligation here, mechanic in /qmd

Per the skill↔qmd boundary, this doc states *that* you must reindex and *which* collection; it does
**not** pin the command. Invoke the **qmd skill** (`/qmd`) for the current syntax.

Do not reindex while the promotion files are still provisional or revertible in an editor review
window. A healthy harness lifecycle integration may track the changed paths and flush the affected
collection at the next settled boundary. If that integration is absent, disabled, untrusted,
interrupted, or fails, invoke qmd directly after the review window settles.

> ⚠️ Do **not** use the task-memory-bank `memory_bank.py reindex` for knowledge/learning
> collections. That script is scoped to the `mb-*` task collections only — it does **not** cover
> a product's `<product>-knowledge` / `<product>-learning` collections. Reindex those with a
> **collection-scoped qmd call** targeting the collection you just wrote to. Confirm the flag
> spelling via /qmd.

After reindexing, verify the file is retrievable by querying scoped to the knowledge collection
(via query-kb / qmd) before considering the promotion complete.

## Related references

- Placement & naming: [classification.md](classification.md)
- Authoring model & contracts: [authoring-principles.md](authoring-principles.md)
