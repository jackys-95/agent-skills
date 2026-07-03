#!/usr/bin/env python3
"""Revert a file to its pre-edit snapshot captured by pre_edit_zed_snapshot.py.

Usage: python3 revert_zed_snapshot.py <file_path>
"""
import os
import shutil
import sys

from _zed_common import pointer_path


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <file_path>", file=sys.stderr)
        sys.exit(1)

    file_path = os.path.abspath(sys.argv[1])
    pointer = pointer_path(file_path)

    if not os.path.isfile(pointer):
        print(f"No snapshot pointer found for {file_path}", file=sys.stderr)
        sys.exit(1)

    snapshot = open(pointer).read().strip()

    # A /dev/null pointer means the file did not exist at turn start (created this
    # turn by Write). Reverting = restoring "did not exist" = deleting it.
    if snapshot == os.devnull:
        if os.path.isfile(file_path):
            os.remove(file_path)
        print(f"Reverted {file_path} — deleted (was created this turn)")
        return

    if not os.path.isfile(snapshot):
        print(f"Snapshot file missing: {snapshot}", file=sys.stderr)
        sys.exit(1)

    shutil.copyfile(snapshot, file_path)
    print(f"Reverted {file_path} to {snapshot}")


if __name__ == "__main__":
    main()
