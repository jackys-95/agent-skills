---
name: query-kb
description: Retrieve information from the knowledge base — approved knowledge files and WIP learning primers — via qmd. Use whenever answering a question that a stored domain/technical doc, ramp-up primer, or program knowledge could inform. Activate proactively before answering from general knowledge. For task status / implementation history, this skill delegates to the task-memory-bank skill.
---

# query-kb — Knowledge Base Retrieval

The read side of the knowledge base. The knowledge base has two halves:

- **Knowledge files** — permanent, approved system documentation (`contains: knowledge`).
- **Task memory bank** — episodic task state (`contains: tasks`), owned by the
  [task-memory-bank](../task-memory-bank/SKILL.md) skill.

A third tier, **learning** (`contains: learning`), holds lower-confidence WIP ramp-up primers
that graduate into knowledge via an explicit promotion step.

This skill searches **knowledge** and **learning** collections directly, and **delegates task
scope to the task-memory-bank skill**. It never reads tmb's config or duplicates its collection
list — each skill stays sovereign over its own collections.

## What this skill owns vs. delegates

query-kb owns the *knowledge-base domain inputs*: which collections exist and how they're
classified (the registry), how a caller's scope maps to a set of collections, the fan-out
principle, when to delegate to tmb, and how to cite/qualify what comes back.

It does **not** own qmd *mechanics* — exact flags, query modes, CLI vs MCP call shape. Those
belong to the **qmd skill**, which is the maintained source of truth and evolves with qmd. Invoke
`/qmd` (or run `qmd skill show`) for authoritative syntax. Pass qmd the resolved collections and a
search intent; let it choose CLI or MCP and the current flag spellings. This mirrors how
task-memory-bank delegates retrieval mechanics — do not re-pin the interface here.

## ⚠️ Critical Rules

- **Always use qmd tools** (search/retrieve) — never hand-navigate directories.
- **Never read a collection root path as a file** — it's a directory.
- **The knowledge base is authoritative** — check it BEFORE answering from general knowledge.
- **Scope every query to specific collections** (see the scope selector below). An unscoped query
  searches everything and returns a falsely broad result. For the exact scoping flag/parameter,
  defer to the qmd skill.
- **Cross-collection search is min-score fan-out, never a shared top-K.** This is a query-kb design
  choice, not a qmd default: a single top-K across collections starves small collections (e.g. a
  4-doc primer set loses to a 500-doc bank). Scope each collection in and apply a min-score cutoff
  so each is judged on its own merit.

## The Registry

query-kb reads a **local** `registry.yaml` cataloging the knowledge/learning collections it owns,
classifying each by `contains` (knowledge | learning) and `domain` (program/grouping membership
tag). It intentionally omits task collections and physical layout (path/pattern) — those are owned
by tmb and by qmd's `index.yml` respectively.

`registry.yaml` lives at **`${XDG_CONFIG_HOME:-~/.config}/qmd/registry.yaml`** — beside qmd's own `index.yml`, not at the skill root. This is deliberately **harness-neutral**: every harness installs its own skill copy (Claude Code `~/.claude/skills/query-kb/`, Codex `~/.agents/skills/query-kb/`), so a registry at the skill root would be visible to only one of them. qmd is the shared substrate all harnesses call, so one registry beside `index.yml` serves them all. The file is **git-ignored** by nature of living outside the repo — collection names can
encode internal identifiers, so the real registry stays on your machine.

The registry has an **authoring-driven origin**: it is born and grown by the
[knowledge-files](../knowledge-files/SKILL.md) skill, which appends a `contains`/`domain` entry whenever it creates a new knowledge/learning collection (a human `qmd collection add` plus a hand-edited line works too). Nothing seeds it at install time. To bootstrap by hand, the repo ships [`assets/registry.example.yaml`](assets/registry.example.yaml) as a schema reference you can copy and fill in:

```bash
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/qmd"
cp assets/registry.example.yaml "${XDG_CONFIG_HOME:-$HOME/.config}/qmd/registry.yaml"
```

Read the registry to resolve a scope request into a concrete set of collections to search.

**Granularity — collection, not file.** The registry classifies whole collections; it says
nothing about individual files. Two caveats follow:

- `domain:` is a **program/grouping** tag (e.g. `example-program`), used to pick *which collections* to
  fan out over. It is **not** the technical-vs-domain-knowledge axis.
- Technical knowledge files and domain knowledge files can coexist in one `knowledge` collection.
  The registry does not distinguish them — they are separated at retrieval time by content
  relevance (your `intent`/`lex`/`vec` terms), i.e. by search, not by the registry. Splitting them
  into separate retrieval skills or collections is full-#14 work, not this MVP; when needed, add
  them as additional `contains: knowledge` entries (same `domain`) and fan-out picks them up.

## Scope Selector

Map the caller's need to collections before querying:

| Requested scope | Collections queried |
|---|---|
| `knowledge` | every registry entry with `contains: knowledge` |
| `learning` | every registry entry with `contains: learning` |
| `tasks` | **delegate to the task-memory-bank skill** — do not query here |
| `both` / `all` | union of the above, fanned out with a min-score cutoff |

Optionally filter by `domain` first (e.g. "everything for program X" = registry entries with
`domain: X`, plus the matching tmb project via delegation).

When the answer could plausibly live in either half and the caller has not specified, default to
`both`: fan out across knowledge + learning collections, and if the question is about task status,
implementation history, or "what was I doing," delegate the task half to task-memory-bank.

### Delegating task scope

For task status, implementation context, or resume state, hand off to the
[task-memory-bank](../task-memory-bank/SKILL.md) skill — it resolves the current repo to its
`mb-<project>` collection and owns the resume-query shape. query-kb does not enumerate or search
`mb-*` collections itself.

## Retrieval workflow

The shape is always: **search** for candidates → **retrieve** the full source → **answer from
retrieved text**, never from snippets alone. Choose the tool by goal:

- **Content/topic search** — you know *what* you want, not *where*. Author a structured query
  (an `intent` line plus lexical/semantic terms) rather than pasting the user's sentence.
- **Filename-pattern browsing** — you know the *naming convention* and want every match (e.g. all
  primers in a domain directory).
- **Read a known file** — you have a path or docid from a prior result. Paths are
  collection-relative; prepend the collection name, or use the `#docid` (which needs no prefix).

For query modes (`lex`/`vec`/`hyde`), the scoping flag, min-score parameter, and CLI-vs-MCP call
shape, **see the qmd skill** — it is authoritative and current. Pass it the collections from your
scope selection and your search intent.

### Convenience cheatsheet (verify syntax against `/qmd`)

A concrete starting point for a two-collection, min-score-filtered fan-out. Treat the exact flag
spellings as illustrative — the **qmd skill is the source of truth** if they differ:

```bash
qmd query -c <knowledge-collection> -c <learning-collection> --min-score 0.5 \
  $'intent: what am I actually looking for\nlex: exact keywords\nvec: natural-language question'
```

Collection names come from your `registry.yaml` at `~/.config/qmd/registry.yaml`. Scope each collection in explicitly; omitting scope searches everything.

## After Retrieving

- Cite the source doc (collection + path or docid) when you answer, so the user can open it.
- If a `learning` doc is the only hit, flag that it's lower-confidence WIP, not approved knowledge.
- If nothing clears the min-score cutoff, say the KB has no answer rather than inventing one — then
  fall back to general knowledge, clearly labeled as such.

## Quick Reference

| Need | Approach |
|---|---|
| Domain/technical concept | search the `knowledge` collection(s) (add the `learning` one for WIP) |
| "What have I been studying?" | search the `learning` collection(s) |
| Everything for one program | knowledge + learning collections with that `domain` + delegate tasks to tmb |
| Task status / resume state | delegate to [task-memory-bank](../task-memory-bank/SKILL.md) |
| Read a file from a result | retrieve by `<collection>/<path>` or by `#docid` |
| All files of a naming convention | filename-pattern retrieval with a glob |
