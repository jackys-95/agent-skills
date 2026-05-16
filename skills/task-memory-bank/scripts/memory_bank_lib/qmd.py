from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from .common import (
    collection_name,
    expand,
    parse_collections,
    project_dir,
    run_command,
    slugify,
)


def reindex(args: argparse.Namespace) -> None:
    commands = [["qmd", "update"]]
    if not args.no_embed:
        commands.append(["qmd", "embed"])
    for command in commands:
        optional = command[1] == "embed" and args.embed_optional
        ok = run_command(command, optional=optional)
        if not ok:
            break


def qmd_status(args: argparse.Namespace) -> None:
    command = ["qmd", "status"]
    if args.json:
        command.append("--json")
    run_command(command)


def qmd_doctor() -> list[str]:
    result = subprocess.run(
        ["qmd", "--help"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return [] if result.returncode == 0 else ["qmd CLI is unavailable"]


def setup_qmd(args: argparse.Namespace) -> None:
    root = expand(args.root)
    if args.project:
        project = slugify(args.project)
        pdir = project_dir(root, project)
        cname = collection_name(project)
        readme = pdir / "README.md"
        if not pdir.exists():
            raise SystemExit(f"Project memory does not exist: {pdir}")
        commands = [["qmd", "collection", "add", str(pdir), "--name", cname]]
        if readme.exists():
            commands.append(["qmd", "context", "add", project, str(readme)])
    else:
        commands = [["qmd", "collection", "add", str(root), "--name", "task-memory-bank"]]
    for command in commands:
        run_command(command)


def doctor(args: argparse.Namespace) -> None:
    root = expand(args.root)
    problems = []
    warnings = []
    if not root.exists():
        problems.append(f"Missing root: {root}")
    if not (root / "registry.md").exists():
        problems.append("Missing registry.md")
    if not (root / ".memory-bank" / "collections.yaml").exists():
        problems.append("Missing .memory-bank/collections.yaml")
    else:
        collections = parse_collections(root / ".memory-bank" / "collections.yaml")
        for name, fields in collections.items():
            if fields.get("kind") != "project":
                continue
            for key in ("path", "project", "repo", "context"):
                if not fields.get(key):
                    problems.append(f"Collection {name} is missing {key}")
            if fields.get("path") and not expand(fields["path"]).exists():
                problems.append(f"Collection {name} path does not exist: {fields['path']}")
            if fields.get("repo") and not expand(fields["repo"]).exists():
                warnings.append(f"Collection {name} repo does not exist on this machine: {fields['repo']}")
    problems.extend(qmd_doctor())
    if problems:
        print("Problems:")
        for problem in problems:
            print(f"- {problem}")
        raise SystemExit(1)
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")
    print("Memory bank looks structurally healthy.")
