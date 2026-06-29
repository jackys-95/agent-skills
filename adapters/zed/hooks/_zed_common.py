#!/usr/bin/env python3
"""Shared helpers for the Zed adapter hooks.

The hook scripts are deployed as flat files into ~/.claude/hooks/, so this module
sits beside them and is imported by name (the running script's own directory is on
sys.path). install.py copies it alongside the hooks. Keep this dependency-free.
"""
import hashlib
import os
import shutil

# Zed ships its CLI inside the .app. A Homebrew cask install or `cli: install`
# symlinks it onto PATH; a bare .app download does not. The bundle is the fallback.
BUNDLED_ZED_CLI = "/Applications/Zed.app/Contents/MacOS/cli"


def path_hash(file_path):
    """Stable short hash of a file path — keys all the /tmp scratch files below."""
    return hashlib.sha256(file_path.encode()).hexdigest()[:16]


def pointer_path(file_path):
    """File holding the latest snapshot path for file_path (written by pre, read by post/revert)."""
    return f"/tmp/cc_pre_ptr_{path_hash(file_path)}"


def snapshot_path(file_path, ts):
    """Timestamped pre-edit snapshot of file_path."""
    return f"/tmp/cc_pre_{path_hash(file_path)}_{ts}"


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
