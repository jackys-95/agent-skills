#!/usr/bin/env python3
"""
Install the Zed adapter hooks into ~/.claude/settings.json.

Run once:
    python3 adapters/zed/install.py

Then set CC_ZED_HOOK=1 in Zed's terminal environment:
    ~/.config/zed/settings.json → "terminal": { "env": { "CC_ZED_HOOK": "1" } }
"""
import json
import pathlib
import shutil
import sys

# Shared, adapter-neutral hook-registration helpers live in <repo>/scripts. Import
# by path so this installer stays self-contained without a package layout.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts"))
from hook_install import install_hook, load_settings, save_settings  # noqa: E402

HOOKS_DIR = pathlib.Path(__file__).parent / "hooks"
ADAPTER_CLAUDE_MD = pathlib.Path(__file__).parent / "CLAUDE.md"

# Harness-agnostic manifest/snapshot/revert core (adapters/core/, sibling of
# adapters/zed/) — deployed flat alongside the hooks, same as _zed_common.py, so
# `import manifest` / `import snapshot_revert` resolve via same-directory sys.path.
CORE_DIR = pathlib.Path(__file__).resolve().parent.parent / "core"

# Zed bundles its CLI inside the .app; a Homebrew cask install symlinks it onto
# PATH, but a direct .app download does not unless you run `cli: install`.
# The post-edit hook calls `zed -a --diff` and fails silently if it's missing.
BUNDLED_ZED_CLI = pathlib.Path("/Applications/Zed.app/Contents/MacOS/cli")

# Claude Code global config
CLAUDE_SETTINGS = pathlib.Path.home() / ".claude" / "settings.json"
CLAUDE_HOOKS_DIR = pathlib.Path.home() / ".claude" / "hooks"
CLAUDE_MD = pathlib.Path.home() / ".claude" / "CLAUDE.md"

CLAUDE_MD_MARKER = "<!-- zed-adapter -->"

# Zed terminal environment (user must set manually)
ZED_SETTINGS = pathlib.Path.home() / ".config" / "zed" / "settings.json"
ZED_ENV_VAR = "CC_ZED_HOOK"

FILE_MATCHER = "Edit|Write"

# PreToolUse/PostToolUse are file-tool hooks (matched on Edit|Write); UserPromptSubmit
# and Stop are turn-boundary hooks with no tool matcher. The pre-hook snapshots the
# turn-start base once per file; the post-hook queues the file in the turn manifest;
# UserPromptSubmit resets the manifest at turn start; Stop flushes the whole turn into
# one multi-diff. Batching to Stop fronts Zed once per turn instead of once per edit.
HOOKS = [
    {
        "event": "PreToolUse",
        "matcher": FILE_MATCHER,
        "src": HOOKS_DIR / "pre_edit_zed_snapshot.py",
        "dest": CLAUDE_HOOKS_DIR / "pre_edit_zed_snapshot.py",
    },
    {
        "event": "PostToolUse",
        "matcher": FILE_MATCHER,
        "src": HOOKS_DIR / "post_edit_open_in_zed.py",
        "dest": CLAUDE_HOOKS_DIR / "post_edit_open_in_zed.py",
    },
    {
        "event": "UserPromptSubmit",
        "matcher": None,
        "src": HOOKS_DIR / "reset_zed_turn.py",
        "dest": CLAUDE_HOOKS_DIR / "reset_zed_turn.py",
    },
    {
        "event": "Stop",
        "matcher": None,
        "src": HOOKS_DIR / "stop_flush_zed_diffs.py",
        "dest": CLAUDE_HOOKS_DIR / "stop_flush_zed_diffs.py",
    },
]

# Scripts copied to hooks dir but not registered as CC hooks.
# _zed_common.py, manifest.py, and snapshot_revert.py are modules the hooks import —
# they MUST land beside them.
SCRIPTS = [
    HOOKS_DIR / "_zed_common.py",
    HOOKS_DIR / "revert_zed_snapshot.py",
    HOOKS_DIR / "tmux_diff_injector.py",
    CORE_DIR / "manifest.py",
    CORE_DIR / "snapshot_revert.py",
]


def install_claude_md():
    content = ADAPTER_CLAUDE_MD.read_text()
    block = f"{CLAUDE_MD_MARKER}\n{content.rstrip()}\n{CLAUDE_MD_MARKER}"
    existing = CLAUDE_MD.read_text() if CLAUDE_MD.exists() else ""
    if CLAUDE_MD_MARKER in existing:
        import re
        updated = re.sub(
            rf"{re.escape(CLAUDE_MD_MARKER)}.*?{re.escape(CLAUDE_MD_MARKER)}",
            block,
            existing,
            flags=re.DOTALL,
        )
        CLAUDE_MD.write_text(updated)
        print(f"Updated Zed adapter section in {CLAUDE_MD}")
    else:
        sep = "\n\n" if existing.strip() else ""
        CLAUDE_MD.write_text(existing + sep + block + "\n")
        print(f"Appended Zed adapter section to {CLAUDE_MD}")


def install_accept_edits(claude_settings):
    perms = claude_settings.setdefault("permissions", {})
    if perms.get("defaultMode") == "acceptEdits":
        print("defaultMode: acceptEdits already set.")
        return
    perms["defaultMode"] = "acceptEdits"
    print("Set defaultMode: acceptEdits.")


def check_zed_cli():
    """Warn if the `zed` CLI isn't on PATH — the post-edit hook needs it to open diffs.

    Returns True if `zed` resolves, False otherwise (install continues either way).
    """
    if shutil.which("zed"):
        return True

    print("\n⚠️  The `zed` CLI is not on your PATH.")
    print("   The post-edit hook runs `zed -a --diff` to open the review pane; without")
    print("   the CLI it fails silently and no diff appears.\n")
    if BUNDLED_ZED_CLI.exists():
        print("   Zed is installed, but its CLI isn't linked. Fix it with either:")
        print("     • In Zed: command palette → `cli: install`")
        print(f"     • Shell:  ln -s {BUNDLED_ZED_CLI} /usr/local/bin/zed")
    else:
        print("   Install Zed (https://zed.dev) and then run its `cli: install` command,")
        print("   or `brew install --cask zed` which links the CLI for you.")
    print("   Verify with: zed --version\n")
    return False


def main():
    CLAUDE_HOOKS_DIR.mkdir(parents=True, exist_ok=True)
    claude_settings = load_settings()

    for hook in HOOKS:
        shutil.copy2(hook["src"], hook["dest"])
        hook["dest"].chmod(0o755)
        print(f"Copied {hook['src'].name} → {hook['dest']}")
        install_hook(claude_settings, hook["event"], hook["dest"], hook["matcher"])

    for script in SCRIPTS:
        dest = CLAUDE_HOOKS_DIR / script.name
        shutil.copy2(script, dest)
        dest.chmod(0o755)
        print(f"Copied {script.name} → {dest}")

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


if __name__ == "__main__":
    main()
