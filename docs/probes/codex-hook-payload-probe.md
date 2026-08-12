# Codex hook payload probe

This document records the reusable Codex hook probe pattern and the sanitized
results that informed the Zed + Codex CLI adapter design. The probe is research
tooling, not production adapter behavior.

Production hooks should live under the owning adapter. Probe scripts should stay
under `scripts/probes/` so they do not look like installed runtime hooks.

## Probe script

Use:

```text
scripts/probes/codex_hook_payload_probe.py
```

The probe:

- exits unless `CODEX_HOOK_PROBE` is set;
- reads hook stdin as raw text and JSON when possible;
- records argv, cwd, timestamp, process id, selected redacted environment, and
  parse metadata;
- writes one JSON file per invocation under `/tmp/codex_hook_payloads` by
  default;
- prints status only to stderr.

The stderr-only behavior keeps the capture command from steering Codex. Codex
`Stop` and `SubagentStop` accept structured JSON on stdout; plain text is
invalid for those events.

Override the capture directory with:

```bash
export CODEX_PROBE_DIR=/tmp/my-codex-hook-captures
```

Run the script directly for a smoke test:

```bash
CODEX_HOOK_PROBE=1 \
python3 scripts/probes/codex_hook_payload_probe.py --event Stop \
  <<< '{"hook_event_name":"Stop","example":true}'
```

Do not commit raw captures. They can contain prompts, transcript paths, local
paths, model responses, and environment details. Commit only sanitized summaries
or minimal fixtures.

## Example hook config

Codex hook config uses PascalCase event names and command hook entries:

```toml
[[hooks.SessionStart]]
[[hooks.SessionStart.hooks]]
type = "command"
command = "CODEX_HOOK_PROBE=1 python3 /absolute/path/to/scripts/probes/codex_hook_payload_probe.py --event SessionStart"
timeout = 30
statusMessage = "Probe SessionStart"

[[hooks.UserPromptSubmit]]
[[hooks.UserPromptSubmit.hooks]]
type = "command"
command = "CODEX_HOOK_PROBE=1 python3 /absolute/path/to/scripts/probes/codex_hook_payload_probe.py --event UserPromptSubmit"
timeout = 30
statusMessage = "Probe UserPromptSubmit"

[[hooks.PreToolUse]]
matcher = "*"
[[hooks.PreToolUse.hooks]]
type = "command"
command = "CODEX_HOOK_PROBE=1 python3 /absolute/path/to/scripts/probes/codex_hook_payload_probe.py --event PreToolUse"
timeout = 30
statusMessage = "Probe PreToolUse"

[[hooks.PostToolUse]]
matcher = "*"
[[hooks.PostToolUse.hooks]]
type = "command"
command = "CODEX_HOOK_PROBE=1 python3 /absolute/path/to/scripts/probes/codex_hook_payload_probe.py --event PostToolUse"
timeout = 30
statusMessage = "Probe PostToolUse"

[[hooks.Stop]]
[[hooks.Stop.hooks]]
type = "command"
command = "CODEX_HOOK_PROBE=1 python3 /absolute/path/to/scripts/probes/codex_hook_payload_probe.py --event Stop"
timeout = 30
statusMessage = "Probe Stop"
```

Use `/hooks` in Codex CLI to inspect and trust non-managed hooks. Avoid
`--dangerously-bypass-hook-trust` except for deliberate local experiments.

## Initial results

The Zed + Codex CLI adapter investigation used this probe pattern against Codex
CLI 0.143.0. It captured a no-edit turn and a shell-created file.

Observed lifecycle payloads:

| Event | Fields observed |
|---|---|
| `SessionStart` | `session_id`, `cwd`, `hook_event_name`, `model`, `permission_mode`, `source`, `transcript_path` |
| `UserPromptSubmit` | `session_id`, `turn_id`, `cwd`, `hook_event_name`, `model`, `permission_mode`, `prompt`, `transcript_path` |
| `Stop` | `session_id`, `turn_id`, `cwd`, `hook_event_name`, `model`, `permission_mode`, `stop_hook_active`, `last_assistant_message`, `transcript_path` |
| `PreToolUse` around shell write | `tool_name = "Bash"`, `tool_input.command`, `tool_use_id`, `session_id`, `turn_id` |
| `PostToolUse` around shell write | same tool fields plus `tool_response` |

Shell write example:

```text
tool_name = "Bash"
tool_input.command = "printf ok > codex_probe_target.txt"
```

The observed shell-write payload did not include a canonical
`tool_input.file_path`. That does not prove every Codex write tool lacks file
paths. It proves that any adapter requiring complete file-change coverage cannot
depend only on Claude-style per-file hook payloads.

Design consequence for the Zed + Codex CLI adapter:

- Shell writes cannot be discovered from a canonical file-path field.
- The MVP detects `apply_patch` paths and documents shell-mediated writes as a
  known review gap.

## Round 3 results

These results were observed on Codex CLI 0.146.1.322 unless marked
documentation-derived.

### Hook output

- **Observed:** plain text from `PreToolUse` stdout was ignored. The tool ran,
  and the model reported no injected context.
- **Observed:** JSON
  `hookSpecificOutput.additionalContext` reached the model verbatim after the
  tool call.
- **Observed:** `systemMessage` did not enter model context.
- **Observed:** successful-hook stderr was not model-visible. Exit code 1
  marked the hook failed but still allowed the tool to run; its stderr reason
  was not model-visible.
- **Observed:** plain text from `Stop` marked that hook failed. The completed
  answer remained valid and the Codex process exited 0.
- **Documentation-derived:** `systemMessage` is a UI/event-stream warning;
  `PreToolUse` and `PostToolUse` use nested
  `hookSpecificOutput.additionalContext` for model-visible context; `Stop`
  accepts common structured JSON output and continuation decisions.
- **Documentation-derived:** `additionalContextLimit` is an approximate token
  threshold, not a character limit. The default is 2,500 tokens. Oversized
  context spills to disk and the model receives a head-and-tail preview plus
  the saved-file path; setting the value to `0` disables spilling.

### apply_patch payloads

- **Observed:** hook `tool_name` is exactly `apply_patch`.
- **Observed:** the full freeform patch is `tool_input.command`.
- **Observed:** one successful patch mixed Add, Update, Delete, Move, and paths
  containing spaces, single quotes, double quotes, and non-ASCII characters.
  Header paths were column-zero raw text without shell quoting.
- **Observed:** Move used `*** Update File: old` followed by
  `*** Move to: new`. An empty move hunk failed validation; a context hunk
  containing the unchanged source line succeeded.
- **Observed:** relative headers resolve against hook `cwd`. Starting Codex in
  a subdirectory produced `*** Update File: relative.txt` and a hook `cwd`
  equal to that subdirectory.
- **Observed:** successful `PostToolUse.tool_response` listed one status line
  per file (`A`, `M`, or `D`). Failed patches emitted `PreToolUse` but no
  `PostToolUse`.

Raw captures were deleted after extracting these sanitized findings.

### Hook configuration and trust

- **Observed:** project-local `.codex/hooks.json` was discovered after the
  project trust prompt.
- **Observed:** startup grouped five unreviewed command hooks by event. `/hooks`
  displayed source, matcher, command, timeout, and trust state.
- **Observed:** trust persisted across later Codex processes for the unchanged
  hook definitions.
- **Documentation-derived:** Codex also reads user-level
  `~/.codex/hooks.json` and inline hooks in `~/.codex/config.toml`; matching
  sources are additive. Trust is keyed to the current hook-definition hash, so
  a changed definition requires review again.
