<!-- zed-codex-adapter -->
# ZedCodex Review Behavior

When `CODEX_ZED_HOOK=1` is present, `apply_patch` changes are collected into one Zed multi-diff at the end of the turn. The review is non-blocking.

- After each successful `apply_patch`, retain every unique hook-provided `reply 'r <file>' to revert` instruction for that turn. Do not surface these instructions during implementation updates. Before ending the turn, append every retained instruction to the final response as a standalone line, one line per file.
- When the user replies `r <file>`, run `python3 ~/.codex/hooks/zedcodex/revert_codex_zed_snapshot.py <file>` and then ask what they want instead.
- For `revert all`, run the same command once for every file changed in the reviewed turn.
- Prefer `apply_patch` for file mutation while this adapter is active. Shell redirection, `sed -i`, move commands, and scripts that write files bypass the current review detector and will not get a Zed diff or revert snapshot.
- Do not narrate the diff contents or ask for acceptance. Silence means the user accepted the files on disk.

Reverting restores each file to its first pre-edit state from the turn. A file created during the turn is deleted when reverted.

## When the user saves in the diff view

A save in Zed (Cmd+S on macOS, Ctrl+S on Linux) keeps the user's version on disk and discards yours for that file - but **nothing notifies this session**. There is no watcher echoing the saved delta back, so the file on disk can differ from what you last wrote with no signal in the conversation.

- Re-read a file before editing it again if the user may have saved it, and re-read it whenever they mention editing, saving, or keeping their own version. Do not assume your last written content is still current.
- Do not treat silence as confirmation that your version survived. Silence means the user did not ask for a revert; it does not mean they did not edit the file themselves.
<!-- zed-codex-adapter -->
