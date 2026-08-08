#!/usr/bin/env python3
"""Zed-render-specific helpers for the Zed adapter hooks.

The manifest/snapshot/revert primitives live in adapters/core/ (manifest.py,
snapshot_revert.py) — shared with any future harness's Zed adapter. What's left here is
genuinely Zed/tmux-render-specific: resolving the `zed` CLI and the tmux
generation-token helper. Deployed as a flat file into ~/.claude/hooks/, so this module
sits beside the hooks and core files it imports and is imported by name (the running
script's own directory is on sys.path). install.py copies it alongside the hooks. Keep
this dependency-free beyond snapshot_revert.
"""
import os
import shutil

from snapshot_revert import path_hash

# Zed ships its CLI inside the .app. A Homebrew cask install or `cli: install`
# symlinks it onto PATH; a bare .app download does not. The bundle is the fallback.
BUNDLED_ZED_CLI = "/Applications/Zed.app/Contents/MacOS/cli"


def gen_path(file_path):
    """Generation token file — lets the tmux watcher detect a superseded edit."""
    return f"/tmp/cc_gen_{path_hash(file_path)}"


def resolve_zed():
    """Return a usable `zed` binary path (PATH first, then the bundled .app), or None."""
    found = shutil.which("zed")
    if found:
        return found
    if os.path.isfile(BUNDLED_ZED_CLI) and os.access(BUNDLED_ZED_CLI, os.X_OK):
        return BUNDLED_ZED_CLI
    return None
