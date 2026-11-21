#!/usr/bin/env python3
"""Core Zed-render-specific helpers shared across harness hooks.

The manifest/snapshot/revert primitives live in adapters/core/ (manifest.py,
snapshot_revert.py) — shared with any future harness's Zed adapter. What's left here is
genuinely Zed-render-specific: resolving the `zed` CLI. Deployed as a flat file into
~/.claude/hooks/, so this module sits beside the hooks and is imported by name (the
running script's own directory is on sys.path). install_zed_cc.py copies it alongside the
hooks.
"""
import os
import shutil
import sys

# Fallback CLI location when `zed` isn't on PATH. macOS: Zed ships its CLI inside
# the .app — a Homebrew cask install or `cli: install` symlinks it onto PATH, a
# bare .app download does not. Linux: the official install script places the CLI
# at ~/.local/bin/zed, which may not be on PATH in a hook's environment.
BUNDLED_ZED_CLI = {
    "darwin": "/Applications/Zed.app/Contents/MacOS/cli",
    "linux": os.path.expanduser("~/.local/bin/zed"),
}.get(sys.platform, "")

def resolve_project_cwd(event, env=None):
    """Return the directory to use as the `zed` process cwd, or None if none is safe.

    With `--add`, Zed matches the diff to an open project by the CLI's working
    directory. A cwd inside an open project routes the diff there whatever has focus;
    a cwd that matches no open project makes Zed fall back to the focused workspace and
    attach that directory to it as a root. So pass the originating project directory
    explicitly instead of inheriting whatever directory the agent was launched from.

    Candidates, in order: CLAUDE_PROJECT_DIR, the hook event's `cwd`, this process's
    cwd. A candidate is unusable if it is not a directory, or is the home directory or
    the filesystem root — attaching those to a project is the failure being avoided.
    """
    env = os.environ if env is None else env
    unsafe = {os.path.realpath(os.path.expanduser("~")), os.path.realpath(os.sep)}
    for candidate in (env.get("CLAUDE_PROJECT_DIR"), event.get("cwd"), os.getcwd()):
        if not candidate or not os.path.isabs(candidate):
            continue
        if os.path.isdir(candidate) and os.path.realpath(candidate) not in unsafe:
            return candidate
    return None


def resolve_zed():
    """Return a usable `zed` binary path (PATH first, then the platform fallback), or None."""
    found = shutil.which("zed")
    if found:
        return found
    if (
        BUNDLED_ZED_CLI
        and os.path.isfile(BUNDLED_ZED_CLI)
        and os.access(BUNDLED_ZED_CLI, os.X_OK)
    ):
        return BUNDLED_ZED_CLI
    return None
