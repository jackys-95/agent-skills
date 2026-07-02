# Zed diff hook — batch-and-flush design

**Status:** design complete (both open risks closed by experiment)
**Date:** 2026-07-01
**Tracking:** [jackys-95/agent-skills#22](https://github.com/jackys-95/agent-skills/issues/22)
**Component:** zed-cc adapter hooks — `pre_edit_zed_snapshot.py`, `post_edit_open_in_zed.py`
(adapter source in `adapters/zed/`)

---

## 1. Problem

The zed-cc post-edit hook opens a Zed diff pane after each file edit. It fires **one
fire-and-forget `zed --diff` process per file write** (`post_edit_open_in_zed.py:55-66`,
`subprocess.Popen`). When Claude Code writes N files in a single turn, that produces N
near-simultaneous `zed` processes.

**Observed failure:** when those files share a common ancestor directory, Zed coalesces the
concurrent invocations into a single workspace rooted at that ancestor and **swaps the current
window's project** to it. Editing several memory-bank files sharing a `tasks/` ancestor
swapped the active window away from the `agent-skills` project to the `tasks/` folder.

### Root cause (proven, black-box, Zed 1.9.0)

The trigger is **concurrency**, not the number of diffs. Reproduced deterministically:

- 3 **concurrent** `zed --diff` on files under `/tmp/zedtest/sub/` → active project swapped to
  `sub/` (the common ancestor). Matches the live repro.
- 1 **single** `zed` process carrying 3 chained `--diff` pairs on the same files → **no swap,
  all 3 diffs visible.** (Validated live: window stayed put, all diffs shown.)
- Single / sequential opens never coalesce — which is why earlier sequential-only testing
  wrongly cleared the hook.

### Constraints

- **The visual diff pane must be preserved.** "Skip out-of-project files" (dropping the pane)
  is rejected by the user.
- **No CLI flag fixes it.** `-e/--existing` still swapped; `-a/--add` opened in the wrong
  window under a multi-window setup. Zed 1.9.0's CLI has no per-window / per-project target
  flag (see §6). So the fix must change *how* the hook invokes Zed, not *which flag* it passes.

### Reduction

Because a single `zed` process with chained `--diff` pairs is proven safe, the entire fix
reduces to: **collapse a turn's N writes into one `zed` process.**

---

## 2. Proposed design — batch-and-flush with a stale backstop

The unit of batching is **the Claude Code turn**. Per-tool-call writes are enqueued, then
flushed once per turn as a single `zed` process.

| Hook | Behavior |
|---|---|
| **PreToolUse** (`Edit`\|`Write`) | (1) **Flush-if-stale:** if a queue file from a *prior* turn exists, drain it into one chained `zed` call first (backstop for interrupted turns — §4). (2) Snapshot the file as today. |
| **PostToolUse** (`Edit`\|`Write`) | **Stop calling `zed`.** Append one record `snapshot⇥file_path` to a session-scoped queue file. |
| **Stop** (new) | Drain the queue → build one `zed --diff s1 f1 --diff s2 f2 …` → fire it (single process) → clear the queue → `activate` Zed + run the tmux injector per file. |

### Why this shape

- **One flush = one `zed` process = zero possible burst, by construction.** No timers, no
  flock, no debounce daemon. The design *removes* the concurrency rather than trying to
  out-race it.
- The turn boundary is the correct, exact batch unit — `Stop` fires once when Claude finishes
  responding.

---

## 3. Design alternatives considered

| Option | Verdict |
|---|---|
| **Flags** (`-e`, `-a`) | ❌ Falsified — still swaps / wrong window. No per-window flag exists. |
| **Scope-skip** out-of-project files | ❌ Kills the diff pane. Rejected requirement. |
| **A1 — Stop-hook flush** (chosen core) | ✅ Exact batching, no burst by construction. Needs a backstop for interrupts (§4). |
| **A2 — debounce daemon** (PostToolUse enqueues, flock winner sleeps ~400ms then flushes) | ➖ Survives interrupt without a Stop hook, but reintroduces timing heuristics + flock races — the exact concurrency class we are removing. Fallback only. |
| **C — collapse to a single "open newest diff"** | ❌ Loses per-file visibility (partially violates the pane requirement). |
| **D — snapshot always, open lazily on request** | ➖ Keeps the pane but makes it opt-in — a UX regression. |

Chosen: **A1 + a PreToolUse flush-if-stale backstop** (§4), which keeps the burst
*structurally* impossible on the normal path and only defers (never drops) diffs on interrupt.

---

## 4. Interrupt handling — the risk, and why the backstop is a PreToolUse flush

`Stop` fires on clean turn end but **not** on user interrupt. Under plain A1, an interrupted
turn would orphan the queue: those diffs never open, and would wrongly flush at the *next*
turn's `Stop` against stale snapshots. This is a correctness hole, so A1-as-is is rejected.

The backstop cannot be another turn-lifecycle hook, because neither `Stop` nor `SessionEnd`
fires on interrupt (see §5, verified by probe and by docs). So the backstop is
**`PreToolUse` flush-if-stale**: at the top of the next action's PreToolUse, if a queue file
from a prior turn exists (detected by a turn/session marker), flush it **first** — against the
correct original snapshots — before snapshotting the new write. On a normal turn the queue is
already empty (Stop drained it), so this is a no-op.

| Scenario | Outcome |
|---|---|
| Normal turn | `Stop` flushes → one chained `zed`, no swap. ✅ |
| Interrupted turn | Queue orphaned, but next `PreToolUse` flushes it → diffs appear (deferred), correct snapshots. ✅ |
| Any case | Single `zed` process → **never a burst.** ✅ |

**Residual (accepted):** interrupt-then-never-edit-again leaves diffs pending until the next
edit. An optional `SessionStart` flush (`source` ∈ `startup`/`resume`) mops these up next
session.

---

## 5. Evidence — hook lifecycle probe

A throwaway hook logging `hook_event_name` + timestamp was registered on `Stop` and
`SessionEnd`, then exercised in this session (probe + log removed after):

- **Clean turn end → `Stop` fired** (observed twice: 17:53:38, 17:54:36). ✅
- **User interrupt (Esc mid-tool-call) → no `Stop`, no `SessionEnd`.** ❌

This matches the documented semantics:

- `Stop` — *"When Claude finishes responding."* Interrupt is not "finishing," and is not
  listed as a trigger.
- `SessionEnd` triggers are `clear`, `resume`, `logout`, `prompt_input_exit`,
  `bypass_permissions_disabled`, `other` — **interrupt is not among them.**
- `SessionStart` fires on `startup`, `resume`, `clear`, `compact` — usable as the mop-up
  backstop for the residual case.

Source: Claude Code hooks reference, https://code.claude.com/docs/en/hooks (fetched
2026-07-01).

---

## 6. Evidence — Zed CLI (installed binary is authoritative)

`zed --version` → `Zed 1.9.0 – /Applications/Zed.app`. From `zed --help` (full form) on this
binary:

> `--diff <OLD_PATH> <NEW_PATH>` — "Pairs of file paths to diff. **Can be specified multiple
> times.** When directories are provided, recurses into them and shows all changed files in a
> single multi-diff view"

> Options: `-w/--wait`, `-a/--add`, `-n/--new`, `-e/--existing`. **No `-r/--reuse`, no
> window-id / per-project target flag.**

Two consequences:

1. **The chained-`--diff` form the fix depends on is documented** ("can be specified multiple
   times") — a supported API, not a hidden trick. (Corrects an earlier note that called it
   hidden; that was based on the short `-h`, which omits it.)
2. **The online docs describe a different Zed.** zed.dev lists `-r/--reuse` and a
   `cli_default_open_behavior` setting, **neither present in 1.9.0's `--help`**. Therefore the
   *installed* `zed --help` and live black-box tests — not the online docs — are ground truth
   for this machine's behavior.

The failure mode itself — concurrent invocations coalescing on a common ancestor and swapping
the window's project — is **undocumented** in both `zed --help` and the online docs, consistent
with it being a Zed bug provoked by the hook's misuse of the CLI (N concurrent processes
instead of one documented chained invocation).

Sources (fetched/run 2026-07-01):
- `zed --help`, `zed --version` on the installed 1.9.0 binary (authoritative).
- Zed CLI reference, https://zed.dev/docs/reference/cli (describes a newer/different build —
  use with caution).

---

## 7. Implementation notes (for the follow-on task)

- **Queue file:** session-scoped path, e.g. `/tmp/cc_zed_queue_<session_id>`; each line
  `snapshot⇥file_path`. "Stale" = queue exists carrying a turn/session marker older than the
  current turn.
- **Same file edited twice in a turn:** dedupe by `file_path`, keep the **earliest** snapshot
  (true pre-turn state) and diff against final on-disk content.
- **New files (no snapshot):** today they get a plain `zed <path>` open. Fold them into the
  *same* chained invocation (plain path arg, or diff-vs-empty) — otherwise a new-file + edit in
  one turn still spawns a second concurrent process and re-triggers the bug.
- **Self-healing:** flush always drains the whole queue; a missed flush clears on the next one.
- **Preserve existing behavior:** keep the `CC_ZED_HOOK` guard, the `resolve_zed()` fallback to
  the bundled CLI, the `osascript … activate`, and the tmux injector — only the *invocation
  shape* (one batched process) and the *trigger point* (Stop/flush-if-stale, not PostToolUse)
  change.

---

## 8. Status & next steps

Both open risks are closed by experiment: the single-chained-`zed` mechanism (validated live —
no swap, all diffs shown) and the interrupt/`Stop` behavior (probed + doc-confirmed). The design
is ready to split into an implementation task under `adapters/zed/`:

1. Add the queue writer to `post_edit_open_in_zed.py` (enqueue instead of `Popen zed`).
2. Add flush-if-stale to `pre_edit_zed_snapshot.py`.
3. Add the `Stop` flush hook (new script + `settings.json` registration).
4. Optional: `SessionStart` mop-up for the interrupt-then-quit residual.
