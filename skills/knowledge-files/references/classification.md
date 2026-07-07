# Classification & Naming

Where a knowledge file lives and what it's called. Generalized from a Domain/Technical split that
proved out in production.

## The two-axis model

A knowledge file is placed on **one classification axis** and tagged on **one product axis**.
They are independent — do not conflate them.

### Classification axis: Domain vs Technical (physical placement)

- **`Domain/`** — business processes, real-world concepts, product/user-facing behavior, data
  *meaning* (what a field represents), workflows, policies. Answers "what is this thing and what
  does it mean in the problem space."
- **`Technical/`** — build systems, package/service architecture, code generation, API design,
  development workflows, testing, implementation detail. Answers "how is this built or operated."

A concept that has both a business meaning and an implementation gets **two atoms** — one in each
tree — cross-referenced. Do not merge them into one file; they change for different reasons (SRP).

> Boundary check: if you cannot decide Domain vs Technical, you are probably describing two
> entities. Split first, then place each.

### Product axis: `domain:` tag (logical grouping, NOT placement)

A **product** is the top-level thing a set of collections collectively documents — a product,
service, or initiative you'd scope "everything about X" to. Product membership is a **frontmatter
`domain:` tag**, not a parent folder. This is what query-kb's registry filters on to pick *which
collections* to fan out over.

> ⚠️ The key is spelled `domain:` (for registry-historical reasons), but it is the **product**
> axis — it has nothing to do with the `Domain/` placement folder above. A `Technical/` file and a
> `Domain/` file can both carry the same `domain:` product tag.

The axis is **flat**: one tag per file, no sub-product nesting. A sub-system that lives inside a
product does **not** get its own tag — it carries the parent's `domain:` and is distinguished by
content and placement (e.g. a `Domain/<Sub-System>/` subdirectory), not by the product axis.

## Naming conventions

- **Directories** — `PascalCase-With-Hyphens` (e.g. `Control-Sets/`, `Customer-Agent/`).
- **Files** — `kebab-case`, optionally with a short entity prefix when a subsystem has many files
  (e.g. `svc-`, `api-`; use a prefix only when it aids discovery, else none).
- **One entity per filename** — the filename should name the atom. If the name needs an "and" /
  "vs" / "during", it's either mis-scoped or it's a *composed doc* (see `authoring-principles.md`).

## Scope boundary (what does NOT go in a knowledge file)

- Content owned by a **different system's** source of truth — reference it, don't restate it.
  (Example: when your product sits atop a lower-level platform, platform-owned concepts live
  below your abstraction; your knowledge file links to the platform's sources rather than
  absorbing them.)
- **Episodic / task state** — "what was done on ticket X", resume state, session history. That is
  the task memory bank's job; delegate to the task-memory-bank skill.
- **WIP / unvetted** material — that stays in the `learning` tier until promoted (see
  `promotion.md`). Knowledge files are approved/merged only.

## Related references

- Authoring model, file skeletons, sizing: [authoring-principles.md](authoring-principles.md)
- Learning → knowledge promotion: [promotion.md](promotion.md)
