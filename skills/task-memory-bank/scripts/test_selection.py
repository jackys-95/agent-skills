#!/usr/bin/env python3
"""Unit tests for the selection module: ranking, work-item parsing, candidate gathering.

Run: python3 test_selection.py

Stdlib only (unittest + tempfile). No network, no qmd, no git — the pure logic
(resume ordering, work-index parsing, and the candidate-gathering spine) is tested
directly against on-disk fixtures. Bank discovery and git signals shell out and are
verified by the CLI smoke tests, not here.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import selection as sel


def _mk_bank(projects: dict[str, dict]) -> Path:
    """Build a throwaway bank: {collection_name: {repos, work: {wid: status}}}."""
    root = Path(tempfile.mkdtemp())
    (root / ".memory-bank").mkdir(parents=True)
    blocks = ["collections:"]
    for cname, spec in projects.items():
        project = cname[3:] if cname.startswith("mb-") else cname
        pdir = root / "projects" / project
        pdir.mkdir(parents=True, exist_ok=True)
        blocks.append(f"  {cname}:")
        blocks.append(f"    path: {pdir}")
        blocks.append("    kind: project")
        blocks.append(f"    project: {project}")
        if spec.get("description"):
            blocks.append(f"    description: {spec['description']}")
        repos = spec.get("repos", [])
        if repos:
            blocks.append("    repos:")
            blocks.extend(f"      - {r}" for r in repos)
        else:
            blocks.append("    repos: []")
        blocks.append(f"    context: {project}")
        for wid, status in spec.get("work", {}).items():
            _mk_work_item(pdir, wid, status)
    (root / ".memory-bank" / "collections.yaml").write_text("\n".join(blocks) + "\n", encoding="utf-8")
    return root


def _mk_work_item(pdir: Path, wid: str, status: str, title: str | None = None) -> Path:
    prefix = wid.split("-")[0]
    plural = {"EPIC": "epics", "STORY": "stories", "TASK": "tasks", "SPIKE": "spikes"}[prefix]
    wdir = pdir / "work" / plural / f"{wid}-example-slug"
    wdir.mkdir(parents=True, exist_ok=True)
    (wdir / "README.md").write_text(
        f"# {wid}: {title or 'Example Title'}\n\n## Status\n\n{status}\n", encoding="utf-8"
    )
    return wdir


class ResumeOrderTests(unittest.TestCase):
    def test_in_progress_is_most_resumable(self):
        self.assertLess(sel.resume_sort_key("in-progress"), sel.resume_sort_key("open"))

    def test_paused_outranks_blocked(self):
        # Deliberately parked work is more resumable than externally-stuck work.
        self.assertLess(sel.resume_sort_key("paused"), sel.resume_sort_key("blocked"))

    def test_open_outranks_terminal(self):
        self.assertLess(sel.resume_sort_key("open"), sel.resume_sort_key("done"))

    def test_unknown_status_sorts_last(self):
        self.assertGreater(sel.resume_sort_key("bogus"), sel.resume_sort_key("superseded"))


class ReadWorkItemTests(unittest.TestCase):
    def test_reads_id_type_status_title(self):
        d = Path(tempfile.mkdtemp())
        wdir = _mk_work_item(d, "TASK-0007", "in-progress", title="Fix the thing")
        item = sel.read_work_item(wdir)
        self.assertEqual(item["id"], "TASK-0007")
        self.assertEqual(item["type"], "task")
        self.assertEqual(item["status"], "in-progress")
        self.assertEqual(item["title"], "Fix the thing")

    def test_off_vocabulary_status_falls_back_to_open(self):
        d = Path(tempfile.mkdtemp())
        wdir = _mk_work_item(d, "TASK-0001", "active")  # legacy/hand-edited off-vocab value
        self.assertEqual(sel.read_work_item(wdir)["status"], "open")

    def test_non_work_dir_returns_none(self):
        d = Path(tempfile.mkdtemp())
        (d / "not-a-work-item").mkdir()
        self.assertIsNone(sel.read_work_item(d / "not-a-work-item"))

    def test_title_falls_back_to_slug(self):
        d = Path(tempfile.mkdtemp())
        wdir = d / "work" / "tasks" / "TASK-0003-saved-filter-state"
        wdir.mkdir(parents=True)
        # README with no `# WID: title` line at all.
        (wdir / "README.md").write_text("## Status\n\nopen\n", encoding="utf-8")
        self.assertEqual(sel.read_work_item(wdir)["title"], "Saved Filter State")


class ScanAndIndexTests(unittest.TestCase):
    def test_scan_sorts_in_progress_before_open(self):
        root = _mk_bank({"mb-x": {"work": {"TASK-0001": "open", "TASK-0002": "in-progress"}}})
        pdir = root / "projects" / "x"
        items = sel.scan_work_items(pdir)
        self.assertEqual(items[0]["id"], "TASK-0002")  # in-progress first

    def test_regen_index_lists_all_items_resume_ordered(self):
        root = _mk_bank({"mb-x": {"work": {
            "TASK-0001": "done", "TASK-0002": "in-progress", "TASK-0003": "open"}}})
        pdir = root / "projects" / "x"
        index = sel.regen_work_index(pdir)
        text = index.read_text(encoding="utf-8")
        self.assertIn("| ID | Type | Status | Title | Created |", text)
        # in-progress ranks above open ranks above done.
        self.assertLess(text.index("TASK-0002"), text.index("TASK-0003"))
        self.assertLess(text.index("TASK-0003"), text.index("TASK-0001"))

    def test_append_row_idempotent(self):
        root = _mk_bank({"mb-x": {}})
        pdir = root / "projects" / "x"
        sel.append_work_index_row(pdir, "TASK-0009", "task", "open", "First")
        sel.append_work_index_row(pdir, "TASK-0009", "task", "open", "First")
        text = (pdir / "work" / "index.md").read_text(encoding="utf-8")
        self.assertEqual(text.count("TASK-0009"), 1)


class GatherCandidatesTests(unittest.TestCase):
    def test_matches_by_repo_association(self):
        root = _mk_bank({"mb-x": {"repos": ["/repo/x"], "work": {"TASK-0001": "open"}}})
        out = sel.gather_candidates({sel.normalize_path("/repo/x")}, [root])
        self.assertEqual(len(out["candidates"]), 1)
        self.assertEqual(out["candidates"][0]["collection"], "mb-x")
        self.assertFalse(out["conflict"])

    def test_no_match_reports_searched_banks(self):
        root = _mk_bank({"mb-x": {"repos": ["/repo/x"]}})
        out = sel.gather_candidates({sel.normalize_path("/repo/unmapped")}, [root])
        self.assertEqual(out["candidates"], [])
        self.assertEqual(len(out["searched_banks"]), 1)
        self.assertEqual(out["searched_banks"][0]["projects"], 1)
        self.assertEqual(out["searched_banks"][0]["repos"], 1)

    def test_multiple_candidates_flag_conflict_and_rank_by_status(self):
        root = _mk_bank({
            "mb-a": {"repos": ["/shared"], "work": {"TASK-0001": "open"}},
            "mb-b": {"repos": ["/shared"], "work": {"TASK-0001": "in-progress"}},
        })
        out = sel.gather_candidates({sel.normalize_path("/shared")}, [root])
        self.assertTrue(out["conflict"])
        self.assertEqual(len(out["candidates"]), 2)
        # in-progress project ranks first.
        self.assertEqual(out["candidates"][0]["collection"], "mb-b")

    def test_union_across_two_banks(self):
        bank1 = _mk_bank({"mb-a": {"repos": ["/r"]}})
        bank2 = _mk_bank({"mb-b": {"repos": ["/r"]}})
        out = sel.gather_candidates({sel.normalize_path("/r")}, [bank1, bank2])
        names = {c["collection"] for c in out["candidates"]}
        self.assertEqual(names, {"mb-a", "mb-b"})

    def test_terminal_only_project_has_empty_active_work(self):
        root = _mk_bank({"mb-x": {"repos": ["/r"], "work": {"TASK-0001": "shipped"}}})
        out = sel.gather_candidates({sel.normalize_path("/r")}, [root])
        c = out["candidates"][0]
        self.assertEqual(c["active_work"], [])
        self.assertEqual(c["top_status"], "")

    def test_association_count_breaks_status_tie(self):
        # Both open; the project matching more of the repo signals ranks first.
        root = _mk_bank({
            "mb-a": {"repos": ["/one"], "work": {"TASK-0001": "open"}},
            "mb-b": {"repos": ["/one", "/two"], "work": {"TASK-0001": "open"}},
        })
        signals = {sel.normalize_path("/one"), sel.normalize_path("/two")}
        out = sel.gather_candidates(signals, [root])
        self.assertEqual(out["candidates"][0]["collection"], "mb-b")


if __name__ == "__main__":
    unittest.main(verbosity=2)
