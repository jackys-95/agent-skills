"""Errors shared by Codex installer subsystems."""

from __future__ import annotations


class InstallError(ValueError):
    """The adapter cannot be installed safely with the supplied configuration."""
