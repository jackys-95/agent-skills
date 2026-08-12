#!/usr/bin/env python3
"""Restore one path to the turn-start base captured before apply_patch."""

import os
import sys

import snapshot_revert
from _codex_patch import canonical_path

NAMESPACE = "codex_zed"


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <file_path>", file=sys.stderr)
        return 1

    path = canonical_path(sys.argv[1], os.getcwd())
    return 0 if snapshot_revert.revert(NAMESPACE, path) else 1


if __name__ == "__main__":
    raise SystemExit(main())
