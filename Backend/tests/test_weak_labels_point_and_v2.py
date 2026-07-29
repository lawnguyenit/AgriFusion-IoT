from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd
import yaml

from Backend.Benchmark.weak_labels import WeakLabelsConfig, build_weak_labels
from Backend.tests.dataset_views_helpers import create_dataset_views_v2_fixture


class WeakLabelsPointAndV2Tests(unittest.TestCase):
    def test_point_and_v2_contracts_hold_on_v2_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v2_fixture(Path(temp_dir))
            result = build_weak_labels(
                WeakLabelsConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "weak_labels_artifacts",
                )
            )

            output_dir = result.output_dir
            point_dir = output_dir / "point"
            v2_dir = output_dir / "v2"
            registry_dir = output_dir / "registries"
            metadata_dir = output_dir / "run_metadata"
            for path in (
                point_dir / "point_evidence_flags.parquet",
                point_dir / "point_labels_detailed.parquet",
                point_dir / "point_labels_train.parquet",
                point_dir / "technical_labels_audit.parquet",
                v2_dir / "v2_same_y_labels.parquet",
                v2_dir / "v2_temporal_evidence_3h.parquet",
                v2_dir / "v2_temporal_evidence_8h.parquet",
                v2_dir / "v2_temporal_labels_3h.parquet",
                v2_dir / "v2_temporal_labels_8h.parquet",
                registry_dir / "label_dependency_registry.csv",
                metadata_dir / "run_manifest.json",
                metadata_dir / "current_scope_summary.json",
                output_dir / "ARTIFACT_GUIDE.md",
            ):
                self.assertTrue(path.exists(), str(path))

            point_train_df = pd.read_parquet(point_dir / "point_labels_train.parquet")
            point_detailed_df = pd.read_parquet(point_dir / "point_labels_detailed.parquet")
            v2_same_y_df = pd.read_parquet(v2_dir / "v2_same_y_labels.parquet")
            v2_evidence_3h_df = pd.read_parquet(v2_dir / "v2_temporal_evidence_3h.parquet")
            v2_evidence_8h_df = pd.read_parquet(v2_dir / "v2_temporal_evidence_8h.parquet")
            v2_temporal_3h_df = pd.read_parquet(v2_dir / "v2_temporal_labels_3h.parquet")
            v2_temporal_8h_df = pd.read_parquet(v2_dir / "v2_temporal_labels_8h.parquet")
            audit_assignment_df = pd.read_parquet(output_dir / "audit" / "label_assignment.parquet")
            audit_rule_firings_df = pd.read_parquet(output_dir / "audit" / "rule_firings.parquet")
            audit_rule_registry_df = pd.read_csv(output_dir / "audit" / "rule_registry.csv")
            dependency_df = pd.read_csv(registry_dir / "label_dependency_registry.csv")
            label_registry = yaml.safe_load((registry_dir / "label_registry.yaml").read_text(encoding="utf-8"))
            current_scope_summary = json.loads((metadata_dir / "current_scope_summary.json").read_text(encoding="utf-8"))
            guide_text = (output_dir / "ARTIFACT_GUIDE.md").read_text(encoding="utf-8")

            v0_df = point_train_df.loc[point_train_df["task_id"].astype("string") == "v0_point_train", ["sample_id", "label_name", "label_status"]]
            v1_df = point_train_df.loc[point_train_df["task_id"].astype("string") == "v1_point_train", ["sample_id", "label_name", "label_status"]]
            point_join = v0_df.merge(v1_df, on="sample_id", how="inner", suffixes=("_v0", "_v1"))
            self.assertFalse(point_join.empty)
            self.assertTrue((point_join["label_name_v0"].astype("string") == point_join["label_name_v1"].astype("string")).all())
            self.assertTrue((point_join["label_status_v0"].astype("string") == point_join["label_status_v1"].astype("string")).all())

            point_lookup = v0_df.rename(columns={"label_name": "point_label_name", "label_status": "point_label_status"})
            for task_id in ("v2_same_y_3h", "v2_same_y_8h"):
                same_y_task_df = v2_same_y_df.loc[v2_same_y_df["task_id"].astype("string") == task_id].copy()
                joined = same_y_task_df.merge(point_lookup, on="sample_id", how="inner")
                eligible = joined["intrinsic_eligibility"].fillna(False).astype(bool)
                self.assertTrue(
                    (
                        joined.loc[eligible, "label_name"].astype("string")
                        == joined.loc[eligible, "point_label_name"].astype("string")
                    ).all()
                )
                self.assertTrue(joined.loc[~eligible, "label_name"].isna().all())

            invalid_point = point_detailed_df.loc[point_detailed_df["sample_id"].astype("string") == "r8"].iloc[0]
            self.assertEqual(str(invalid_point["label_name"]), "excluded_technical_invalid")
            self.assertFalse(bool(invalid_point["intrinsic_eligibility"]))

            self._assert_v2_temporal_contract(v2_temporal_3h_df, v2_evidence_3h_df)
            self._assert_v2_temporal_contract(v2_temporal_8h_df, v2_evidence_8h_df)
            self._assert_tranche0_provenance_contract(
                assignment_df=audit_assignment_df,
                rule_firings_df=audit_rule_firings_df,
                rule_registry_df=audit_rule_registry_df,
                point_detailed_df=point_detailed_df,
                temporal_evidence_3h_df=v2_evidence_3h_df,
                temporal_evidence_8h_df=v2_evidence_8h_df,
            )

            direct_source_rows = dependency_df.loc[dependency_df["task_id"].astype("string") == "v0_point_train", "direct_source_fields"]
            direct_source_text = "|".join(str(value) for value in direct_source_rows.tolist())
            self.assertNotIn("ph", direct_source_text.lower())
            self.assertNotIn("n_proxy", direct_source_text.lower())
            self.assertNotIn("p_proxy", direct_source_text.lower())
            self.assertNotIn("k_proxy", direct_source_text.lower())
            self.assertEqual(
                current_scope_summary["primary_public_scope"]["task_ids"],
                ["v0_point_train", "v1_point_train", "v2_same_y_3h", "v2_temporal_3h"],
            )
            self.assertIn("v2_temporal_8h", current_scope_summary["optional_explicit_scope"]["task_ids"])
            self.assertIn("## Output", guide_text)
            self.assertIn("point weak labels used by v0 and v1", guide_text)
            self.assertEqual(
                label_registry["current_primary_scope_task_ids"],
                ["v0_point_train", "v1_point_train", "v2_same_y_3h", "v2_temporal_3h"],
            )
            task_lookup = {task["task_id"]: task for task in label_registry["tasks"]}
            self.assertEqual(task_lookup["v2_temporal_3h"]["scope_role"], "PRIMARY_PUBLIC_SCOPE")
            self.assertEqual(task_lookup["v2_temporal_8h"]["scope_role"], "OPTIONAL_EXPLICIT")

    def _assert_v2_temporal_contract(self, labels_df: pd.DataFrame, evidence_df: pd.DataFrame) -> None:
        joined = labels_df.merge(
            evidence_df.loc[
                :,
                [
                    "record.id",
                    "eligible_for_training",
                    "intrinsic_eligibility",
                    "low_run_length_ending_at_point",
                    "point_train_label_name",
                    "positive_environmental_evidence_count",
                ],
            ].rename(columns={"record.id": "sample_id", "intrinsic_eligibility": "evidence_intrinsic_eligibility"}),
            on="sample_id",
            how="inner",
        )
        self.assertFalse(joined.empty)

        excluded = ~joined["intrinsic_eligibility"].fillna(False).astype(bool)
        self.assertTrue((joined.loc[excluded, "label_name"].astype("string") == "insufficient_window_context").all())

        persistent = joined["label_name"].astype("string") == "persistent_low_relative_moisture_window"
        if persistent.any():
            self.assertTrue((joined.loc[persistent, "point_train_label_name"].astype("string") == "low_relative_moisture_point").all())
            self.assertTrue((joined.loc[persistent, "low_run_length_ending_at_point"].fillna(0).astype(int) >= 3).all())

        unknown = joined["label_name"].astype("string") == "unknown_environment_window"
        if unknown.any():
            allowed = (
                (joined.loc[unknown, "point_train_label_name"].astype("string") == "unknown_environment_point")
                | (joined.loc[unknown, "positive_environmental_evidence_count"].fillna(0).astype(int) > 0)
            )
            self.assertTrue(allowed.all())

    def _assert_tranche0_provenance_contract(
        self,
        *,
        assignment_df: pd.DataFrame,
        rule_firings_df: pd.DataFrame,
        rule_registry_df: pd.DataFrame,
        point_detailed_df: pd.DataFrame,
        temporal_evidence_3h_df: pd.DataFrame,
        temporal_evidence_8h_df: pd.DataFrame,
    ) -> None:
        required_columns = {
            "assignment_id",
            "sample_id",
            "label_task_id",
            "target_label",
            "primary_fired_rule_id",
            "fired_rule_ids",
            "resolution_id",
            "assignment_mode",
            "source_task",
            "source_assignment_id",
            "source_label",
            "eligibility_provenance",
        }
        self.assertTrue(required_columns.issubset(set(assignment_df.columns)))
        self.assertFalse((assignment_df["resolution_id"].astype("string") == "POINT_LABEL_TRANSFER").any())
        self.assertFalse((rule_firings_df["rule_id"].astype("string") == "POINT_LABEL_TRANSFER").any())
        self.assertFalse((rule_registry_df["rule_id"].astype("string") == "POINT_LABEL_TRANSFER").any())

        for row in assignment_df.to_dict(orient="records"):
            fired_rule_ids = json.loads(str(row["fired_rule_ids"]))
            primary_fired_rule_id = row.get("primary_fired_rule_id")
            if pd.notna(primary_fired_rule_id):
                self.assertIn(str(primary_fired_rule_id), fired_rule_ids)

        point_assignment = assignment_df.loc[assignment_df["label_task_id"].astype("string") == "v0_v1_point_detailed"].copy()
        point_join = point_assignment.merge(
            point_detailed_df.loc[:, ["sample_id", "label_name"]].rename(columns={"label_name": "point_label_name"}),
            on="sample_id",
            how="left",
            validate="one_to_one",
        )
        normal_point = point_join.loc[point_join["point_label_name"].astype("string") == "normal_point"]
        self.assertTrue((normal_point["resolution_id"].astype("string") == "POINT_NORMAL_DEFAULT").all())
        self.assertTrue(normal_point["primary_fired_rule_id"].isna().all())

        same_y_assignment = assignment_df.loc[
            assignment_df["label_task_id"].astype("string").isin(["v2_same_y_3h", "v2_same_y_8h"])
        ].copy()
        self.assertFalse(same_y_assignment.empty)
        self.assertTrue((same_y_assignment["assignment_mode"].astype("string") == "LABEL_TRANSFER").all())
        self.assertTrue((same_y_assignment["source_task"].astype("string") == "POINT").all())
        self.assertTrue((same_y_assignment["resolution_id"].astype("string") == "SAME_Y_POINT_LABEL_TRANSFER").all())
        self.assertTrue(same_y_assignment["source_assignment_id"].notna().all())
        self.assertTrue(same_y_assignment["primary_fired_rule_id"].isna().all())
        self.assertTrue((same_y_assignment["fired_rule_ids"].astype("string") == "[]").all())

        temporal_assignment = assignment_df.loc[
            assignment_df["label_task_id"].astype("string").isin(["v2_temporal_3h", "v2_temporal_8h"])
        ].copy()
        self.assertFalse(temporal_assignment.empty)

        excluded_temporal = temporal_assignment.loc[temporal_assignment["assignment_mode"].astype("string") == "EXCLUDED"]
        self.assertTrue((excluded_temporal["resolution_id"].astype("string") == "TEMPORAL_WINDOW_INELIGIBLE").all())
        self.assertTrue(excluded_temporal["source_assignment_id"].isna().all())

        temporal_evidence = pd.concat(
            [
                temporal_evidence_3h_df.assign(label_task_id="v2_temporal_3h"),
                temporal_evidence_8h_df.assign(label_task_id="v2_temporal_8h"),
            ],
            ignore_index=True,
        ).rename(columns={"record.id": "sample_id"})
        temporal_join = temporal_assignment.merge(
            temporal_evidence.loc[
                :,
                [
                    "sample_id",
                    "label_task_id",
                    "intrinsic_eligibility",
                    "point_train_label_name",
                    "low_run_length_ending_at_point",
                ],
            ],
            on=["sample_id", "label_task_id"],
            how="left",
            validate="one_to_one",
        )
        insufficient_persistence = temporal_join.loc[
            temporal_join["intrinsic_eligibility"].fillna(False).astype(bool)
            & (temporal_join["point_train_label_name"].astype("string") == "low_relative_moisture_point")
            & (temporal_join["low_run_length_ending_at_point"].fillna(0).astype(int) < 3)
        ]
        if not insufficient_persistence.empty:
            self.assertTrue(
                (
                    insufficient_persistence["resolution_id"].astype("string")
                    == "TEMPORAL_UNKNOWN_INSUFFICIENT_PERSISTENCE"
                ).all()
            )
            self.assertTrue((insufficient_persistence["assignment_mode"].astype("string") == "RULE_EVALUATION").all())
            self.assertTrue(insufficient_persistence["source_assignment_id"].isna().all())

        point_unknown_transfer = temporal_join.loc[
            temporal_join["intrinsic_eligibility"].fillna(False).astype(bool)
            & (temporal_join["point_train_label_name"].astype("string") == "unknown_environment_point")
        ]
        self.assertFalse(point_unknown_transfer.empty)
        self.assertTrue(
            (
                point_unknown_transfer["resolution_id"].astype("string")
                == "TEMPORAL_POINT_UNKNOWN_TRANSFER"
            ).all()
        )
        self.assertTrue((point_unknown_transfer["assignment_mode"].astype("string") == "LABEL_TRANSFER").all())
        self.assertTrue(point_unknown_transfer["source_assignment_id"].notna().all())


if __name__ == "__main__":
    unittest.main()
