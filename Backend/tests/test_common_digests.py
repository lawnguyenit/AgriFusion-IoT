"""core.common.digests is the single home of hash helpers; its two families stay distinct."""
from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from agrifusion_research.core.common import digests
from agrifusion_research.core.dataset_views import validators

RESEARCH = Path(__file__).resolve().parents[2] / "research" / "agrifusion_research"


class DigestFamiliesTests(unittest.TestCase):
    def test_dataset_views_reexports_are_the_common_functions(self) -> None:
        for name in ("file_sha256", "stable_hash_object", "hash_dataframe_rows", "dataframe_schema_hash"):
            self.assertIs(getattr(validators, name), getattr(digests, name))

    def test_families_agree_on_ints_and_strings_but_not_floats_or_none(self) -> None:
        self.assertEqual(digests.stable_hash_object({"a": 1, "b": "x"}), digests.stable_digest({"a": 1, "b": "x"}))
        self.assertNotEqual(digests.stable_hash_object({"a": 1.5}), digests.stable_digest({"a": 1.5}))
        self.assertNotEqual(digests.stable_hash_object({"a": None}), digests.stable_digest({"a": None}))
        frame = pd.DataFrame({"sample_id": ["a", "b"], "x": [1.5, None]})
        self.assertNotEqual(digests.hash_dataframe_rows(frame), digests.dataframe_digest(frame, columns=["sample_id", "x"]))

    def test_raw_hash_values_are_pinned(self) -> None:
        """Pinned so a refactor cannot silently change hashes stored in existing artifacts."""
        frame = pd.DataFrame({"sample_id": ["a", "b"], "x": [1.5, None], "n": [1, 2]})
        self.assertEqual(digests.hash_dataframe_rows(frame), "02f1c3f0cd7be5800fb19944328295cd169ce0e798dc32eb385fc6b12f860e81")
        self.assertEqual(digests.dataframe_digest(frame, columns=list(frame.columns)), "61ffe306cd952c1fdf3462232b97e70e79046c7d704e7cf45cf0829b4480743a")

    def test_file_and_bytes_hash_agree(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "f.bin"
            path.write_bytes(b"agrifusion" * 1000)
            self.assertEqual(digests.file_sha256(path), digests.bytes_sha256(path.read_bytes()))

    def test_no_sha256_helper_defined_outside_common_digests(self) -> None:
        offending = []
        for path in RESEARCH.rglob("*.py"):
            if path.name == "digests.py" and path.parent.name == "common":
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.FunctionDef) and "sha256" in node.name:
                    offending.append(f"{path.relative_to(RESEARCH)}:{node.lineno} {node.name}")
        self.assertEqual(offending, [])


if __name__ == "__main__":
    unittest.main()
