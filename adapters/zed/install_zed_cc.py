#!/usr/bin/env python3
"""
Install ZedCC hooks into ~/.claude/settings.json.

Run once:
    python3 adapters/zed/install_zed_cc.py

Then set CC_ZED_HOOK=1 in Zed's terminal environment:
    ~/.config/zed/settings.json → "terminal": { "env": { "CC_ZED_HOOK": "1" } }
"""
import json
import pathlib
import shlex
import shutil
import sys

# Import Claude Code hook registration and shared installer helpers from their
# source responsibility directories without requiring a package layout.
SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[2] / "scripts"
sys.path[:0] = [
    str(SCRIPTS_DIR / "claude-code"),
    str(SCRIPTS_DIR / "core"),
]
from hook_install import install_hook, load_settings, save_settings  # noqa: E402
from install_common import install_tagged_blocks  # noqa: E402

HOOKS_DIR = pathlib.Path(__file__).parent / "hooks"
HOOKS_CORE_DIR = HOOKS_DIR / "core"
HOOKS_CLAUDE_CODE_DIR = HOOKS_DIR / "claude-code"
ADAPTER_CLAUDE_MD = pathlib.Path(__file__).parent / "CLAUDE.md"
PHASE_TURNS_MD = pathlib.Path(__file__).parent / "phase-turns.md"

# Harness-agnostic manifest/snapshot/revert core (adapters/core/, sibling of
# adapters/zed/) — deployed flat alongside the hooks, same as _zed_common.py, so
# `import manifest` / `import snapshot_revert` resolve via same-directory sys.path.
CORE_DIR = pathlib.Path(__file__).resolve().parent.parent / "core"

# Fallback CLI location per platform. macOS: Zed bundles its CLI inside the .app;
# a Homebrew cask install symlinks it onto PATH, but a direct .app download does
# not unless you run `cli: install`. Linux: the official install script places the
# CLI at ~/.local/bin/zed. The post-edit hook calls `zed -a --diff` and fails
# silently if it's missing.
BUNDLED_ZED_CLI = {
    "darwin": pathlib.Path("/Applications/Zed.app/Contents/MacOS/cli"),
    "linux": pathlib.Path.home() / ".local" / "bin" / "zed",
}.get(sys.platform)

# tmux edit-injection watcher binary per platform (see tmux_edit_injection.py).
# Only needed for the tmux edit-injection feature — its absence doesn't break
# the core diff-batching flow, so this is a warning, not a hard requirement.
WATCHER_BIN = {"darwin": "fswatch", "linux": "inotifywait"}.get(sys.platform)

# Claude Code global config
CLAUDE_SETTINGS = pathlib.Path.home() / ".claude" / "settings.json"
CLAUDE_HOOKS_DIR = pathlib.Path.home() / ".claude" / "hooks"
CLAUDE_MD = pathlib.Path.home() / ".claude" / "CLAUDE.md"

# Zed terminal environment (user must set manually)
ZED_SETTINGS = pathlib.Path.home() / ".config" / "zed" / "settings.json"
ZED_ENV_VAR = "CC_ZED_HOOK"

FILE_MATCHER = "Edit|Write"


def hook_command(path, *args):
    return shlex.join(["python3", str(path), *args])


# PreToolUse/PostToolUse are file-tool hooks (matched on Edit|Write). The other
# events are lifecycle hooks with no matcher. UserPromptSubmit resets the
# manifest and restakes pane authority; SessionStart/SessionEnd revoke stale or
# ended authority; Stop flushes one multi-diff and conditionally launches
# watchers. Batching to Stop fronts Zed once per turn instead of once per edit.
HOOKS = [
    {
        "event": "PreToolUse",
        "matcher": FILE_MATCHER,
        "src": HOOKS_CLAUDE_CODE_DIR / "pre_edit_zed_snapshot.py",
        "dest": CLAUDE_HOOKS_DIR / "pre_edit_zed_snapshot.py",
    },
    {
        "event": "PostToolUse",
        "matcher": FILE_MATCHER,
        "src": HOOKS_CLAUDE_CODE_DIR / "post_edit_open_in_zed.py",
        "dest": CLAUDE_HOOKS_DIR / "post_edit_open_in_zed.py",
    },
    {
        "event": "UserPromptSubmit",
        "matcher": None,
        "src": HOOKS_CORE_DIR / "zed_turn_lifecycle.py",
        "dest": CLAUDE_HOOKS_DIR / "zed_turn_lifecycle.py",
        "args": ("--harness", "cc", "--action", "begin"),
        "legacy_commands": (
            hook_command(CLAUDE_HOOKS_DIR / "reset_zed_turn.py"),
        ),
    },
    {
        "event": "Stop",
        "matcher": None,
        "src": (
            HOOKS_CLAUDE_CODE_DIR
            / "stop_flush_claude_code_zed_diffs.py"
        ),
        "dest": (
            CLAUDE_HOOKS_DIR / "stop_flush_claude_code_zed_diffs.py"
        ),
        "legacy_commands": (
            hook_command(CLAUDE_HOOKS_DIR / "stop_flush_zed_diffs.py"),
            hook_command(CLAUDE_HOOKS_DIR / "stop_flush_cc_zed_diffs.py"),
        ),
    },
    {
        "event": "SessionStart",
        "matcher": None,
        "src": HOOKS_CORE_DIR / "zed_turn_lifecycle.py",
        "dest": CLAUDE_HOOKS_DIR / "zed_turn_lifecycle.py",
        "args": ("--harness", "cc", "--action", "reconcile"),
        "legacy_commands": (
            hook_command(CLAUDE_HOOKS_DIR / "revoke_zed_pane_authority.py"),
        ),
    },
    {
        "event": "SessionEnd",
        "matcher": None,
        "src": HOOKS_CORE_DIR / "zed_turn_lifecycle.py",
        "dest": CLAUDE_HOOKS_DIR / "zed_turn_lifecycle.py",
        "args": ("--harness", "cc", "--action", "reconcile"),
        "legacy_commands": (
            hook_command(CLAUDE_HOOKS_DIR / "revoke_zed_pane_authority.py"),
        ),
    },
]

# Scripts copied to hooks dir but not registered as CC hooks. Imported modules
# MUST land beside their callers because the installed runtime is flat.
SCRIPTS = [
    HOOKS_CORE_DIR / "_zed_common.py",
    HOOKS_CLAUDE_CODE_DIR / "revert_zed_snapshot.py",
    HOOKS_CORE_DIR / "tmux_edit_injection.py",
    HOOKS_CORE_DIR / "tmux_pane_authority.py",
    CORE_DIR / "manifest.py",
    CORE_DIR / "snapshot_revert.py",
]

OBSOLETE_SCRIPTS = (
    "reset_zed_turn.py",
    "revoke_zed_pane_authority.py",
    "stop_flush_cc_zed_diffs.py",
    "stop_flush_zed_diffs.py",
    "tmux_diff_injector.py",
    "tmux_injection.py",
)


def install_claude_md():
    install_tagged_blocks(ADAPTER_CLAUDE_MD, CLAUDE_MD, False, "Zed CLAUDE.md")
    install_tagged_blocks(PHASE_TURNS_MD, CLAUDE_MD, False, "Zed phase-turn")


def install_accept_edits(claude_settings):
    perms = claude_settings.setdefault("permissions", {})
    if perms.get("defaultMode") == "acceptEdits":
        print("defaultMode: acceptEdits already set.")
        return
    perms["defaultMode"] = "acceptEdits"
    print("Set defaultMode: acceptEdits.")


def remove_obsolete_scripts():
    for name in OBSOLETE_SCRIPTS:
        path = CLAUDE_HOOKS_DIR / name
        if path.exists():
            path.unlink()
            print(f"Removed obsolete runtime: {path}")


def check_zed_cli():
    """Warn if the `zed` CLI isn't on PATH — the post-edit hook needs it to open diffs.

    Returns True if `zed` resolves, False otherwise (install continues either way).
    """
    if shutil.which("zed"):
        return True

    print("\n⚠️  The `zed` CLI is not on your PATH.")
    print("   The post-edit hook runs `zed -a --diff` to open the review pane; without")
    print("   the CLI it fails silently and no diff appears.\n")
    if BUNDLED_ZED_CLI and BUNDLED_ZED_CLI.exists():
        print("   Zed is installed, but its CLI isn't on PATH. Fix it with either:")
        print("     • In Zed: command palette → `cli: install`")
        print(f"     • Shell:  ln -s {BUNDLED_ZED_CLI} /usr/local/bin/zed")
    elif sys.platform == "darwin":
        print("   Install Zed (https://zed.dev) and then run its `cli: install` command,")
        print("   or `brew install --cask zed` which links the CLI for you.")
    else:
        print("   Install Zed for Linux (https://zed.dev/docs/linux) and make sure")
        print("   ~/.local/bin is on your PATH.")
    print("   Verify with: zed --version\n")
    return False


def check_watcher():
    """Warn if the tmux edit-injection watcher binary isn't on PATH.

    Only affects the tmux edit-injection feature (`tmux_edit_injection.py`); the
    core diff-batching flow works without it. Returns True if found.
    """
    if not WATCHER_BIN:
        return True
    if shutil.which(WATCHER_BIN):
        return True

    print(f"\n⚠️  `{WATCHER_BIN}` is not on your PATH.")
    print("   If you run CC inside tmux, the Stop hook uses it to notice when you")
    print("   save an edit in Zed and inject the diff back into CC's input. Without")
    print("   it, that tmux edit-injection feature silently does nothing (the core")
    print("   diff-batching flow is unaffected).\n")
    if sys.platform == "darwin":
        print("   Install with: brew install fswatch")
    else:
        print("   Install with: sudo apt install inotify-tools  (or your distro's equivalent)")
    print(f"   Verify with: {WATCHER_BIN} --version\n")
    return False


def main():
    CLAUDE_HOOKS_DIR.mkdir(parents=True, exist_ok=True)
    claude_settings = load_settings()

    copied = set()
    for hook in HOOKS:
        if hook["dest"] not in copied:
            shutil.copy2(hook["src"], hook["dest"])
            hook["dest"].chmod(0o755)
            copied.add(hook["dest"])
            print(f"Copied {hook['src'].name} → {hook['dest']}")
        install_hook(
            claude_settings,
            hook["event"],
            hook["dest"],
            hook["matcher"],
            args=hook.get("args", ()),
            legacy_commands=hook.get("legacy_commands", ()),
        )

    for script in SCRIPTS:
        dest = CLAUDE_HOOKS_DIR / script.name
        shutil.copy2(script, dest)
        dest.chmod(0o755)
        print(f"Copied {script.name} → {dest}")
    remove_obsolete_scripts()

    install_accept_edits(claude_settings)
    save_settings(claude_settings)
    print(f"Updated Claude settings: {CLAUDE_SETTINGS}")

    # Install CLAUDE.md section
    install_claude_md()

    # Remind user to set the guard env var in Zed agent_servers config
    print(
        f"\nNext: set {ZED_ENV_VAR}=1 in Zed's agent_servers env so the hook only"
        f" fires when CC runs inside Zed.\n"
        f"In {ZED_SETTINGS} add:\n"
        f'  "agent_servers": {{ "claude-acp": {{ "type": "registry", "env": {{ "{ZED_ENV_VAR}": "1" }} }} }}'
    )

    # Preflight: the diff pane silently no-ops without the `zed` CLI on PATH.
    check_zed_cli()
    # Preflight: tmux edit-injection silently no-ops without the watcher binary.
    check_watcher()


if __name__ == "__main__":
    main()
