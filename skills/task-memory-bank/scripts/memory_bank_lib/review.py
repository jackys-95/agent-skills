from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .common import WORK_TYPES, expand, run_command


SESSION_FILE = "session.json"


def memory_review_relpath(rel: Path) -> Path:
    parts = rel.parts
    if len(parts) >= 4 and parts[0] == "work" and parts[1] in {v[1] for v in WORK_TYPES.values()}:
        match = re.match(r"^([A-Z]+-\d+)(?:-|$)", parts[2])
        if match:
            return Path("memory") / match.group(1) / Path(*parts[3:])
    return Path("memory") / rel


def file_changed(before_file: Path | None, after_file: Path | None) -> bool:
    if before_file is None or after_file is None:
        return True
    if not before_file.exists() or not after_file.exists():
        return True
    if before_file.stat().st_size != after_file.stat().st_size:
        return True
    return before_file.read_bytes() != after_file.read_bytes()


def changed_memory_files(before: Path, after: Path) -> list[Path]:
    before_files = {
        path.relative_to(before)
        for path in before.rglob("*")
        if path.is_file() and ".DS_Store" not in path.parts
    }
    after_files = {
        path.relative_to(after)
        for path in after.rglob("*")
        if path.is_file() and ".DS_Store" not in path.parts
    }
    changed = []
    for rel in sorted(before_files | after_files):
        before_file = before / rel if rel in before_files else None
        after_file = after / rel if rel in after_files else None
        if file_changed(before_file, after_file):
            changed.append(rel)
    return changed


def mirror_dir(path: str) -> Path:
    value = Path(path)
    return value if value.is_absolute() else Path.cwd() / value


def session_path(mirror: Path) -> Path:
    return mirror / SESSION_FILE


def load_session(path: Path) -> dict[str, str]:
    if not path.exists():
        raise SystemExit(f"Review session not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def git_add(paths: list[Path], intent: bool = False) -> None:
    if not paths:
        return
    command = ["git", "add"]
    if intent:
        command.append("-N")
    command.extend(str(path) for path in paths)
    run_command(command)


def review_start(args: argparse.Namespace) -> None:
    memory_path = expand(args.memory_path)
    mirror = mirror_dir(args.mirror_dir)
    if not memory_path.exists():
        raise SystemExit(f"Memory path does not exist: {memory_path}")
    if args.clean and mirror.exists():
        shutil.rmtree(mirror)
    mirror.mkdir(parents=True, exist_ok=True)
    snapshot = Path(tempfile.mkdtemp(prefix="task-memory-before-"))
    before = snapshot / "memory"
    shutil.copytree(memory_path, before, symlinks=True)
    payload = {
        "memory_path": str(memory_path),
        "snapshot_path": str(before),
        "mirror_dir": str(mirror),
        "created_at": dt.datetime.now(dt.UTC).isoformat(),
    }
    session_path(mirror).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Started memory review session: {session_path(mirror)}")
    print(f"Snapshot: {before}")


def resolve_review_inputs(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    mirror = mirror_dir(args.mirror_dir)
    if args.before and args.memory_path:
        return expand(args.before), expand(args.memory_path), mirror
    session = load_session(session_path(mirror))
    return Path(session["snapshot_path"]), Path(session["memory_path"]), Path(session["mirror_dir"])


def review_mirror(args: argparse.Namespace) -> None:
    before, memory_path, mirror = resolve_review_inputs(args)
    if not before.exists():
        raise SystemExit(f"Before snapshot does not exist: {before}")
    if not memory_path.exists():
        raise SystemExit(f"Memory path does not exist: {memory_path}")

    changed = changed_memory_files(before, memory_path)
    if not changed:
        if args.clean_empty and mirror.exists():
            shutil.rmtree(mirror)
            print(f"No memory changes; removed empty mirror: {mirror}")
        else:
            print("No memory changes.")
        return

    baseline_paths: list[Path] = []
    added_paths: list[Path] = []
    for rel in changed:
        mirror_path = mirror / memory_review_relpath(rel)
        before_file = before / rel
        after_file = memory_path / rel
        mirror_path.parent.mkdir(parents=True, exist_ok=True)
        if before_file.exists():
            shutil.copy2(before_file, mirror_path)
            baseline_paths.append(mirror_path)
        elif after_file.exists():
            shutil.copy2(after_file, mirror_path)
            added_paths.append(mirror_path)

    git_add(baseline_paths)
    git_add(added_paths, intent=True)

    for rel in changed:
        mirror_path = mirror / memory_review_relpath(rel)
        after_file = memory_path / rel
        if after_file.exists():
            shutil.copy2(after_file, mirror_path)
        elif mirror_path.exists():
            mirror_path.unlink()

    print(f"Wrote memory review mirror: {mirror}")
    print(f"Mirrored {len(changed)} changed file(s).")


def review_clean(args: argparse.Namespace) -> None:
    mirror = mirror_dir(args.mirror_dir)
    session = {}
    if session_path(mirror).exists():
        session = load_session(session_path(mirror))
    if args.remove_snapshot and session.get("snapshot_path"):
        snapshot = Path(session["snapshot_path"])
        if snapshot.exists():
            shutil.rmtree(snapshot.parent)
            print(f"Removed snapshot: {snapshot.parent}")
    if mirror.exists():
        shutil.rmtree(mirror)
        print(f"Removed memory review mirror: {mirror}")


def compact_review_path(path: str) -> str:
    prefix = ""
    rel = path
    for candidate in ("a/before/", "b/after/", "a/after/", "b/before/"):
        if path.startswith(candidate):
            prefix = candidate[:2]
            rel = path[len(candidate) :]
            break
    else:
        for candidate in ("before/", "after/"):
            if path.startswith(candidate):
                rel = path[len(candidate) :]
                break
    return prefix + str(memory_review_relpath(Path(rel)))


def rewrite_review_patch_paths(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) == 4:
                line = f"diff --git {compact_review_path(parts[2])} {compact_review_path(parts[3])}"
        elif line.startswith("--- a/before/") or line.startswith("--- b/after/"):
            line = "--- " + compact_review_path(line[4:])
        elif line.startswith("+++ b/after/") or line.startswith("+++ a/before/"):
            line = "+++ " + compact_review_path(line[4:])
        lines.append(line)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def review_patch(args: argparse.Namespace) -> None:
    before, memory_path, _mirror = resolve_review_inputs(args)
    output = Path(args.output)
    if not output.is_absolute():
        output = Path.cwd() / output
    if not before.exists():
        raise SystemExit(f"Before snapshot does not exist: {before}")
    if not memory_path.exists():
        raise SystemExit(f"Memory path does not exist: {memory_path}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="memory-review-") as tmp:
        tmp_path = Path(tmp)
        shutil.copytree(before, tmp_path / "before", symlinks=True)
        shutil.copytree(memory_path, tmp_path / "after", symlinks=True)
        result = subprocess.run(
            ["git", "diff", "--no-index", "--", "before", "after"],
            cwd=tmp_path,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    if result.returncode not in (0, 1):
        if result.stderr:
            print(result.stderr, end="")
        raise SystemExit(result.returncode)
    if result.returncode == 0 and args.remove_empty:
        output.unlink(missing_ok=True)
        print(f"No memory changes; removed empty review patch: {output}")
        return
    output.write_text(rewrite_review_patch_paths(result.stdout), encoding="utf-8")
    print(f"Wrote memory review patch: {output}")
