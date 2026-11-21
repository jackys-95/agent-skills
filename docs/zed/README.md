# Zed adapter documentation

These documents describe the Zed side of the Zed + Claude Code and Zed + Codex integrations: how the hooks open diffs, and how Zed itself behaves when they do. For setup and usage, start with the [adapter README](../../adapters/zed/README.md).

| Document | Covers |
|---|---|
| [zed-cli-internals.md](zed-cli-internals.md) | How `zed -a --diff` chooses a workspace and attaches roots, reconstructed from the Zed source and live runs, with the assumptions the hooks depend on and a checklist for new Zed releases. |
| [zed-diff-hook-window-swap-fix.md](zed-diff-hook-window-swap-fix.md) | Why diffs on out-of-project files swapped the window's project, and the `-a` fix. |
| [zed-diff-turn-lifecycle.md](zed-diff-turn-lifecycle.md) | How edits are collected during a turn and opened as one multi-diff when the turn ends. |
| [zed-codex-cli-adapter-design.md](zed-codex-cli-adapter-design.md) | The design of the Codex CLI adapter. |

Zed does not document most of the CLI behavior these hooks rely on, and it changes between releases. Read `zed-cli-internals.md` before changing the hooks' `zed` invocation.
