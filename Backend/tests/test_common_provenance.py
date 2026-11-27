from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agrifusion_research.core.common.provenance import resolve_code_commit


class ResolveCodeCommitTests(unittest.TestCase):
    def test_resolves_branch_ref_with_nested_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            git_dir = root / ".git"
            (git_dir / "refs" / "heads" / "feature").mkdir(parents=True)
            (git_dir / "HEAD").write_text("ref: refs/heads/feature/x\n", encoding="utf-8")
            (git_dir / "refs" / "heads" / "feature" / "x").write_text("abc123\n", encoding="utf-8")
            self.assertEqual(resolve_code_commit(root), "abc123")

    def test_detached_head_and_missing_git(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.assertEqual(resolve_code_commit(root), "UNKNOWN")
            (root / ".git").mkdir()
            (root / ".git" / "HEAD").write_text("deadbeef\n", encoding="utf-8")
            self.assertEqual(resolve_code_commit(root), "deadbeef")


if __name__ == "__main__":
    unittest.main()
