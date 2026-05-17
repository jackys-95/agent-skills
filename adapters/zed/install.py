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

ADAPTER_HOOK_SRC = pathlib.Path(__file__).parent / "hooks" / "post_edit_open_in_zed.py"

# Claude Code global config
CLAUDE_SETTINGS = pathlib.Path.home() / ".claude" / "settings.json"
CLAUDE_HOOKS_DIR = pathlib.Path.home() / ".claude" / "hooks"
CLAUDE_HOOK_DEST = CLAUDE_HOOKS_DIR / "post_edit_open_in_zed.py"

# Zed terminal environment (user must set manually)
ZED_SETTINGS = pathlib.Path.home() / ".config" / "zed" / "settings.json"
ZED_ENV_VAR = "CC_ZED_HOOK"

CLAUDE_HOOK_ENTRY = {
    "type": "command",
    "command": f"python3 {CLAUDE_HOOK_DEST}",
}
CLAUDE_POSTTOOLUSE_MATCHER = "Edit|Write"


def load_claude_settings():
    if CLAUDE_SETTINGS.exists():
        return json.loads(CLAUDE_SETTINGS.read_text())
    return {}


def save_claude_settings(data):
    CLAUDE_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    CLAUDE_SETTINGS.write_text(json.dumps(data, indent=2) + "\n")


def install_claude_hook(claude_settings):
    post_tool_use = claude_settings.setdefault("hooks", {}).setdefault("PostToolUse", [])

    for entry in post_tool_use:
        if entry.get("matcher") == CLAUDE_POSTTOOLUSE_MATCHER:
            cmds = entry.setdefault("hooks", [])
            if any(h.get("command") == CLAUDE_HOOK_ENTRY["command"] for h in cmds):
                print("Hook already installed in Claude settings.")
                return
            cmds.append(CLAUDE_HOOK_ENTRY)
            print("Added hook to existing Edit|Write matcher in Claude settings.")
            return

    post_tool_use.append({"matcher": CLAUDE_POSTTOOLUSE_MATCHER, "hooks": [CLAUDE_HOOK_ENTRY]})
    print("Added new Edit|Write matcher with hook to Claude settings.")


def main():
    if not shutil.which("fswatch"):
        print("Warning: fswatch not found. Install with: brew install fswatch")

    # Copy hook script into Claude hooks directory
    CLAUDE_HOOKS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ADAPTER_HOOK_SRC, CLAUDE_HOOK_DEST)
    CLAUDE_HOOK_DEST.chmod(0o755)
    print(f"Copied hook to Claude hooks dir: {CLAUDE_HOOK_DEST}")

    # Wire hook into Claude global settings
    claude_settings = load_claude_settings()
    install_claude_hook(claude_settings)
    save_claude_settings(claude_settings)
    print(f"Updated Claude settings: {CLAUDE_SETTINGS}")

    # Remind user to set the guard env var in Zed
    print(
        f"\nNext: set {ZED_ENV_VAR}=1 in Zed's terminal environment so the hook only"
        f" fires when CC runs inside Zed.\n"
        f"In {ZED_SETTINGS} add:\n"
        f'  "terminal": {{ "env": {{ "{ZED_ENV_VAR}": "1" }} }}'
    )


if __name__ == "__main__":
    main()
