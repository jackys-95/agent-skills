"""Shared helpers for agent skill installers."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    tomllib = None


# Exclude developer-only files from the installed skill: bytecode/OS cruft plus
# test files, which ship no runtime value to an installed skill (they are never
# referenced from SKILL.md, so an agent never loads them). Covers both the flat
# `test_*.py` convention used in this repo and a `tests/` subdirectory.
COPY_IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", ".DS_Store", "test_*.py", "*_test.py", "tests"
)


def load_manifest(path: Path) -> dict:
    if tomllib is None:
        raise SystemExit("Python 3.11+ is required to read wrappers.toml")
    with path.open("rb") as handle:
        return tomllib.load(handle)


def copy_skill(skill_type: str, source: Path, target: Path, dry_run: bool) -> None:
    print(f"Install {skill_type} skill: {source} -> {target}")
    if dry_run:
        return
    try:
        shutil.copytree(
            source,
            target,
            dirs_exist_ok=True,
            copy_function=shutil.copy2,
            ignore=COPY_IGNORE,
        )
    except FileNotFoundError:
        raise SystemExit(f"Missing {skill_type} skill source: {source}")


def render(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered.rstrip() + "\n"


def install_wrapper(
    wrapper: dict[str, str],
    template: str,
    target_root: Path,
    canonical_skill_path: str,
    dry_run: bool,
    label: str = "wrapper",
) -> None:
    name = wrapper["name"]
    target = target_root / name / "SKILL.md"
    values = {
        "name": name,
        "description": wrapper["description"],
        "argument_hint": wrapper["argument_hint"],
        "workflow": wrapper["workflow"],
        "body": wrapper["body"],
        "canonical_skill_path": canonical_skill_path,
    }
    print(f"Install {label}: {target}")
    if dry_run:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(template, values), encoding="utf-8")


def install_canonical_skills(
    repo_root: Path,
    manifest: dict,
    template: str,
    target_root: Path,
    dry_run: bool,
    wrapper_label: str = "wrapper",
) -> None:
    canonical_name = manifest["canonical_skill"]
    canonical_source = repo_root / manifest["canonical_skill_source"]
    copy_skill("canonical", canonical_source, target_root / canonical_name, dry_run)

    canonical_skill_path = f"{canonical_name}/SKILL.md"
    for wrapper in manifest.get("wrappers", []):
        install_wrapper(
            wrapper,
            template,
            target_root,
            canonical_skill_path,
            dry_run,
            label=wrapper_label,
        )


def install_plain_skills(
    repo_root: Path,
    manifest: dict,
    target_root: Path,
    dry_run: bool,
) -> None:
    for skill in manifest.get("skills", []):
        source = repo_root / skill["source"]
        copy_skill("plain", source, target_root / skill["name"], dry_run)


def install_qmd_skill(dry_run: bool) -> None:
    qmd = shutil.which("qmd")
    if not qmd:
        pm = "bun" if shutil.which("bun") else "npm"
        print(f"qmd not found - installing via {pm}...")
        if not dry_run:
            subprocess.run([pm, "install", "-g", "@tobilu/qmd"], check=True)

    cmd = ["qmd", "skill", "install", "--global", "--yes"]
    print(f"Install qmd skill: {' '.join(cmd)}")
    if dry_run:
        return
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("  (qmd skill already installed or install skipped - continuing)")


def install_tagged_blocks(
    source: Path,
    target: Path,
    dry_run: bool,
    label: str,
    tags=None,
) -> None:
    """Upsert tagged markdown blocks from source into target."""
    source_text = source.read_text(encoding="utf-8")
    block_re = re.compile(r"(<!-- (\S+) -->.*?<!-- \2 -->)", re.DOTALL)
    blocks = block_re.findall(source_text)
    if tags is not None:
        blocks = [block for block in blocks if block[1] in tags]
    if not blocks:
        return

    print(f"Install {label} blocks: {target}")
    if dry_run:
        return

    target_text = target.read_text(encoding="utf-8") if target.exists() else ""
    for block_content, tag in blocks:
        existing = re.compile(
            r"<!-- " + re.escape(tag) + r" -->.*?<!-- " + re.escape(tag) + r" -->",
            re.DOTALL,
        )
        if existing.search(target_text):
            target_text = existing.sub(block_content, target_text)
        else:
            separator = "\n\n" if target_text.strip() else ""
            target_text = target_text.rstrip("\n") + separator + block_content + "\n"

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(target_text, encoding="utf-8")
