#!/usr/bin/env python3
"""Scaffold and maintain a qmd-backed task memory bank."""

from __future__ import annotations

import argparse
import sys

from memory_bank_lib.common import WORK_TYPES
from memory_bank_lib.project import init_project, resolve_project
from memory_bank_lib.qmd import doctor, qmd_status, reindex, setup_qmd
from memory_bank_lib.review import review_clean, review_mirror, review_patch, review_start
from memory_bank_lib.work import append_history, branch_work, new_work


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init-project", help="Initialize project memory structure")
    p.add_argument("--root", required=True)
    p.add_argument("--project", required=True)
    p.add_argument("--repo")
    p.set_defaults(func=init_project)

    p = sub.add_parser("new-work", help="Create an epic/story/task/spike")
    p.add_argument("--root", required=True)
    p.add_argument("--project", required=True)
    p.add_argument("--type", required=True, choices=sorted(WORK_TYPES))
    p.add_argument("--title", required=True)
    p.add_argument("--id")
    p.add_argument("--domain")
    p.set_defaults(func=new_work)

    p = sub.add_parser("resolve-project", help="Resolve current or provided git repo to memory project")
    p.add_argument("--root", required=True)
    p.add_argument("--repo")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=resolve_project)

    p = sub.add_parser("branch-work", help="Create an attempt under a work item")
    p.add_argument("--work", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--reason")
    p.set_defaults(func=branch_work)

    p = sub.add_parser("append-history", help="Append a session history entry")
    p.add_argument("--work", required=True)
    p.add_argument("--summary")
    p.add_argument("--summary-file")
    p.set_defaults(func=append_history)

    p = sub.add_parser("reindex", help="Run memory-bank qmd maintenance")
    p.add_argument("--no-embed", action="store_true", help="Run qmd update only")
    p.add_argument(
        "--embed-optional",
        action="store_true",
        help="Treat qmd embed failure as a warning after qmd update succeeds",
    )
    p.set_defaults(func=reindex)

    p = sub.add_parser("qmd-status", help="Show qmd index and collection status")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=qmd_status)

    p = sub.add_parser("setup-qmd", help="Register memory-bank qmd collections/contexts")
    p.add_argument("--root", required=True)
    p.add_argument("--project")
    p.set_defaults(func=setup_qmd)

    p = sub.add_parser("review-start", help="Snapshot external memory before Codex app edits")
    p.add_argument("--memory-path", required=True)
    p.add_argument("--mirror-dir", default=".task-memory-review")
    p.add_argument("--clean", action="store_true", help="Remove the mirror dir before starting")
    p.set_defaults(func=review_start)

    p = sub.add_parser("review-mirror", help="Mirror external memory changes into repo-local review files")
    p.add_argument("--before", help="Snapshot directory from before the memory edit")
    p.add_argument("--memory-path", help="Current memory project directory")
    p.add_argument("--mirror-dir", default=".task-memory-review")
    p.add_argument("--clean-empty", action="store_true")
    p.set_defaults(func=review_mirror)

    p = sub.add_parser("review-patch", help="Write a compact patch for external memory changes")
    p.add_argument("--before", help="Snapshot directory from before the memory edit")
    p.add_argument("--memory-path", help="Current memory project directory")
    p.add_argument("--mirror-dir", default=".task-memory-review")
    p.add_argument("--output", required=True)
    p.add_argument("--remove-empty", action="store_true")
    p.set_defaults(func=review_patch)

    p = sub.add_parser("review-clean", help="Remove Codex app memory review mirror and snapshot")
    p.add_argument("--mirror-dir", default=".task-memory-review")
    p.add_argument("--remove-snapshot", action="store_true")
    p.set_defaults(func=review_clean)

    p = sub.add_parser("doctor", help="Check memory-bank structure and qmd availability")
    p.add_argument("--root", required=True)
    p.set_defaults(func=doctor)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
