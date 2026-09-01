#!/usr/bin/env python3
"""Zed-render-specific helpers for the Zed adapter hooks.

The manifest/snapshot/revert primitives live in adapters/core/ (manifest.py,
snapshot_revert.py) — shared with any future harness's Zed adapter. What's left here is
genuinely Zed-render-specific: resolving the `zed` CLI. Deployed as a flat file into
~/.claude/hooks/, so this module sits beside the hooks and is imported by name (the
running script's own directory is on sys.path). install.py copies it alongside the
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
