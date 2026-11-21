# Zed CLI diff routing: how `zed -a --diff` chooses a workspace

This document records how the Zed CLI and editor decide where a `--diff` request opens and which folders it attaches to a workspace, and how the Zed adapter's end-of-turn hooks depend on that behavior. Zed does not document most of these rules, so they were reconstructed from the Zed source and confirmed with live runs. Maintainers of the adapter should read it when a Zed release changes where diffs open, and anyone who changes the hooks' `zed` invocation should check it first.

The findings apply to Zed 1.29.x on macOS. The source references point at the `v1.29.2` tag (commit `2de9e435a5d98657f35c260b5f4dd0979df659e6`), which is the version the live runs used. Other versions may behave differently, and the last section lists what to re-check after an update.

## Summary

A `zed -a --diff` call has two independent effects: it picks a workspace to show the diff in, and it may attach folders to that workspace as roots. Which paths take part in picking the workspace depends on whether a Zed window is currently active. While one is, Zed discards the CLI's working directory for a diff-only request and shows the diff in whichever workspace has focus, regardless of which project the calling agent belongs to. When no Zed window is active, Zed keeps the working directory, matches it to an open project, and attaches it as a root if nothing matches.

The adapter's hooks therefore add the originating project directory to every call, as the process working directory and as a positional path placed after all `--diff` pairs. That path matches the project's workspace even while another project is focused. The ordering is required, because the CLI treats every argument after the first positional path as another path.

## How Zed handles the request

### Selecting the matching mode

`--add` (`-a`) maps to `OpenBehavior::Add`, which Zed turns into `WorkspaceMatching::MatchSubdirectory` ([open_listener.rs:825-829](https://github.com/zed-industries/zed/blob/2de9e435a5d98657f35c260b5f4dd0979df659e6/crates/zed/src/zed/open_listener.rs#L825-L829)). The other open behaviors map to no matching, subpath matching, or exact matching. Matching a subdirectory means a requested path that lies inside an existing worktree counts as a match for that worktree's workspace.

### Which paths take part in matching

The CLI forwards its own working directory with the request, and `open_local_workspace` ([open_listener.rs:964](https://github.com/zed-industries/zed/blob/2de9e435a5d98657f35c260b5f4dd0979df659e6/crates/zed/src/zed/open_listener.rs#L964)) decides whether to use it. A request is diff-only when it carries at least one `--diff` pair and no positional paths (`user_provided_paths` is false, [open_listener.rs:974](https://github.com/zed-industries/zed/blob/2de9e435a5d98657f35c260b5f4dd0979df659e6/crates/zed/src/zed/open_listener.rs#L974)). For a diff-only request, Zed appends the working directory to the paths used for matching, unless the matching mode is `MatchSubdirectory` and a local Zed window is the active window ([open_listener.rs:976-996](https://github.com/zed-industries/zed/blob/2de9e435a5d98657f35c260b5f4dd0979df659e6/crates/zed/src/zed/open_listener.rs#L976-L996)). The source comment reads, "Avoid adding cwd as a root to the focused window with `--add`. Without a focused local window, retain cwd for workspace matching."

With a positional path present, none of this applies: the request is not diff-only, the working directory is ignored, and the positional paths alone take part in matching.

### Choosing the workspace

`find_existing_workspace` ([workspace.rs:11296](https://github.com/zed-industries/zed/blob/2de9e435a5d98657f35c260b5f4dd0979df659e6/crates/workspace/src/workspace.rs#L11296)) scores each open workspace by how its worktrees cover the requested paths, and breaks ties in favor of the active window and then each window's active workspace. When nothing matches and the mode is `MatchSubdirectory`, it falls back to `preferred_workspace_target` ([workspace.rs:11252](https://github.com/zed-industries/zed/blob/2de9e435a5d98657f35c260b5f4dd0979df659e6/crates/workspace/src/workspace.rs#L11252); the call is at [workspace.rs:11355-11357](https://github.com/zed-industries/zed/blob/2de9e435a5d98657f35c260b5f4dd0979df659e6/crates/workspace/src/workspace.rs#L11355-L11357)), which returns the focused window's active workspace. An empty path list therefore always ends at the focused workspace. Both outcomes carry `OpenVisible::All`, so any path opened through this target becomes a visible root.

### What gets attached to the workspace

Positional paths, including the working directory when Zed appends it, go through `workspace::open_paths` ([open_listener.rs:505](https://github.com/zed-industries/zed/blob/2de9e435a5d98657f35c260b5f4dd0979df659e6/crates/zed/src/zed/open_listener.rs#L505)), which attaches a visible root for any path outside the existing worktrees. The `--diff` operands take a different route. After the workspace is chosen, each pair opens as a diff view, either `FileDiffView::open` ([open_listener.rs:564](https://github.com/zed-industries/zed/blob/2de9e435a5d98657f35c260b5f4dd0979df659e6/crates/zed/src/zed/open_listener.rs#L564)) or, for directory or multi-diff mode, `MultiDiffView::open` ([open_listener.rs:522](https://github.com/zed-industries/zed/blob/2de9e435a5d98657f35c260b5f4dd0979df659e6/crates/zed/src/zed/open_listener.rs#L522)). `FileDiffView` loads its files with `project.open_local_buffer` ([file_diff_view.rs:56](https://github.com/zed-industries/zed/blob/2de9e435a5d98657f35c260b5f4dd0979df659e6/crates/git_ui_core/src/file_diff_view.rs#L56) and [file_diff_view.rs:59](https://github.com/zed-industries/zed/blob/2de9e435a5d98657f35c260b5f4dd0979df659e6/crates/git_ui_core/src/file_diff_view.rs#L59)), so operands outside the project open as buffers without becoming sidebar roots.

### The argument ordering rule

The CLI declares its positional `paths` argument with `trailing_var_arg = true` ([main.rs:101](https://github.com/zed-industries/zed/blob/2de9e435a5d98657f35c260b5f4dd0979df659e6/crates/cli/src/main.rs#L101)), and `--diff` takes exactly two values per occurrence ([main.rs:139-140](https://github.com/zed-industries/zed/blob/2de9e435a5d98657f35c260b5f4dd0979df659e6/crates/cli/src/main.rs#L139-L140)). Once the first positional path appears, the parser reads every later argument as a path, including a following `--diff`. A comment in the CLI source says so directly: "Positional paths consume all following arguments, so launcher options must precede them" ([main.rs:996](https://github.com/zed-industries/zed/blob/2de9e435a5d98657f35c260b5f4dd0979df659e6/crates/cli/src/main.rs#L996)). The user documentation for `--add` ([cli.md:72-76](https://github.com/zed-industries/zed/blob/2de9e435a5d98657f35c260b5f4dd0979df659e6/docs/src/reference/cli.md#L72-L76)) and `--diff` does not mention the ordering rule.

## Behavior by situation

| Zed state | Positional path | Result |
|---|---|---|
| A local window is active | none | The working directory is dropped. The diff opens in the focused window's active workspace, and no root is added. |
| A local window is active | an open project root or a directory inside one, placed after every `--diff` pair | The path matches that project's workspace, so the diff opens there even while another project is focused. No root is added. |
| No window is active | none | The working directory is kept. A working directory inside an open project routes the diff there. One that matches no project falls back to the preferred workspace and is attached to it as a root. |
| Any | a path placed before a `--diff` | Zed reads `--diff` and its operands as paths and opens them as plain files. No diff opens, and operands outside the project are attached as roots. |

## Evidence

The live runs used Zed 1.29.2 on macOS with two projects open in one window. Unless noted, the diff operands were temporary files outside both projects, and stdio was detached to match how the hooks spawn `zed`. Each case was run once.

| Run | Launched from | Zed active | Command shape | Result |
|---|---|---|---|---|
| B | external terminal, cwd in the first project | no | `zed -a --diff a b` | Opened in the first project; no new root. |
| D | external terminal, cwd in a subdirectory of the first project | no | same | Opened in the first project; no new root. |
| control | external terminal, cwd `/private/tmp` | no | same | Followed focus to the second project and attached `/private/tmp` as a root. |
| E | external terminal, cwd in the first project; target was a file in a memory-bank folder | no | `zed -a --diff a <file>` | Opened in the first project with no memory-bank root, whichever project was focused. |
| F | terminal pane inside Zed | yes | `zed -a --diff a b` | Opened in the focused second project; no new root. |
| G | terminal pane inside Zed | yes | `zed -a <project> --diff a b --diff c d` | Routed to the first project, but the four files opened as plain files and were attached as roots, and a tab named `--diff` appeared. |
| H | terminal pane inside Zed | yes | `zed -a --diff a b --diff c d <project>` | Two diff tabs in the first project; no stray roots. |
| I | terminal pane inside Zed | yes | `zed -a --diff a b <project>/adapters/zed` | Diff in the first project; the subdirectory was not added as a root. |

Two cautions apply when reading these runs. Early attempts with the second project carrying the home folder as an unintended root were discarded, because every path under the home folder matched that workspace. Run H also produced two separate diff tabs where the hook documentation describes a single multi-diff pane, and no two-pair baseline exists to say whether the positional path caused it.

The hooks' automated tests replace the `zed` binary with a stand-in that records its arguments. They establish the argument order and the working directory the hooks pass, and say nothing about what Zed does with them. The live runs carry that second claim.

## What the hooks do about it

Both end-of-turn hooks resolve a project directory and pass it twice: as the working directory of the `zed` process and as the last argument, after every `--diff` pair. The Claude Code hook prefers `CLAUDE_PROJECT_DIR`, then the hook event's `cwd`, then its own working directory. The Codex hook uses the event's `cwd` only, because Codex provides no equivalent environment variable. A candidate is rejected when it is not a directory, or when it resolves to the home directory or the filesystem root. If no candidate survives, the hook skips the diff pane and prints a `[Zed]` notice, since attaching the home directory or `/` to a project would be worse than showing no diff. The code is in `adapters/zed/hooks/core/_zed_common.py` (`resolve_project_cwd`) and the two flush hooks under `adapters/zed/hooks/`.

## What the hooks depend on

| Assumption | Where it comes from | What a break looks like |
|---|---|---|
| Positional paths must follow every `--diff` pair. | `trailing_var_arg` on the CLI's `paths` argument. | A tab named `--diff`, or diff operands in the sidebar. |
| A positional path that is an open project's root, or lies inside one, routes the diff to that project regardless of focus. | `find_existing_workspace` with `MatchSubdirectory`; runs H and I. | The diff follows focus despite the path. |
| `--diff` operands never become roots on their own. | Operands open through `open_local_buffer`, not `open_paths`. | Operand files or folders appear in a sidebar after a diff-only call. |
| While Zed is active the working directory is ignored for a diff-only call; otherwise a non-matching working directory becomes a root. | `open_local_workspace`; the control run. | A directory the hook never named appears as a root. |

## Not verified

The source shows the condition under which Zed drops the working directory (a local window being the active window). That Zed counts as active exactly when it is the frontmost application on macOS is an assumption. A symlinked or moved project directory may not match Zed's canonical worktree path, and this was not tried. A positional path that matches no open project should attach it as a root on the preferred workspace according to the source, but no run used that case. The hooks' project directory is normally open in Zed, since the hooks only run inside Zed sessions. Sessions that were started in another directory and moved into Zed could still reach it.

## Checking a new Zed release

1. Compare the files cited above at the new tag with the pinned commit, concentrating on `open_local_workspace`, the declaration of `paths` in the CLI, `find_existing_workspace`, and the two upstream tests that cover the focused-window and working-directory rules ([open_listener.rs:2064](https://github.com/zed-industries/zed/blob/2de9e435a5d98657f35c260b5f4dd0979df659e6/crates/zed/src/zed/open_listener.rs#L2064) and [open_listener.rs:2134](https://github.com/zed-industries/zed/blob/2de9e435a5d98657f35c260b5f4dd0979df659e6/crates/zed/src/zed/open_listener.rs#L2134)).
2. From a terminal pane inside Zed, with the project under test in one workspace and a different project focused, run the F and H commands within the ten-second delay shown here, and look at where each diff opens and whether either sidebar gained a root.

```sh
d=$(mktemp -d); for n in a b c d; do printf "$n\n" > $d/$n.txt; done
(sleep 10; zed -a --diff $d/a.txt $d/b.txt --diff $d/c.txt $d/d.txt) &            # F: expect the focused project
(sleep 10; zed -a --diff $d/a.txt $d/b.txt --diff $d/c.txt $d/d.txt <project>) &  # H: expect <project>, no new roots
```

3. When H fails to land in the named project or adds roots, the contract has changed. Update `resolve_project_cwd` and the hooks, and read the upstream pull request history for the new rules.

## References

- Zed pull request 66386, "Respect focus when selecting CLI workspaces" (merged 2026-11-09, merge commit `597c383bcd024b253c916b083e33d4abcc46fbe1`): https://github.com/zed-industries/zed/pull/66386. Its release note says it fixed `zed --add` choosing the wrong window or project when matches are ambiguous and stopped `zed --add --diff` from adding an unwanted project folder.
- Zed tag `v1.29.2`, commit `2de9e435a5d98657f35c260b5f4dd0979df659e6`. The `v1.29.1` tag is commit `2f58040086e07bd170594a7e857ed3a0b2f218e9`; the change above is confirmed in the `v1.29.2` source only.
- Zed discussion 38023 (exposing `ZED_WINDOW_ID` and CLI window targeting) and issue 58302 (`zed -a` from a linked-worktree terminal routing a diff to the main worktree) cover related requests. This repository has not commented on either.
- [Window-swap fix for `--add`](zed-diff-hook-window-swap-fix.md) and [turn lifecycle](zed-diff-turn-lifecycle.md) describe the earlier behavior this builds on.
