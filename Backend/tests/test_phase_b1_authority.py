from __future__ import annotations

import tempfile
import unittest
import hashlib
from pathlib import Path

import pandas as pd

from Backend.Benchmark.weak_labels.lifecycle.phase_b_contract.threshold_audit import (
    build_candidate_threshold_audit,
    load_phase_a_threshold_inputs,
)


class PhaseB1AuthorityTests(unittest.TestCase):
    def _write_phase_a_thresholds(self, root: Path, values: dict[str, float]) -> Path:
        run = root / "phase_a"
        threshold_dir = run / "threshold_diagnostics"
        threshold_dir.mkdir(parents=True)
        rows = []
        for q in (5, 10, 15, 20):
            rows.append(
                {
                    "threshold_id": f"LOW_MOISTURE_Q{q:02d}_E1_DISCOVERY_CANDIDATE",
                    "threshold_value": values[f"Q{q:02d}"],
                    "threshold_unit": "percent",
                    "threshold_role": "PHASE_A_CANDIDATE",
                    "fit_mode": "DISCOVERY_QUANTILE",
                    "fit_cohort_id": "E1_DISCOVERY_TRAIN_V1",
                }
            )
        rows.extend(
            [
                {
                    "threshold_id": "THERMAL_VPD_FIXED_2_5_REFERENCE",
                    "threshold_value": 2.5,
                    "threshold_unit": "kPa",
                    "threshold_role": "PHASE_A_REFERENCE_CANDIDATE",
                    "fit_mode": "FIXED_REFERENCE",
                    "fit_cohort_id": "NONE",
                },
                {
                    "threshold_id": "MOISTURE_RISE_FIXED_5PP_REFERENCE",
                    "threshold_value": 5.0,
                    "threshold_unit": "percentage_points",
                    "threshold_role": "PHASE_A_REFERENCE_CANDIDATE",
                    "fit_mode": "FIXED_REFERENCE",
                    "fit_cohort_id": "NONE",
                },
                {
                    "threshold_id": "EC_SHIFT_Q95_E1_DISCOVERY_CANDIDATE",
                    "threshold_value": 6.0,
                    "threshold_unit": "canonical_ec_unit_required",
                    "threshold_role": "PHASE_A_CANDIDATE",
                    "fit_mode": "DISCOVERY_QUANTILE",
                    "fit_cohort_id": "E1_DISCOVERY_TRAIN_V1",
                },
            ]
        )
        registry = pd.DataFrame(rows)
        registry.to_csv(threshold_dir / "threshold_registry.csv", index=False)
        pd.DataFrame(
            [
                {
                    "threshold_family": "LOW_MOISTURE",
                    "q05": values["Q05"],
                    "q10": values["Q10"],
                    "q15": values["Q15"],
                    "q20": values["Q20"],
                }
            ]
        ).to_csv(threshold_dir / "threshold_sensitivity.csv", index=False)
        pd.DataFrame(
            [
                {
                    "record_id": "r1",
                    "sample_time": "2026-04-01T00:00:00+07:00",
                    "npk_soil_moisture_pct": 50.0,
                    "ec_delta_abs_strict": 0.0,
                }
            ]
        ).to_parquet(threshold_dir / "threshold_fit_cohort_records.parquet", index=False)
        catalog_dir = run / "run_metadata"
        catalog_dir.mkdir(parents=True)
        catalog_rows = []
        for path in sorted(threshold_dir.iterdir()):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            catalog_rows.append(
                {
                    "relative_path": str(path.relative_to(run)).replace("\\", "/"),
                    "file_hash": digest,
                }
            )
        pd.DataFrame(catalog_rows).to_csv(catalog_dir / "artifact_catalog.csv", index=False)
        return run

    def test_loader_uses_phase_a_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run = self._write_phase_a_thresholds(
                Path(temp), {"Q05": 11.0, "Q10": 22.0, "Q15": 33.0, "Q20": 44.0}
            )
            inputs = load_phase_a_threshold_inputs(run)
            self.assertEqual(inputs.q_values, (("Q05", 11.0), ("Q10", 22.0), ("Q15", 33.0), ("Q20", 44.0)))

    def test_threshold_audit_calculates_ties_from_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            inputs = load_phase_a_threshold_inputs(
                self._write_phase_a_thresholds(
                    Path(temp), {"Q05": 10.0, "Q10": 20.0, "Q15": 30.0, "Q20": 40.0}
                )
            )
            evidence = pd.DataFrame(
                [
                    {
                        "record.id": "r1",
                        "sample_time": "2026-04-01",
                        "low_evidence_value": 20.0,
                        "thermal_evidence_value": 2.5,
                        "moisture_rise_evidence_value": 5.0,
                        "ec_shift_evidence_value": 6.0,
                    },
                    {
                        "record.id": "r2",
                        "sample_time": "2026-04-01",
                        "low_evidence_value": 25.0,
                        "thermal_evidence_value": 1.0,
                        "moisture_rise_evidence_value": 0.0,
                        "ec_shift_evidence_value": 0.0,
                    },
                ]
            )
            applicability = pd.DataFrame(
                [
                    {
                        "record.id": "r1",
                        "low_rule_applicability": True,
                        "thermal_rule_applicability": True,
                        "rise_rule_applicability": True,
                        "ec_shift_rule_applicability": True,
                    },
                    {
                        "record.id": "r2",
                        "low_rule_applicability": True,
                        "thermal_rule_applicability": True,
                        "rise_rule_applicability": True,
                        "ec_shift_rule_applicability": True,
                    },
                ]
            )
            audit, boundaries, status = build_candidate_threshold_audit(evidence, applicability, inputs)
            ec = audit.loc[audit["evidence_id"] == "ec_shift"].iloc[0]
            self.assertEqual(int(ec["equal_to_threshold_count"]), 1)
            self.assertEqual(len(boundaries), 4)
            self.assertEqual(status["ec_shift_viability"], "PHASE_B_DECISION_REQUIRED")
            self.assertTrue(audit["authority_status"].eq("CANDIDATE_ONLY").all())


if __name__ == "__main__":
    unittest.main()
