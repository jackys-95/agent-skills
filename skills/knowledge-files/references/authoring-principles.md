# Authoring Principles

How to decide *what goes in a file* and *how big a file should be*. The knowledge base is a
dependency graph of concepts, so the forces that shape good software modules shape good knowledge
files. This doc adapts SOLID and composition-over-inheritance to knowledge authoring.

## Core thesis

**One entity = one authoritative file (an "atom"). Combinations are composed, never inherited or
copied.** A dense all-in-one primer is a God-object: high coupling, low cohesion, impossible to
cite precisely, and everything changes at once. Atomize it.

## SOLID, translated

| Principle | Knowledge-file meaning |
|---|---|
| **S — Single Responsibility** | A file documents one entity and changes only when *that entity's* truth changes. Two facts that change for different reasons ⇒ two files. |
| **O — Open/Closed** | Add new composed views and cross-references *around* an atom without editing it. A canonical atom never grows just because a new consumer appears. |
| **L — Liskov Substitution** | Every file *of the same type* obeys the same contract (skeleton + frontmatter), so readers and query-kb can rely on a consistent shape. |
| **I — Interface Segregation** | A reader asking about entity X shouldn't have to load Y and Z. Small focused files ⇒ retrieval scoped to X returns only X. This is the direct cure for dense primers. |
| **D — Dependency Inversion** | Files reference other entities by stable link (`[[name]]`), never by copying content. The link is the abstraction; the target owns the detail. |

## Composition over inheritance (the assembly model)

There is **no** God-doc that "contains everything." Assemble combinations at the cheapest layer
that works:

1. **Retrieval-time** — query-kb fan-out already pulls multiple atoms for one question. Most
   combinations need *no* new file at all. Prefer this.
2. **Composed doc** — create one only when a *relationship* is itself durable and citable
   (e.g. "how service X consumes resource Y during an operation"). It holds the **relationship**,
   and links out to the atoms for their definitions. It must not restate them.
3. **Index / routing doc** — a thin map (glossary) that only points to atoms.

## Single source of truth (DRY)

Each *fact* lives in exactly one file — its home atom. Composed and index docs **reference, never
restate**. A duplicated fact is a future contradiction: the copies drift. "Authoritative" means
*the only place that fact is defined.*

## Sizing — heuristics, not a line count

Target a **contract**, not a size. Apply these tests:

- **Single-intent test** — the file should satisfy one retrieval intent. If you can name two
  distinct questions that each want only half the file, split it.
- **No-conjunction test** — if the accurate title needs "and" / "vs" / "during", it's mis-scoped,
  or it's a composed doc (which is fine — label it as one).
- **Cite-once test** — if answering a question *always* needs this file plus one specific other,
  that pairing is a relationship that may deserve a composed doc.
- **One-reason-to-change** (SRP restated) — if editing entity A would ever force an edit about
  entity B in this file, B doesn't belong here.

An atom is **as small as the smallest thing with a stable, independent identity — and no smaller.**
Don't shatter a cohesive concept into fragments that are never useful alone; that breaks cohesion
just as God-docs break SRP.

## File contracts (LSP)

### Entity atom

```markdown
---
name: <canonical-kebab-name>
aliases: [<other names/acronyms it's searched by>]
contains: knowledge
domain: <product tag, e.g. example-product>
relationships:            # typed links out — see below
  depends-on: [[...]]
  produces: [[...]]
  contained-by: [[...]]
---

# <Canonical Name>

## Definition
<one authoritative paragraph — the single source of truth for what this is>

## Responsibility
<what it is FOR; the role it plays>

## Boundaries
<what it is NOT / what lives elsewhere — the SRP guardrail. Link out to the owner.>

## Key properties
<intrinsic attributes; the durable facts>

## Relationships
<prose + typed [[links]] to other atoms. Reference, never inline their content.>

## Provenance & confidence
<source(s); vetted status; promoted-from which learning primer + date>
```

### Composed doc (a durable relationship)

```markdown
---
name: <participant-a>-<relationship>-<participant-b>
contains: knowledge
domain: <tag>
---

# <A> <relationship> <B>

## Participants
- [[participant-a]]
- [[participant-b]]

## Relationship / interaction
<the connective tissue — the thing that is ONLY true of the combination>

## See also
<links back to each atom for their definitions>
```

## New file vs. append

**Create a new file when:**
1. the existing file is already large / covers many concepts;
2. the topic is a **distinct entity** someone would search for independently;
3. the content answers a self-contained, focused question.

**Append to an existing file when:**
1. the content is a minor clarification/correction;
2. the existing file is the natural home — a direct sub-topic readers always want together;
3. the file isn't already large.

**When you create a new file, cross-reference is mandatory and bidirectional:** add a link in the
related atom's `Relationships` section, and link back from the new atom. This keeps the graph
connected without bloating any single file (DIP + Open/Closed in practice).

## Related references

- Placement & naming: [classification.md](classification.md)
- Promotion from learning: [promotion.md](promotion.md)
