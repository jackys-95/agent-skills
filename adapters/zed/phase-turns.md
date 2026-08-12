<!-- phase-turns -->
## Phase-Scoped Turns

The task-memory-bank workflow defines resume/plan, implement, verify, and memory close-out
checkpoints. In Zed, bind those checkpoints to turn boundaries because diffs, revert windows, and
memory reindexing are all batched per turn:

- End the resume/plan turn after persisting the plan and before editing repository files.
- Keep implementation and verification in subsequent turns, following the workflow's rules for
  when those checkpoints may be combined.
- End the implementation/verification turn before writing memory close-out files.
- Perform memory close-out in its own turn so those writes have a separate diff and settle window.
- End each phase turn with one line naming the next phase, for example:
  `next: implement - reply to continue`.

Completion pressure is not a reason to cross a checkpoint. A clean review boundary takes
precedence over finishing multiple phases in one turn.
<!-- phase-turns -->
