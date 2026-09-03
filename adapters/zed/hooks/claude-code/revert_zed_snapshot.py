#!/usr/bin/env python3
"""Claude Code revert command for a snapshot captured before an edit.

Usage: python3 revert_zed_snapshot.py <file_path>
"""
import os
import sys

import snapshot_revert

NAMESPACE = "cc_zed"


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <file_path>", file=sys.stderr)
        sys.exit(1)

    file_path = os.path.abspath(sys.argv[1])
    ok = snapshot_revert.revert(NAMESPACE, file_path)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
