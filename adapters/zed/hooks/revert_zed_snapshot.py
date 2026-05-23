#!/usr/bin/env python3
"""Revert a file to its pre-edit snapshot captured by pre_edit_zed_snapshot.py.

Usage: python3 revert_zed_snapshot.py <file_path>
"""
import hashlib
import os
import shutil
import sys


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <file_path>", file=sys.stderr)
        sys.exit(1)

    file_path = os.path.abspath(sys.argv[1])
    path_hash = hashlib.sha256(file_path.encode()).hexdigest()[:16]
    pointer = f"/tmp/cc_pre_ptr_{path_hash}"

    if not os.path.isfile(pointer):
        print(f"No snapshot pointer found for {file_path}", file=sys.stderr)
        sys.exit(1)

    snapshot = open(pointer).read().strip()
    if not os.path.isfile(snapshot):
        print(f"Snapshot file missing: {snapshot}", file=sys.stderr)
        sys.exit(1)

    shutil.copyfile(snapshot, file_path)
    print(f"Reverted {file_path} to {snapshot}")


if __name__ == "__main__":
    main()
