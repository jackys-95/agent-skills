# Zed diff hooks — turn lifecycle and marker reconciliation

**Status:** proposed — spec for the interrupted/failed-turn flush work (and boundary input to the
settled-state reindex review-window protocol)
**Date:** 2026-07-03
**Component:** zed-cc adapter hooks (`adapters/zed/hooks/`) — `pre_edit_zed_snapshot.py`,
`post_edit_open_in_zed.py`, `reset_zed_turn.py`, `stop_flush_zed_diffs.py`, `revert_zed_snapshot.py`

---

## 1. Problem

The turn-batched diff design (PR #25) accumulates per-turn state and assumes two lifecycle events
reconcile it: `Stop` flushes the batch at turn end, `UserPromptSubmit` resets markers at turn
start. Both assumptions have now failed in live use, producing two distinct damage modes:

- **Damage mode A — lost diff batch.** A user interrupt ends the turn without `Stop`; the next
  `UserPromptSubmit` deletes the leftover markers unconditionally, silently discarding the
  interrupted turn's only review surface. Memory-bank files are not in git, so for them the review
  surface is unrecoverable. (Observed 2026-07-03 during the reindex-hooks relocation work: a
  multi-file turn's diff never opened; only the post-interrupt file appeared.)

- **Damage mode B — stale base, wrong revert.** A turn boundary that produces *neither* `Stop`
  *nor* `UserPromptSubmit` leaves the previous turn's seen-marker standing. The next turn's first
  edit then skips snapshotting ("base already captured this turn"), the per-file pointer stays on
  the older turn's base, and a subsequent `r` revert restores a state **two turns old** — silently
  undoing work the user meant to keep. (Observed 2026-07-03: `r` on `statusline-command.sh`
  reverted both the `eft:med` change and the single-line change; `/tmp` held no snapshot of the
  intermediate state.)

Damage mode B is the more severe: A loses a review convenience, B corrupts the revert contract.

## 2. Current state model

Per-turn state lives in `/tmp`, keyed by content-independent hashes of the file path:

| Artifact | Key | Written by | Cleared/consumed by | Meaning |
|---|---|---|---|---|
| seen-marker | (session_id, file) | `PostToolUse` (post-hook) | `Stop` flush; `UserPromptSubmit` reset | "this file's turn-start base is already captured **this turn**" — a boolean latch, checked for existence only |
| snapshot (`cc_pre_<hash>_<ts>`) | file + ms timestamp | `PreToolUse` (first edit of turn) | never deleted | turn-start file content (diff base, revert source) |
| pointer (`cc_pre_ptr_<hash>`) | file | `PreToolUse` (with snapshot) | overwritten by next capture | path of the current base snapshot; read by `Stop` flush and `revert_zed_snapshot.py` |
| gen token (`cc_gen_<hash>`) | file | `Stop` flush | overwritten by next flush | supersession guard for tmux injectors |

The pre-hook's skip rule is the load-bearing line:

```python
if os.path.isfile(seen_marker(session_id, file_path)):
    sys.exit(0)   # keep first snapshot/pointer — correct WITHIN a turn
```

Correct within a turn (N edits diff original→final; revert restores pre-turn state). Wrong across
turns: a stale marker fuses two turns into one virtual turn, freezing the base and the pointer.

## 3. Boundary matrix

Which real turn boundaries produce which reconciliation events (verified against the CC hooks
docs and live behavior, 2026-07-03):

| Turn boundary | `Stop` fires | `UserPromptSubmit` next | State reconciled today? |
|---|---|---|---|
| Normal completion → user prompt | yes | yes | yes (flush + reset) |
| User interrupt → typed prompt | **no** | yes | markers deleted, batch lost (damage A) |
| User interrupt → steering message delivered into the running loop | **no** | **no** | nothing — stale marker survives into next turn (damage B) |
| API error ends turn | no (`StopFailure` instead) | yes | markers deleted, batch lost (damage A) |
| Background subagent finishes (its edits wrote markers) | **no** (`SubagentStop`) | n/a | markers persist until next user prompt |
| Task-notification-woken turn begins | n/a | **no** | stale markers (e.g. a subagent's) survive into the turn (damage B) |
| Interrupt → session quit | no | no (`SessionEnd`) | batch lost, stale state left in /tmp |
| Hard kill → new session | no | no (`SessionStart`) | stale state, cross-session |

Doc-verified facts underpinning the matrix:

- CC has **no interrupt event**; `Stop` fires only on normal completion. `StopFailure` fires on API
  errors; its output is ignored but side effects run.
- Subagent tool calls fire `PreToolUse`/`PostToolUse` with the **parent `session_id`** (plus
  `agent_id`/`agent_type`), so subagent edits write markers into the parent session's namespace.
  Subagent completion fires `SubagentStop`, not `Stop`.
- `UserPromptSubmit` fires only for actual user prompt submission — not for steering messages
  delivered mid-turn, not for subagent activity, not for task-notification wake-ups.
- `prompt_id` (CC ≥ 2.1.196) is present in hook payloads for `PreToolUse`, `PostToolUse`,
  `UserPromptSubmit`, `Stop`: a UUID identifying the user prompt being processed. Absent until the
  first user input.

Consequence: **no set of cleanup events covers every boundary.** Any design whose correctness
depends on cleanup having run is unsound; cleanup can only be an optimization.

## 4. Design

### 4.1 Self-invalidating markers (fixes damage B)

Stamp each seen-marker with the turn identity instead of relying on deletion. The post-hook writes
`{file_path, prompt_id}` into the marker (today it writes only the file path). The pre-hook's skip
rule becomes a comparison:

- marker exists **and** `marker.prompt_id == event.prompt_id` → same turn: keep first snapshot.
- marker absent, unreadable, or `prompt_id` differs → treat as absent: capture a fresh snapshot,
  overwrite the pointer, and overwrite the marker with the current `prompt_id`.

"Invalidated" therefore means *ignored at read time*; the physical stale file is removed by
overwrite during normal operation, never by required cleanup. Fallbacks:

- `prompt_id` missing from the event (pre-first-input, or CC < 2.1.196): fall back to today's
  existence-only behavior. Strictly no worse than current.
- Marker in the old format (bare file path, no prompt_id): treat as stale → capture fresh. This
  makes the format migration self-healing.

### 4.2 Recovery flush (fixes damage A)

Extract a shared flush helper from `stop_flush_zed_diffs.py` (manifest build from markers +
pointers, single `zed -a --diff …` multi-diff open). Then:

- **`UserPromptSubmit`** (`reset_zed_turn.py`): leftover markers ⇒ the previous turn ended
  abnormally. Flush them via the still-intact pointers (prompt-submit hooks run before the new
  turn's first edit, so the read is race-free), print a context line naming the recovered files
  (`UserPromptSubmit` stdout is injected as context), then clear. tmux injectors stay **disabled**
  on recovery paths — stale deltas would race the new turn.
- **`StopFailure`**: register the same flush — timely review at the error boundary; the recovery
  path then handles interrupts only.
- **`SessionEnd`**: leftover check for interrupt-then-quit; flush or at minimum log the dropped
  file list.
- **Stretch — `SessionStart`** cross-session crash-net for hard kills. Markers are session-scoped
  today; this needs a cross-session glob and is deliberately out of the first cut.

Decision in force (2026-07-03): **flush-at-recovery, not carry-over.** Review windows must not
span prompts (per the review-window protocol); an interrupted turn's batch opens at the next
boundary rather than merging into the next turn's batch.

### 4.3 Revert marks dirty (reindex coherence)

`revert_zed_snapshot.py` marks the file's collection dirty after reverting a memory-bank file, so
the qmd index self-corrects at the next settled boundary instead of retaining the reverted
content. (The reindex hooks — `adapters/claude-code/hooks/` — already flush dirty collections at
`UserPromptSubmit`/`SessionEnd`/`SessionStart` and are interrupt-safe by event choice; this closes
the one mutation path they don't see.)

## 5. Interaction with the settled-state reindex protocol

The reindex hooks' settled-state guarantee assumes every flush boundary fires *after* the turn's
review window has closed. The matrix in §3 shows boundaries where the window never opened. The
recovery flush (§4.2) restores the review surface at those boundaries, but ordering between
"recovery diff opens" and "dirty collections reindex" within the same `UserPromptSubmit` remains
the review-window protocol's problem — this spec only commits to not deleting the batch. That
protocol should reuse the marker stamping from §4.1 rather than introduce a second turn-identity
mechanism.

## 6. Open questions

1. Does a steering message delivered into a running loop change `prompt_id` mid-turn? If yes, the
   §4.1 comparison splits a steered turn into two virtual turns — benign for revert (extra
   snapshot, narrower revert), but the diff batch would also split. Needs a live probe.
2. Do subagent hook events carry the parent's `prompt_id` or none? Determines whether a background
   agent's edits stamp markers that the parent's next turn correctly treats as stale.
3. `StopFailure` payload: confirm it carries `session_id` (assumed; its output is ignored but side
   effects run).

## 7. Non-goals

- Carry-over batch semantics (rejected — see §4.2 decision).
- The review-window/settled-state protocol itself (companion work).
- Phase-scoped turn guidance (separate work on checkpoint conventions).
- Broader Zed-adapter UX-mode scoping — this spec is upstream-independent of it.
