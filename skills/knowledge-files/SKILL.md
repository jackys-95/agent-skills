---
name: knowledge-files
description: Author and maintain qmd-backed knowledge files — the write side of the knowledge base. Use when saving approved system documentation, deciding where a fact belongs, splitting dense docs into authoritative per-entity files, adding cross-references, or promoting WIP learning primers into approved knowledge. For retrieval/search use the query-kb skill; for task/episodic state use the task-memory-bank skill.
compatibility: Requires the qmd CLI (`@tobilu/qmd`) with the knowledge/learning collections indexed. Delegates qmd retrieval/reindex mechanics to the qmd skill; retrieval front-end is the query-kb skill.
---

# knowledge-files — Knowledge File Authoring

The **write side** of the knowledge base. The knowledge base has three tiers:

- **knowledge** (`contains: knowledge`) — permanent, approved system documentation. This skill
  writes it.
- **learning** (`contains: learning`) — lower-confidence WIP ramp-up material that graduates into
  knowledge via an explicit promotion step (see [references/promotion.md](references/promotion.md)).
- **tasks** (`contains: tasks`) — episodic task state, owned by the
  [task-memory-bank](../task-memory-bank/SKILL.md) skill.

This skill authors **knowledge** files and promotes **learning** into them. It does not retrieve
(that's [query-kb](../query-kb/SKILL.md)) and does not own task state (that's task-memory-bank).

## What this skill owns vs. delegates

**Owns** — the authoring *domain inputs*: where a fact belongs (classification), how big a file
should be and what shape it takes (the atomic-entity contract), when to create vs. append, the
cross-reference discipline, and the learning → knowledge promotion procedure.

**Delegates** — qmd *mechanics* (query modes, scoping flags, reindex command, CLI vs MCP) to the
**qmd skill**. Invoke `/qmd` for authoritative, version-current syntax. Do not pin qmd commands in
this skill.

## 🎯 PRIMARY RULE: one entity, one authoritative file

Author to the **atomic-entity contract**, not as dense catch-all documents:

- **One entity = one file (an atom).** It changes only when *that* entity's truth changes.
- **Compose, don't duplicate.** Combinations are assembled at retrieval time, or as a *composed
  doc* that holds the relationship and links to atoms — never by copying content into a God-doc.
- **Each fact has exactly one home** (single source of truth). Reference other atoms by `[[link]]`.
- **Cross-references are bidirectional and mandatory** when you create a new file.

The full model (SOLID mapping, file skeletons, sizing heuristics) is in
[references/authoring-principles.md](references/authoring-principles.md). Read it before authoring.

## ⚠️ Critical Rules

- **Never read a collection root as a file** — it's a directory. Use qmd tools to search/inspect.
- **Knowledge files are approved/merged only.** Anything WIP, uncertain, or under active study
  stays in the `learning` tier until promoted. Do not author speculative content as knowledge.
- **Respect scope boundaries** — do not restate content owned by another system's source of truth;
  link to it (see [references/classification.md](references/classification.md)).
- **Reindex after every write or promotion** — a file that isn't indexed can't be retrieved. This
  skill owns the obligation; the mechanic is in /qmd. Note: the task-memory-bank `reindex` script
  does **not** cover knowledge/learning collections — reindex those directly via qmd.

## Workflows

### Save new knowledge
1. **Classify** — Domain vs Technical, name it, tag `domain:`. See
   [references/classification.md](references/classification.md).
2. **Create vs. append** — apply the new-file-vs-append heuristics in
   [references/authoring-principles.md](references/authoring-principles.md).
3. **Write to the contract** — entity-atom skeleton; fill Definition, Boundaries, Relationships.
4. **Cross-reference** — bidirectional links to related atoms.
5. **Reindex** — via /qmd, scoped to the knowledge collection. Verify retrievable.

### Promote learning → knowledge
Follow [references/promotion.md](references/promotion.md): decompose the primer into atoms,
classify/place/write each to the contract, insert cross-refs, record provenance, reindex.

## References

| File | Covers |
|---|---|
| [references/classification.md](references/classification.md) | Domain/Technical placement, naming, `domain:` tag, scope boundaries |
| [references/authoring-principles.md](references/authoring-principles.md) | SOLID/atomic model, file contracts, sizing, create-vs-append |
| [references/promotion.md](references/promotion.md) | learning → knowledge promotion + reindex obligation |

## Related skills

- [query-kb](../query-kb/SKILL.md) — retrieval (read side).
- [task-memory-bank](../task-memory-bank/SKILL.md) — episodic task state.
- qmd skill (`/qmd`) — authoritative qmd mechanics.
