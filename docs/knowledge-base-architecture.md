# Knowledge Base Architecture

This document is the canonical vocabulary and ownership model for the agent-skills knowledge base. Skill instructions define operational workflows; this document defines the concepts those workflows share.

## Scope

The knowledge base is the umbrella over three content roles:

| Role | Meaning | Authority | Primary owner |
|---|---|---|---|
| `knowledge` | Durable system documentation that has been reviewed and accepted | Authoritative within its stated scope | `knowledge-files` |
| `learning` | Material still being studied, evaluated, or reworked | Lower-confidence and explicitly provisional | `knowledge-files` |
| `tasks` | Episodic implementation state, decisions, history, and resume context | Authoritative for the tracked work, not for durable system facts | `task-memory-bank` |

Use **knowledge** only for the authoritative role. Use **knowledge base** for the three-role umbrella. When discussing the two collections handled directly by query-kb, say **knowledge and learning collections** rather than using knowledge as shorthand for both.

The `query-kb` skill retrieves knowledge and learning directly and delegates task retrieval to `task-memory-bank`. The `knowledge-files` skill authors knowledge and manages promotion from learning. The `task-memory-bank` skill owns episodic task state.

## Knowledge And Learning

Learning exists to protect the authority boundary around knowledge. Material that is incomplete, unverified, actively studied, or not yet shaped as durable documentation belongs in learning. It must not become authoritative merely because it was indexed.

Promotion is an explicit authoring operation, not a file move or confidence-label toggle. The author vets the source material, decomposes it into durable entities, places each fact in one authoritative home, adds cross-references and provenance, settles the edits, and verifies retrieval. The detailed procedure remains in [knowledge-files promotion guidance](../skills/knowledge-files/references/promotion.md).

Knowledge and learning are collection roles. They are independent of the `Domain/` versus `Technical/` file-placement axis inside a collection. A knowledge collection may contain both domain and technical files while remaining entirely `contains: knowledge`.

## Collection Vocabulary

A **qmd collection** is a named qmd catalog entry associated with a physical filesystem path and indexing pattern.

A **collection name** is the stable identifier passed to qmd and used as the key in skill-owned catalogs.

A **collection path** is the physical directory reported by qmd for a registered collection. Call it a path in shared code and documentation. At a harness boundary, call it a sandbox write path or another mechanism-specific access path.

A **knowledge-base registry entry** classifies one qmd collection as `knowledge` or `learning` and associates it with a domain. It does not own the collection's physical path.

A **domain** is a product, service, program, or initiative grouping used to select collections for retrieval fan-out. It is not a directory-placement class and does not imply a one-to-one knowledge/learning pair.

A domain may contain zero or more knowledge collections and zero or more learning collections. Consumers must preserve that cardinality. An adapter may identify a same-domain opposite-role candidate for a specific operation, but uniqueness is an operation precondition, not a Core knowledge-base invariant.

## Ownership And Sources Of Truth

The catalogs are intentionally split by owner:

| Source | Owner | Contains | Excludes |
|---|---|---|---|
| `${XDG_CONFIG_HOME:-~/.config}/qmd/index.yml` | qmd | Every qmd collection's physical path and indexing pattern | Knowledge-base role and task routing metadata |
| `${XDG_CONFIG_HOME:-~/.config}/qmd/registry.yaml` | `query-kb` | Knowledge and learning collection names, `contains`, and `domain` | Physical paths, patterns, and task collections |
| `<bank>/.memory-bank/collections.yaml` | `task-memory-bank` | TMB project collections and routing metadata such as path, project, repos, description, domain, and context | Knowledge and learning collections |

The split prevents one skill from cataloging another skill's collections. It also avoids duplicating knowledge and learning paths outside qmd, where an out-of-band `qmd collection` change would otherwise create two competing path authorities.

TMB's catalog intentionally includes project paths because TMB owns project creation, deterministic project routing, doctor checks, and qmd registration for those projects. This asymmetry is deliberate: the two YAML files serve different workflows and are not alternate schemas for one shared registry.

## Knowledge-Base Registry

The knowledge-base registry is collection-keyed:

```yaml
collections:
  example-knowledge:
    contains: knowledge
    domain: example
  example-learning:
    contains: learning
    domain: example
```

Collection-keyed storage supports direct lookup when a workflow starts with a selected collection name. Consumers may build derived indexes such as `by_name` and `by_domain_and_role` in memory for efficient lookup in either direction.

The schema permits multiple entries with the same `domain` and `contains` value. Do not reject those entries as duplicates and do not persist a separate pair mapping. Retrieval fans out across every selected collection; operation-specific code must handle zero, one, or many candidates explicitly.

## Registration And Consistency

Registering a knowledge or learning collection updates two independent sources:

1. qmd's catalog records the collection name, physical path, and pattern.
2. The knowledge-base registry records the same name with its role and domain.

Registering a TMB project collection updates the bank's `collections.yaml` and qmd's catalog instead. Query-kb does not read or duplicate the TMB catalog.

Healthy state requires the skill-owned entry and qmd entry needed by a workflow to agree on collection identity. A missing entry, unknown role, absent qmd collection, blank path, or changed path must be reported rather than repaired by inference. User-guided repair is appropriate after a consumer fails closed because out-of-band qmd or filesystem changes may reflect intent that the skill cannot determine.

## Retrieval And Authoring Boundaries

`query-kb` owns knowledge-base retrieval inputs: role and domain scoping, collection selection, fan-out, confidence signaling, and delegation of task scope. It delegates qmd command syntax and retrieval mechanics to the qmd skill.

`knowledge-files` owns authoring inputs: placement, file shape, source-of-truth boundaries, learning-to-knowledge promotion, and registration of new knowledge or learning collections. It delegates qmd mechanics to the qmd skill and adapter-specific access mechanics to the active harness adapter.

`task-memory-bank` owns project and work-item structure, task collection registration, deterministic routing, resume context, and episodic history. It does not enumerate knowledge or learning collections.

## Adapter Policy Boundary

Harness adapters may enforce constraints required by their execution environment without changing the Core taxonomy.

For example, the Codex adapter may ask for one access decision covering a selected collection and one same-domain opposite-role collection when exactly one candidate exists. That is a conservative sandbox-path approval policy. It does not establish that every domain has exactly one knowledge collection and one learning collection.

Adapter code may resolve collection paths through qmd and bind approval to those exact paths. It must not add paths to the knowledge-base registry, broaden grants to a shared parent, invent a collection relationship, or reinterpret `domain` as a pairing key.

## Naming Guidance

Names should expose both ownership and role:

- Use **knowledge-base registry**, not qmd registry, for `registry.yaml`.
- Use **qmd catalog** or **qmd index** for `index.yml`.
- Use **TMB collection catalog** for `.memory-bank/collections.yaml`.
- Use **knowledge-base registry entry** for knowledge or learning classification metadata.
- Use **collection path** for qmd's physical directory.
- Use **sandbox write path** at the Codex access boundary; reserve `writable_roots` and `workspace_roots` for literal configuration fields.
- Use **same-domain counterpart candidate** only while describing an operation that seeks the opposite role.
- Use **approved collection-path mapping** for an access decision bound to a collection name and exact path.

Persisted filenames and schema fields remain unchanged. Precision comes from contextual names in code and prose, not from adapter-local migrations of Core user state.
