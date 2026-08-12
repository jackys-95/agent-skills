# Zed + Codex CLI adapter design

**Status:** implemented MVP design.
**Component:** Codex-specific hooks under `adapters/zed/`.
**Tracking:** GitHub #43.

## Goal

Give Codex CLI sessions launched inside Zed the same turn-batched review model
as the existing Zed + Claude Code adapter:

- snapshot each file before its first edit in a turn;
- open one Zed multi-diff when the parent turn stops;
- preserve a per-file revert command after the turn manifest is cleared;
- keep Codex sessions outside Zed unaffected.

The MVP target is structural parity with the shipped Claude Code pairing. It
does not close that adapter's existing blind spot for file writes performed by
shell commands or other opaque mutators.

## Observed Codex contract

The adapter was validated against Codex CLI 0.146.1.322.

- Hook-layer file edits report `tool_name = "apply_patch"`.
- The patch text is `tool_input.command`.
- Add, update, delete, and move paths appear in these headers:
  `*** Add File:`, `*** Update File:`, `*** Delete File:`, and
  `*** Move to:`.
- Headers are raw and unquoted, including paths with spaces, quote characters,
  and non-ASCII characters.
- Relative paths resolve against hook `cwd`; absolute paths are also accepted.
- A move is represented by `Update File` for the old path followed by
  `Move to` for the new path. The move needs a nonempty update hunk.
- A successful `PostToolUse.tool_response` lists each changed file and status.
  Failed patches emit `PreToolUse` but no `PostToolUse`.
- Plain `PreToolUse` stdout is ignored.
  `hookSpecificOutput.additionalContext` is delivered to the model.
- `systemMessage` is UI-facing and is not model context.
- `Stop` requires JSON on stdout. Plain stdout marks the hook failed but does
  not fail the Codex process or discard the completed answer.

The sanitized probe record and reusable capture tool are in
`docs/probes/codex-hook-payload-probe.md` and
`scripts/probes/codex_hook_payload_probe.py`.

## Lifecycle

The pairing uses four registered hooks and one manual revert command.

1. `UserPromptSubmit` clears the parent session's turn manifest. Child prompt
   events carrying `agent_id` are ignored.
2. `PreToolUse` for `apply_patch` parses every path, resolves it against `cwd`,
   and calls the shared core's `seed_if_new()` before mutation.
3. The pre-hook returns concise revert guidance through
   `hookSpecificOutput.additionalContext`.
4. `PostToolUse` parses the same successful patch and calls `mark_touched()`.
   It confirms the queue but is never the discovery boundary.
5. Parent `Stop` calls `close_turn()` and opens one repeatable
   `zed -a --diff` command.

State uses the `codex_zed` namespace, separate from the Claude Code pairing.
The shared implementation remains in `adapters/core/manifest.py` and
`adapters/core/snapshot_revert.py`.

## Patch path handling

`adapters/zed/hooks/_codex_patch.py` is a pure parser. It returns ordered,
deduplicated absolute paths for all recognized headers.

The parser follows the observed `apply_patch` grammar rather than shell path
syntax:

- headers must start at column zero, which avoids mistaking unchanged patch
  body lines such as ` *** Update File: example` for headers;
- quote characters and `~` are literal filename text and are not unquoted or
  expanded;
- absolute paths and `..` traversal are accepted without a tracked-root check.

The last behavior is intentional for the MVP because Codex may edit explicitly
granted external writable roots, including memory-bank files. Codex's sandbox
and approval policy remain the write boundary.

For a move, both paths are seeded:

- old path: existing snapshot, rendered as snapshot versus `/dev/null`;
- new path: `new` base, rendered as `/dev/null` versus the destination.

This also makes revert-all restore the old path and delete the new path.

An add followed by a delete in the same turn is omitted at Stop because both
the turn-start and final states are absent.

## Revert guidance

The hook's additional context is not directly shown in the Zed panel.
`adapters/codex/AGENTS.md` therefore tells Codex to echo each
`reply 'r <file>' to revert` line as standalone user-visible text.

The installer leaves `additionalContextLimit` unset, using Codex's documented
2,500-token default. Larger output spills to disk with a model-visible preview
and saved-file path instead of being silently discarded.

The command:

```text
python3 ~/.codex/hooks/zedcodex/revert_codex_zed_snapshot.py <file>
```

reads the path-keyed pointer created by the shared snapshot core. It does not
read the turn manifest, because the manifest is cleared before the user can
reply.

## Installation

Run:

```bash
python3 adapters/zed/install_codex.py
```

The installer:

- copies runtime files to `~/.codex/hooks/zedcodex/`;
- merges four hook definitions into `~/.codex/hooks.json`;
- installs the tagged ZedCodex block into `~/.codex/AGENTS.md`;
- leaves `~/.codex/config.toml` untouched;
- tells the user to review the exact definitions with `/hooks`.

Codex stores trust against each hook definition's hash. New or changed
definitions remain disabled until reviewed. Project and user hook sources are
additive, so the installer uses the user-level file and does not depend on
project trust.

The hook scripts are guarded by `CODEX_ZED_HOOK=1`. Configure that variable in
Zed's terminal environment; do not put it in the global hook command, or the
adapter would activate in every Codex terminal.

## Deferred work

- Detecting shell redirection, `sed -i`, `mv`, heredocs, and scripts that write
  files.
- Locking concurrent manifest read-modify-write operations.
- tmux edit injection for Codex.
- Cross-session isolation for path-keyed revert pointers.
