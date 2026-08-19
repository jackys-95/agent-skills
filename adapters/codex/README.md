# Codex Adapter

Installs this repository's skills into Codex's local skills directory without packaging them as a Codex plugin.

```bash
python3 scripts/install_codex.py
```

The installer copies the canonical skills from `skills/`, renders short `memory-*` wrapper skills from `wrappers.toml`, and installs/checks the qmd dependency. It also configures the qmd MCP read path, upserts tagged Codex guidance from `AGENTS.md` into `~/.codex/AGENTS.md`, packages the external-root permission helper under `memory-init-project`, `memory-doctor`, and `knowledge-files`, and optionally installs deferred qmd reindex hooks.

For qmd reads, the installer appends the supported STDIO entry below to `$CODEX_HOME/config.toml` only when `mcp_servers.qmd` is absent. It parses the complete TOML before writing, preserves all existing text, and verifies compatible existing entries without rewriting them. An existing enabled streamable-HTTP qmd entry is also preserved; the installer does not start another daemon. A malformed, disabled, filtered, or conflicting qmd entry fails before installation writes begin.

```toml
[mcp_servers.qmd]
command = "qmd"
args = ["mcp"]
```

Start a new Codex session and use `/mcp` to confirm that qmd exposes `query`, `get`, and `multi_get`. Installing the qmd CLI or skill alone does not prove MCP availability. Use `--skip-qmd` to omit the CLI/skill check and MCP setup together.

The generated init and doctor wrappers automatically check external memory-bank write roots. Before each write to an existing knowledge or learning collection, the installed `knowledge-files` skill's Codex guidance automatically runs the same helper with the selected collection name. A synchronized read-only `check` continues without a permission prompt. Missing roots require either a new session with exact `codex --add-dir <path>` grants or explicit approval before persistent `add-roots` setup, followed by a new Codex process plus `/status` verification. See [the Codex adapter permission model](../../docs/task-memory-bank-adapters/codex-adapter.md#external-write-permissions).

The memory wrappers normally run this check themselves; the equivalent manual command is:

```bash
MEMORY_HELPER=~/.agents/skills/memory-doctor/scripts/codex_memory_permissions.py
MEMORY_ROOT=/path/to/task-memory-bank

python3 "$MEMORY_HELPER" check --memory-root "$MEMORY_ROOT"
```

The harness normally checks knowledge permissions automatically. The equivalent manual command uses the collection name, so the user does not need to remember its directory:

```bash
KNOWLEDGE_HELPER=~/.agents/skills/knowledge-files/scripts/codex_memory_permissions.py
COLLECTION=example-product-knowledge

python3 "$KNOWLEDGE_HELPER" check --collection "$COLLECTION"
```

For a collection that does not exist yet, plan permission before creating its root or changing either catalog:

```bash
NEW_COLLECTION=example-product-learning
NEW_ROOT=/exact/planned/example-product/learning

python3 "$KNOWLEDGE_HELPER" plan-new-collection \
  --collection "$NEW_COLLECTION" \
  --expected-root "$NEW_COLLECTION" "$NEW_ROOT" \
  --contains learning \
  --domain example-product
```

The helper reads classification from the shared qmd registry and resolves the physical root from `qmd collection show`. If it reports missing persistent roots and `/status` does not already confirm them for the current process, show the resolved exact child path and offer session-only access with scoped launch grants:

```bash
COLLECTION_ROOT=/exact/child/path/reported/by/check

codex --add-dir "$COLLECTION_ROOT"
```

Repeat `--add-dir` only for roots required by the actual write, then run `/status` in the new session. Session-only access never expands to a related collection. The checker reads persistent configuration, so it cannot verify launch-only flags and must not invalidate an exact session grant already confirmed by `/status`.

For persistent memory-bank setup instead, add the required roots and start a new process:

```bash
python3 "$MEMORY_HELPER" add-roots --memory-root "$MEMORY_ROOT"
codex
```

For persistent knowledge or learning setup, the harness first asks the helper to resolve a deterministic pair:

```bash
python3 "$KNOWLEDGE_HELPER" \
  resolve-knowledge-learning-pair --collection "$COLLECTION"
```

The resolver accepts only one knowledge collection and one learning collection in the same explicit registry domain. It obtains both roots from qmd, orders the result knowledge-first, and prints both collection names and exact paths plus exact path-bound `--collection` / `--expected-root` arguments. The harness relays that result without inferring names or paths.

When resolution succeeds, show both entries in one explicit persistent approval request. On approval, run the exact returned arguments:

```bash
python3 "$KNOWLEDGE_HELPER" add-roots \
  --collection <knowledge-collection> \
  --expected-root <knowledge-collection> <knowledge-path> \
  --collection <learning-collection> \
  --expected-root <learning-collection> <learning-path>
codex
```

Existing collection checks and paired persistent grants require only those exact collection roots. qmd state roots are added separately for memory-bank operations and new-collection setup before registration.

When the counterpart is absent or ambiguous, no pair is formed. The harness falls back to requesting approval for `add-roots --collection <collection> --expected-root <collection> <exact-path-shown-by-check>` for the selected collection only. `add-roots` requires one expected-root binding for every collection, re-resolves each collection immediately before mutation, and stops before creating a backup or changing config if any path differs. Declining either request leaves Codex configuration unchanged.

Run `/status` in that new session before using the external roots.

When `$knowledge-files` creates a collection, it selects the name, exact child path, classification, and domain before any mutation, then runs `plan-new-collection`. The read-only planner requires the name to be absent from both qmd and the shared registry, checks the new root plus qmd state roots needed for registration, and returns exact session-only and path-bound persistent commands when access is missing. Its persistent command includes one existing opposite-classification collection only when the registry has exactly one in the same explicit domain; absent or ambiguous counterparts leave the command scoped to the planned collection. The harness shows the mappings and relays the selected command without inferring names or paths. Declining before a session grant leaves the collection root, both catalogs, and Codex config unchanged.

After the planned roots are effective, the harness creates the root, registers the collection in both catalogs, and runs `check --collection <new-collection> --expected-root <new-collection> <planned-exact-path>`. A path mismatch fails and requires a fresh plan and approval. If the binding is unchanged and only persistent roots already confirmed by `/status` remain missing, the current session grant is authoritative. Collection content is not written before that bound verification. A persistent config change still requires a new Codex process plus `/status` before registration.

Reindex runtime files are installed under `~/.codex/hooks/agent-skills/` and four hooks are merged into `~/.codex/hooks.json`:

- `PostToolUse ^apply_patch$` marks qmd collections touched by direct edits.
- `UserPromptSubmit` reindexes settled changes at the next turn.
- `SessionEnd` covers the final turn of a clean session.
- `SessionStart` on startup/resume/clear recovers markers left by an interrupted session; mid-turn compaction is excluded.

Hook installation requires explicit consent. In a terminal, the installer explains that trusted hooks can run qmd with host user permissions and prompts before writing them. Non-interactive installs must pass `--enable-hooks` or `--skip-hooks`; a dry run with neither flag plans no hook installation. `--skip-hooks` leaves hook registration unchanged rather than uninstalling or disabling existing definitions. Installation consent does not trust the hooks.

When a complete matching managed hook installation exists, the installer composes an adapter-owned entrypoint over the preserved canonical task-memory-bank script so successful deterministic writes emit dirty markers without parsing Codex Bash payloads. A fresh `--skip-hooks` install leaves the canonical script untouched, while a skipped reinstall preserves complete existing hook definitions and runtime files and recomposes their adapter entrypoint without rewriting hook configuration. A partial installation must be repaired with `--enable-hooks`; conflicting managed commands fail safely for manual inspection. Reindexing runs detached and silently; `qmd update` runs once per flush and `qmd embed -c` runs for each dirty collection. Start a new Codex session after installing or updating hooks and use `/hooks` to review and trust the definitions as a separate step. Current Codex builds have been observed to execute trusted hooks outside the spawned-command sandbox, but that placement is not an official guarantee and remains a live regression target.

If no matching hooks are installed, or installed hooks are disabled, untrusted, interrupted, or fail, `memory-reindex` remains the memory-bank fallback: it runs one `qmd update` after writes settle, then requests one-shot approval for each exact `qmd embed -c <collection>` command.

Knowledge and learning files do not route through `memory-reindex`. After their editor review window settles, request one-shot approval for the exact `qmd update` command outside the spawned-command sandbox. After it succeeds, request separate one-shot approval for the exact `qmd embed -c <collection>` command outside that sandbox, then verify retrieval through qmd MCP. The harness invokes both commands; manual execution is only a fallback when native approval is unavailable. Do not approve bare `qmd embed`, broad qmd/Python/shell prefixes, or `danger-full-access`.

For optional turn-batched Zed diff/revert hooks, also run:

```bash
python3 adapters/zed/install_codex.py
```

Both installers merge their own definitions into `~/.codex/hooks.json` and preserve each other's hooks. The base Codex adapter owns only the qmd MCP entry in `config.toml`; the ZedCodex installer leaves that file untouched. Changed hook definitions require another review through `/hooks`.

Use `--dry-run` to preview writes, or `--target <skills-dir>` to select the Codex skills installation root referenced by the reindex hooks. Use `--skip-agents` to leave `~/.codex/AGENTS.md` untouched, `--skip-qmd` to omit qmd installation and MCP setup, `--enable-hooks` to install or repair managed hooks, `--skip-hooks` to preserve current hook registration without installing updates, or `--codex-home <dir>` to select the home containing Codex configuration and managed hook runtime.
