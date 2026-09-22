from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from Backend.Benchmark.weak_labels.lifecycle.phase_b_contract import PhaseBConfig, build_phase_b_decision_pack
from Backend.Benchmark.weak_labels.lifecycle.phase_b_contract.resolution import build_point_contract_replay


ROOT = Path(__file__).resolve().parents[2]
PHASE_A = ROOT / "Backend" / "Benchmark" / "weak_labels" / "artifacts" / "legacy" / "phase_a_readiness_legacy" / "phase_a_readiness_20260731_003845"
REGISTRY = ROOT / "Backend" / "Benchmark" / "protocol_registry" / "artifacts" / "protocol_registry_20260731_003841"
CANONICAL = ROOT / "Backend" / "Output_data" / "Layer1" / "canonical" / "telemetry_history.csv"


class SemanticContractUnitTests(unittest.TestCase):
    def test_missing_context_is_not_environmental_unresolved(self) -> None:
        applicability = pd.DataFrame(
            [
                {"record.id": "r1", "low_target_eligibility": True, "thermal_rule_applicability": True, "rise_rule_applicability": False, "ec_shift_rule_applicability": False},
                {"record.id": "r2", "low_target_eligibility": True, "thermal_rule_applicability": True, "rise_rule_applicability": True, "ec_shift_rule_applicability": True},
            ]
        )
        primitive = pd.DataFrame(
            [
                {"record.id": "r1", "low_flag": False, "thermal_flag": False, "moisture_rise_flag": pd.NA, "ec_shift_flag": pd.NA},
                {"record.id": "r2", "low_flag": False, "thermal_flag": True, "moisture_rise_flag": False, "ec_shift_flag": False},
            ]
        ).convert_dtypes()
        replay, matrix, counts = build_point_contract_replay(applicability, primitive)
        self.assertEqual(replay["point_resolution"].tolist(), ["POINT_CONTEXT_INCOMPLETE", "UNRESOLVED_ENVIRONMENTAL"])
        self.assertEqual(set(counts["point_resolution"]), {"POINT_CONTEXT_INCOMPLETE", "UNRESOLVED_ENVIRONMENTAL"})
        self.assertEqual(len(matrix), 81)

    def test_real_phase_b1_pack_has_expected_snapshot_and_geometry(self) -> None:
        if not (PHASE_A / "phase_a_readiness.yaml").exists():
            self.skipTest("Phase A snapshot required by the B1 integration test is unavailable.")
        with tempfile.TemporaryDirectory() as temp_dir:
            result = build_phase_b_decision_pack(
                PhaseBConfig(PHASE_A, REGISTRY, CANONICAL, Path(temp_dir))
            )
            self.assertEqual(result.status, "SEMANTIC_REVIEW_REQUIRED")
            counts = pd.read_csv(result.output_dir / "resolution" / "point_resolution_snapshot.csv")
            observed = dict(zip(counts["point_resolution"], counts["row_count"]))
            self.assertEqual(observed["POINT_CONTEXT_INCOMPLETE"], 862)
            self.assertEqual(observed["UNRESOLVED_ENVIRONMENTAL"], 146)
            geometry = pd.read_csv(result.output_dir / "operationalization" / "k_regime_registry.csv")
            q10_k3 = geometry.loc[(geometry.q_contract_id == "Q10") & (geometry.k == 3)].iloc[0]
            self.assertEqual(int(q10_k3.persistent_anchor_count), 150)
            self.assertEqual(int(q10_k3.max_run_length), 14)
            manifest = json.loads((result.output_dir / "run_metadata" / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["primary_selection_status"], "REVIEW_REQUIRED")
            self.assertIsNone(manifest["selected_primary_operationalization"])
            self.assertEqual(manifest["authority_status"], "CANDIDATE_ONLY")
            self.assertFalse(manifest["labels_materialized"])
