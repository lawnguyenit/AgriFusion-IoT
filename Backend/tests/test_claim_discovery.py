from __future__ import annotations

import unittest

import pandas as pd

from Backend.Benchmark.claim_discovery.inventory import build_evidence_inventory, flatten_column_roles


class ClaimDiscoveryInventoryTests(unittest.TestCase):
    def test_generates_only_relative_candidates_for_registered_measurements(self) -> None:
        frame = pd.DataFrame({
            "sample_id": [f"s{i}" for i in range(120)],
            "timestamp": pd.date_range("2024-01-01", periods=120, freq="h"),
            "sensor.co": range(120),
            "criterion.co_gt_mg_m3": range(120),
            "water_volume_m3": range(120),
            "device_id": ["dev-a"] * 120,
        })
        manifest = {
            "dataset_id": "test_air",
            "column_roles": {
                "sensor.co": "measurement",
                "criterion.co_gt_mg_m3": "criterion_only",
                "water_volume_m3": "posthoc_operational_evidence",
            },
        }

        inventory, metadata = build_evidence_inventory(frame, manifest)
        by_field = inventory.set_index("field")

        self.assertEqual(by_field.loc["sensor.co", "candidate_status"], "RELATIVE_STATE_CANDIDATE")
        self.assertEqual(by_field.loc["criterion.co_gt_mg_m3", "candidate_status"], "NO_AUTOMATIC_LABEL_CANDIDATE")
        self.assertEqual(by_field.loc["water_volume_m3", "candidate_status"], "NO_AUTOMATIC_LABEL_CANDIDATE")
        self.assertFalse(metadata["semantic_claims_auto_inferred"])
        self.assertEqual(metadata["cadence"]["median_minutes"], 60.0)
        self.assertEqual(metadata["criterion_role_columns"], ["criterion.co_gt_mg_m3"])

    def test_flattens_grouped_stuard_role_manifest(self) -> None:
        roles = flatten_column_roles({
            "column_roles": {
                "measurements": ["soil_moisture_pct", "air_humidity_pct"],
                "posthoc_operational_evidence": ["water_volume_m3"],
            }
        })
        self.assertEqual(roles["soil_moisture_pct"], "measurement")
        self.assertEqual(roles["water_volume_m3"], "operational_evidence")

    def test_unregistered_numeric_field_is_not_auto_labeled(self) -> None:
        frame = pd.DataFrame({"sample_id": ["a", "b"], "raw_code": [1, 2]})
        inventory, _ = build_evidence_inventory(frame, {"dataset_id": "test"}, min_observations=1)
        row = inventory.iloc[0]
        self.assertEqual(row["role"], "unclassified")
        self.assertEqual(row["candidate_claims"], [])

    def test_cadence_is_computed_per_entity_and_datetime_sidecars_are_not_numeric(self) -> None:
        frame = pd.DataFrame({
            "sample_id": ["a", "b", "c", "d"],
            "timestamp": pd.to_datetime([
                "2024-01-01T00:00:00Z", "2024-01-01T00:10:00Z",
                "2024-01-01T00:00:05Z", "2024-01-01T00:10:05Z",
            ]),
            "entity_id": ["line_1", "line_1", "line_2", "line_2"],
            "water_timestamp": pd.to_datetime([
                "2024-01-01T00:00:00Z", None, "2024-01-01T00:00:00Z", None,
            ]),
            "soil_value": [1.0, 2.0, 3.0, 4.0],
        })
        inventory, metadata = build_evidence_inventory(
            frame,
            {"dataset_id": "test_entities", "column_roles": {"soil_value": "measurement"}},
            min_observations=1,
        )
        by_field = inventory.set_index("field")
        self.assertAlmostEqual(metadata["cadence"]["median_minutes"], 10.0)
        self.assertEqual(metadata["cadence"]["per_entity"]["line_1"]["median_minutes"], 10.0)
        self.assertFalse(by_field.loc["water_timestamp", "numeric"])
        self.assertEqual(by_field.loc["water_timestamp", "role"], "temporal_alignment_metadata")

    def test_feature_catalog_defines_measurements_without_labeling_rule_proxy_fields(self) -> None:
        frame = pd.DataFrame({"sht.temp_c": [10.0, 11.0], "delivery.buffer_reason": ["none", "retry"]})
        catalog = pd.DataFrame({
            "canonical_name": ["sht.temp_c", "delivery.buffer_reason"],
            "feature_role": ["measurement", "rule_proxy"],
        })
        inventory, _ = build_evidence_inventory(
            frame,
            {"dataset_id": "firebase"},
            min_observations=1,
            feature_catalog=catalog,
        )
        by_field = inventory.set_index("field")
        self.assertEqual(by_field.loc["sht.temp_c", "candidate_status"], "RELATIVE_STATE_CANDIDATE")
        self.assertEqual(by_field.loc["delivery.buffer_reason", "candidate_status"], "NO_AUTOMATIC_LABEL_CANDIDATE")


if __name__ == "__main__":
    unittest.main()
