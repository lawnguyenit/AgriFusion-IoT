"""B10: Phase A reads the canonical history through agrifusion.io.read_table (parquet or csv)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from Backend.tests.golden_chain_support import run_chain
from agrifusion_research.core.protocol_registry import build_protocol_registry, load_protocol_registry
from agrifusion_research.experiments.weak_labels_phases.phase_a_readiness.canonical import load_canonical_audit_inputs

PROTOCOL_CONFIG = (
    Path(__file__).resolve().parents[2]
    / "research" / "agrifusion_research" / "core" / "protocol_registry" / "config" / "protocol_v1.yaml"
)


class PhaseACanonicalFormatTests(unittest.TestCase):
    def test_parquet_and_csv_give_the_same_structural_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_chain(root)
            layer1 = root / "output" / "Layer1"
            parquet_path = layer1 / "canonical" / "telemetry_history.parquet"
            manifest_path = layer1 / "manifest.json"
            registry = load_protocol_registry(build_protocol_registry(PROTOCOL_CONFIG, manifest_path, output_root=root / "reg"))
            csv_path = root / "telemetry_history.csv"
            pd.read_parquet(parquet_path).to_csv(csv_path, index=False)

            from_parquet = load_canonical_audit_inputs(parquet_path, manifest_path, registry)
            from_csv = load_canonical_audit_inputs(csv_path, manifest_path, registry)

            self.assertEqual(from_parquet[5]["canonical_history_format"], "parquet")
            self.assertEqual(from_parquet[5]["canonical_record_hash_method"], "stable_digest_of_row_values")
            self.assertEqual(from_csv[5]["canonical_record_hash_method"], "sha256_of_raw_csv_line")
            structural_parquet, structural_csv = from_parquet[0], from_csv[0]
            self.assertGreater(len(structural_parquet), 0)
            for column in ("record.id", "environment_id", "logical_measurement_fingerprint"):
                self.assertEqual(
                    structural_parquet[column].astype(str).tolist(),
                    structural_csv[column].astype(str).tolist(),
                    column,
                )
            self.assertTrue(structural_parquet["canonical_record_hash"].astype(str).str.len().eq(64).all())


if __name__ == "__main__":
    unittest.main()
