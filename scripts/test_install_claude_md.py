#!/usr/bin/env python3
"""Tests for install_claude_md() in install_claude_code.py."""

import contextlib
import io
import sys
import textwrap
import unittest
from pathlib import Path

# Allow importing the installer module without running main()
sys.path.insert(0, str(Path(__file__).parent))
from install_claude_code import install_claude_md


def install_quiet(source: Path, target: Path, dry_run: bool) -> None:
    with contextlib.redirect_stdout(io.StringIO()):
        install_claude_md(source, target, dry_run=dry_run)


def dedent(s: str) -> str:
    return textwrap.dedent(s).lstrip("\n")


SOURCE_TWO_BLOCKS = dedent("""\
    <!-- zed-launch-context -->
    ## How CC Is Launched in Zed

    Terminal thread or ACP.
    <!-- zed-launch-context -->

    <!-- zed-adapter -->
    # Zed Adapter Behavior

    Adapter instructions here.
    <!-- zed-adapter -->
""")


class TestInstallClaudeMd(unittest.TestCase):

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _source(self, content: str) -> Path:
        p = self.tmp / "source.md"
        p.write_text(content)
        return p

    def _target(self, content: str = "") -> Path:
        p = self.tmp / "target.md"
        if content:
            p.write_text(content)
        return p

    # --- append when target does not exist ---

    def test_creates_target_when_missing(self):
        source = self._source(SOURCE_TWO_BLOCKS)
        target = self.tmp / "missing.md"
        install_quiet(source, target, dry_run=False)
        text = target.read_text()
        self.assertIn("<!-- zed-launch-context -->", text)
        self.assertIn("<!-- zed-adapter -->", text)

    # --- append when target exists but has no matching tags ---

    def test_appends_blocks_to_existing_content(self):
        source = self._source(SOURCE_TWO_BLOCKS)
        target = self._target("# My existing notes\n\nSome content.\n")
        install_quiet(source, target, dry_run=False)
        text = target.read_text()
        self.assertIn("# My existing notes", text)
        self.assertIn("Terminal thread or ACP.", text)
        self.assertIn("Adapter instructions here.", text)

    # --- replace in-place when tags already present ---

    def test_replaces_existing_block(self):
        old_block = dedent("""\
            <!-- zed-launch-context -->
            ## Old launch section

            Old content.
            <!-- zed-launch-context -->
        """)
        target = self._target("# Preamble\n\n" + old_block + "\n# Postamble\n")
        source = self._source(SOURCE_TWO_BLOCKS)
        install_quiet(source, target, dry_run=False)
        text = target.read_text()
        self.assertNotIn("Old content.", text)
        self.assertIn("Terminal thread or ACP.", text)
        self.assertIn("# Preamble", text)
        self.assertIn("# Postamble", text)

    # --- idempotency ---

    def test_idempotent_on_rerun(self):
        source = self._source(SOURCE_TWO_BLOCKS)
        target = self._target()
        install_quiet(source, target, dry_run=False)
        first = target.read_text()
        install_quiet(source, target, dry_run=False)
        second = target.read_text()
        self.assertEqual(first, second)

    # --- dry_run does not write ---

    def test_dry_run_does_not_write(self):
        source = self._source(SOURCE_TWO_BLOCKS)
        target = self.tmp / "dry.md"
        install_quiet(source, target, dry_run=True)
        self.assertFalse(target.exists())

    # --- source with no tagged blocks is a no-op ---

    def test_no_blocks_is_noop(self):
        source = self._source("# Just a plain file\n\nNo tags here.\n")
        target = self._target("# Existing\n")
        install_quiet(source, target, dry_run=False)
        self.assertEqual(target.read_text(), "# Existing\n")

    # --- preserves content between two blocks ---

    def test_preserves_content_between_blocks(self):
        between = "\n# My personal section\n\nKeep this.\n"
        existing = (
            dedent("""\
                <!-- zed-launch-context -->
                ## Old launch
                <!-- zed-launch-context -->
            """)
            + between
            + dedent("""\
                <!-- zed-adapter -->
                ## Old adapter
                <!-- zed-adapter -->
            """)
        )
        target = self._target(existing)
        source = self._source(SOURCE_TWO_BLOCKS)
        install_quiet(source, target, dry_run=False)
        text = target.read_text()
        self.assertIn("Keep this.", text)
        self.assertIn("Terminal thread or ACP.", text)
        self.assertIn("Adapter instructions here.", text)


if __name__ == "__main__":
    unittest.main()
