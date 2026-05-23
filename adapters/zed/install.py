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

HOOKS_DIR = pathlib.Path(__file__).parent / "hooks"
ADAPTER_CLAUDE_MD = pathlib.Path(__file__).parent / "CLAUDE.md"

# Claude Code global config
CLAUDE_SETTINGS = pathlib.Path.home() / ".claude" / "settings.json"
CLAUDE_HOOKS_DIR = pathlib.Path.home() / ".claude" / "hooks"
CLAUDE_MD = pathlib.Path.home() / ".claude" / "CLAUDE.md"

CLAUDE_MD_MARKER = "<!-- zed-adapter -->"

# Zed terminal environment (user must set manually)
ZED_SETTINGS = pathlib.Path.home() / ".config" / "zed" / "settings.json"
ZED_ENV_VAR = "CC_ZED_HOOK"

FILE_MATCHER = "Edit|Write"

HOOKS = [
    {
        "event": "PreToolUse",
        "src": HOOKS_DIR / "pre_edit_zed_snapshot.py",
        "dest": CLAUDE_HOOKS_DIR / "pre_edit_zed_snapshot.py",
    },
    {
        "event": "PostToolUse",
        "src": HOOKS_DIR / "post_edit_open_in_zed.py",
        "dest": CLAUDE_HOOKS_DIR / "post_edit_open_in_zed.py",
    },
]

# Scripts copied to hooks dir but not registered as CC hooks
SCRIPTS = [
    HOOKS_DIR / "revert_zed_snapshot.py",
]


def load_claude_settings():
    if CLAUDE_SETTINGS.exists():
        return json.loads(CLAUDE_SETTINGS.read_text())
    return {}


def save_claude_settings(data):
    CLAUDE_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    CLAUDE_SETTINGS.write_text(json.dumps(data, indent=2) + "\n")


def install_claude_hook(claude_settings, event, dest):
    entries = claude_settings.setdefault("hooks", {}).setdefault(event, [])
    cmd = f"python3 {dest}"

    for entry in entries:
        if entry.get("matcher") == FILE_MATCHER:
            cmds = entry.setdefault("hooks", [])
            if any(h.get("command") == cmd for h in cmds):
                print(f"{event} hook already installed.")
                return
            cmds.append({"type": "command", "command": cmd})
            print(f"Added {event} hook to existing matcher.")
            return

    entries.append({"matcher": FILE_MATCHER, "hooks": [{"type": "command", "command": cmd}]})
    print(f"Added {event} hook with new matcher.")


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


def main():
    CLAUDE_HOOKS_DIR.mkdir(parents=True, exist_ok=True)
    claude_settings = load_claude_settings()

    for hook in HOOKS:
        shutil.copy2(hook["src"], hook["dest"])
        hook["dest"].chmod(0o755)
        print(f"Copied {hook['src'].name} → {hook['dest']}")
        install_claude_hook(claude_settings, hook["event"], hook["dest"])

    for script in SCRIPTS:
        dest = CLAUDE_HOOKS_DIR / script.name
        shutil.copy2(script, dest)
        dest.chmod(0o755)
        print(f"Copied {script.name} → {dest}")

    install_accept_edits(claude_settings)
    save_claude_settings(claude_settings)
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


if __name__ == "__main__":
    main()
