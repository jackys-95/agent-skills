from __future__ import annotations

import datetime as dt
import re
import subprocess
import sys
from pathlib import Path


WORK_TYPES = {
    "epic": ("EPIC", "epics"),
    "story": ("STORY", "stories"),
    "task": ("TASK", "tasks"),
    "spike": ("SPIKE", "spikes"),
}


def expand(path: str) -> Path:
    return Path(path).expanduser().resolve()


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9_-]+", "-", value)
    value = re.sub(r"-{2,}", "-", value)
    return value.strip("-_") or "item"


def display_title(slug_or_title: str) -> str:
    return slug_or_title.replace("_", " ").replace("-", " ").strip().title()


def today() -> str:
    return dt.date.today().isoformat()


def write_new(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(content.rstrip() + "\n", encoding="utf-8")


def append_once(path: Path, marker: str, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if marker in current:
            return
        path.write_text(current.rstrip() + "\n\n" + content.rstrip() + "\n", encoding="utf-8")
    else:
        path.write_text(content.rstrip() + "\n", encoding="utf-8")


def project_dir(root: Path, project: str) -> Path:
    return root / "projects" / project


def collection_name(project: str) -> str:
    return "mb-" + project.replace("_", "-")


def normalize_path(path: str | None) -> str:
    if not path:
        return ""
    return str(expand(path))


def current_git_root() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if result.returncode != 0:
        return ""
    return str(expand(result.stdout.strip()))


def parse_collections(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    collections: dict[str, dict[str, str]] = {}
    current: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.lstrip().startswith("#") or line == "collections:":
            continue
        top_match = re.match(r"^  ([A-Za-z0-9_.-]+):\s*$", line)
        if top_match:
            current = top_match.group(1)
            collections[current] = {}
            continue
        kv_match = re.match(r"^    ([A-Za-z0-9_.-]+):\s*(.*)\s*$", line)
        if kv_match and current:
            key, value = kv_match.groups()
            collections[current][key] = value.strip().strip("\"'")
    return collections


def write_collections(path: Path, collections: dict[str, dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["collections:"]
    for name, fields in collections.items():
        lines.append(f"  {name}:")
        for key, value in fields.items():
            lines.append(f"    {key}: {value}")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def run_command(command: list[str], optional: bool = False) -> bool:
    print("+ " + " ".join(command))
    result = subprocess.run(command, check=False)
    if result.returncode == 0:
        return True
    if optional:
        print(
            f"Warning: optional command failed with exit code {result.returncode}: {' '.join(command)}",
            file=sys.stderr,
        )
        return False
    raise SystemExit(result.returncode)
