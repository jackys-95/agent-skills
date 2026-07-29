# Zed diff hook — window-swap fix (`-a`/`--add`)

**Status:** fixed — one-flag change, confirmed live (real usage + concurrent stress) post-restart
**Date:** 2026-07-01
**Tracking:** [jackys-95/agent-skills#22](https://github.com/jackys-95/agent-skills/issues/22)
**Component:** zed-cc adapter hook — `post_edit_open_in_zed.py` (adapter source in `adapters/zed/`)

> **History:** this file replaces an earlier `zed-diff-hook-batching-design.md` whose root-cause
> analysis (a concurrency bug) and fix (a batch-and-flush queue) were **wrong**. The correction is
> recorded below. Keeping the corrected reasoning here on purpose — the misdiagnosis is instructive.

---

## 1. Problem

The zed-cc post-edit hook opens a Zed diff pane after each file edit, via
`subprocess.Popen([zed, "--diff", snapshot, file_path])`. Users reported that editing files —
especially task-memory-bank files — sometimes **swapped the active Zed window's project** to an
unrelated folder, losing their working context.

## 2. Root cause (corrected, black-box, Zed 1.9.0)

`zed --diff` with **no window flag** defers to Zed's internal "active workspace" pointer to decide
which window shows the diff:

- **In-project file** (under the focused window's project root) → Zed reuses that window; the diff
  opens **inline**, correctly. (Verified: plain `zed --diff` on an in-project file never swapped.)
- **Out-of-project file** (not under any suitable open project root — e.g. a task-memory-bank file,
  or a cross-package edit in a multi-repo / Brazil workspace) → Zed has no natural home for it and
  falls back to its active-workspace pointer, **re-rooting whatever window that points at.** That
  is the swap.

The out-of-project case is not rare: it is **every** task-memory-bank write, plus normal
cross-package edits in multi-repo work.

### Two earlier theories, both falsified

The first investigation concluded the trigger was **concurrency** —
N fire-and-forget `zed` processes per multi-file turn coalescing on a common ancestor. A live
single-file edit later swapped the window, which **falsifies concurrency** (one process did it),
and it swapped to an unrelated most-recently-used project, not the diff files' common ancestor,
which **falsifies the ancestor theory**. Those early repros were confounded by an already-dirty
Zed session (see §5).

## 3. Fix

Add **`-a`/`--add`** to the hook's `zed` invocation:

```python
# before
subprocess.Popen([zed, "--diff", snapshot, file_path])
subprocess.Popen([zed, file_path])            # new-file / no-snapshot path
# after
subprocess.Popen([zed, "-a", "--diff", snapshot, file_path])
subprocess.Popen([zed, "-a", file_path])
```

`-a` = *"Add paths to the currently focused workspace instead of opening a new window"*
(`zed --help`). It pins the diff to the active workspace and **preserves its root** — no re-root,
no new sidebar root, diff opens as a tab. In-project behavior is unchanged (it was already correct).

### Why not the alternatives

| Option | Verdict |
|---|---|
| **`-a` / `--add`** (chosen) | ✅ Attaches to the active workspace, preserves its root. Survives concurrent bursts (§4). One-line change. |
| **`-r` / `--reuse`** | ❌ *"Reuse an existing window, replacing its current workspace"* — replacing the workspace **is the bug**. Also **absent from 1.9.0's `--help`** (only in the online docs, which describe a newer build). |
| **`-n` / `--new`** | ➖ Always opens a separate diff window — deterministic and never hijacks a project, but gives the user a second window to manage. Viable fallback if `-a` ever regresses. |
| **`-e` / `--existing`** | ❌ Still swapped in testing. |
| **Batch-and-flush queue** (the abandoned design) | ❌ Solved a concurrency bug that does not exist. Large surface (queue + Stop hook + PreToolUse backstop) for no benefit once the real cause was understood. |
| **Skip diff for out-of-project files** | ❌ Kills the diff pane; and out-of-project edits are common (multi-repo), not an edge case. |

## 4. Validation

Black-box, Zed 1.9.0, from a **clean Zed restart** (see §5 for why the restart matters):

- **In-project** plain `zed --diff` → stayed inline. ✅
- **Out-of-project** `zed -a --diff`, single → landed inline in the CC-host (agent-skills) window. ✅
- **Out-of-project** `zed -a --diff`, real memory-bank write → inline in agent-skills. ✅
- **Concurrent stress:** 20 rounds × 4 simultaneous `zed -a --diff` (80 total) on out-of-project
  files → **0 swaps**, all inline. ✅ (Confirms `-a` needs no serialization/batching.)

## 5. The stale-session caveat (important)

`-a` targets Zed's **active-workspace pointer**, which is *not* the same as the OS-focused window
and is *not* bumped by typing in an integrated terminal pane. Heavy window churn — opening and
closing many projects/windows in one Zed session (exactly what the investigation did) — can leave
that pointer **stuck on a stale window.** In that corrupted state `-a` lands in the wrong window
regardless of what you click, and no CLI flag recovers it because 1.9.0 has **no window-ID target
flag** (the integrated terminal exposes `WINDOWID`, but no CLI option consumes it).

- **Reset:** a full Zed restart (Cmd+Q) clears the pointer. After restart, `-a` behaved correctly
  in every test.
- **Normal usage:** ordinary single-project work does not churn windows enough to trigger the
  drift; it took a deliberate afternoon of open/close testing to corrupt it.
- **Residual (accepted):** if the pointer does drift, or you deliberately work across several Zed
  windows, a diff can land in the wrong one until restart. Documented, not fixable via 1.9.0 CLI.

## 6. Zed CLI reference (installed binary is authoritative)

`zed --version` → `Zed 1.9.0 – /Applications/Zed.app`. From `zed --help`:

> `-a, --add` — Add files to the currently open workspace
> `-n, --new` — Create a new workspace
> `-e, --existing` — Open in existing Zed window
> `--diff <OLD_PATH> <NEW_PATH>` — Pairs of file paths to diff. Can be specified multiple times.

**No `-r/--reuse` and no window-id / per-project target flag.** The online CLI reference
(https://zed.dev/docs/reference/cli) lists `-r/--reuse` and `cli_default_open_behavior`, **neither
present in 1.9.0** — it documents a newer/different build. The *installed* `zed --help` plus live
black-box tests are ground truth for this machine.

Sources (fetched/run 2026-07-01): `zed --help` / `zed --version` on the installed 1.9.0 binary;
Zed CLI reference at zed.dev (newer build — use with caution).

## 7. Follow-ups

1. `adapters/zed/hooks/post_edit_open_in_zed.py` — `-a` added to both invocations. **[done]**
2. `adapters/zed/tests/` (`test_post_hook.sh`, `TEST_PLAN.md`) — assert the `-a` flag.
3. `adapters/zed/README.md`, `adapters/zed/install.py` — update `zed --diff` references to `zed -a --diff`.
4. Post the root-cause correction on issue #22 and close with the fix commit.
