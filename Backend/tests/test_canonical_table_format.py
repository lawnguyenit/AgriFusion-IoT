from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from Backend.Config.storage import read_table
from Backend.Navigation.Core.layer1.writers.canonical import CanonicalOutputWriter


class CanonicalTableFormatTests(unittest.TestCase):
    def test_writer_always_writes_parquet_and_read_table_roundtrips(self) -> None:
        frame = pd.DataFrame({"record.id": ["a", "b"], "sht.temp_c": [21.5, None]})
        with tempfile.TemporaryDirectory() as temp_dir:
            writer = CanonicalOutputWriter(Path(temp_dir))
            writer.ensure_directories()
            path, fmt = writer.write_history(frame)
            self.assertEqual(path.suffix, ".parquet")
            self.assertEqual(fmt, "parquet:pyarrow")
            self.assertFalse(path.with_suffix(".csv").exists())
            pd.testing.assert_frame_equal(read_table(path), frame)

    def test_read_table_picks_reader_by_extension(self) -> None:
        frame = pd.DataFrame({"x": [1, 2]})
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "t.csv"
            frame.to_csv(csv_path, index=False)
            pd.testing.assert_frame_equal(read_table(csv_path, low_memory=False), frame)
            with self.assertRaises(ValueError):
                read_table(Path(temp_dir) / "t.json")


if __name__ == "__main__":
    unittest.main()
