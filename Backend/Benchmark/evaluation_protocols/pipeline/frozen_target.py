from __future__ import annotations

import json

import pandas as pd

from Backend.Benchmark.evaluation_protocols.scope import FINAL_TARGET_FOLD_ID, PRIMARY_FEATURE_VIEW_IDS, PRIMARY_FOLD_IDS


def build_frozen_target_manifest(
    task_training_manifest: pd.DataFrame,
    *,
    feature_view_ids: tuple[str, ...] = PRIMARY_FEATURE_VIEW_IDS,
    source_fold_ids: tuple[str, ...] = PRIMARY_FOLD_IDS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    source_rows = task_training_manifest.loc[
        task_training_manifest["feature_view_id"].astype("string").isin(feature_view_ids)
        & task_training_manifest["fold_id"].astype("string").isin(source_fold_ids)
        & task_training_manifest["deployment_domain"].astype("string").eq("P1_SOURCE")
        & task_training_manifest["partition"].astype("string").isin(("train", "validation", "test"))
        & task_training_manifest["final_trainability"].fillna(False).astype(bool)
    ].copy()
    target_rows = task_training_manifest.loc[
        task_training_manifest["feature_view_id"].astype("string").isin(feature_view_ids)
        & task_training_manifest["fold_id"].astype("string").eq("p2_target_holdout")
        & task_training_manifest["deployment_domain"].astype("string").eq("P2_TARGET")
        & task_training_manifest["partition"].astype("string").eq("target_test")
        & task_training_manifest["final_trainability"].fillna(False).astype(bool)
    ].copy()

    manifest_rows: list[dict[str, object]] = []
    validation_rows: list[dict[str, object]] = []
    for feature_view_id in feature_view_ids:
        feature_source = source_rows.loc[source_rows["feature_view_id"].astype("string") == feature_view_id].copy()
        feature_target = target_rows.loc[target_rows["feature_view_id"].astype("string") == feature_view_id].copy()

        frozen_source = _deduplicate_source_rows(feature_source, feature_view_id=feature_view_id)
        if not feature_target.empty and feature_target["sample_id"].astype("string").duplicated(keep=False).any():
            duplicates = feature_target.loc[
                feature_target["sample_id"].astype("string").duplicated(keep=False),
                ["feature_view_id", "sample_id"],
            ]
            raise ValueError(
                "Frozen target manifest found duplicate target_test rows for "
                f"{feature_view_id}: {duplicates.to_dict(orient='records')}"
            )

        manifest_rows.extend(frozen_source.to_dict(orient="records"))
        manifest_rows.extend(feature_target.to_dict(orient="records"))
        validation_rows.append(
            {
                "feature_view_id": feature_view_id,
                "source_final_train_count": int(len(frozen_source)),
                "target_test_count": int(len(feature_target)),
                "source_unique_sample_count": int(frozen_source["sample_id"].astype("string").nunique()) if not frozen_source.empty else 0,
                "target_unique_sample_count": int(feature_target["sample_id"].astype("string").nunique()) if not feature_target.empty else 0,
                "source_present": not frozen_source.empty,
                "target_present": not feature_target.empty,
                "single_refit_ready": bool(not frozen_source.empty and not feature_target.empty),
            }
        )

    manifest_df = pd.DataFrame(manifest_rows).convert_dtypes()
    if not manifest_df.empty and manifest_df.duplicated(
        subset=["feature_view_id", "fold_id", "partition", "sample_id"],
        keep=False,
    ).any():
        duplicates = manifest_df.loc[
            manifest_df.duplicated(subset=["feature_view_id", "fold_id", "partition", "sample_id"], keep=False),
            ["feature_view_id", "fold_id", "partition", "sample_id"],
        ]
        raise ValueError(
            "Frozen target manifest has duplicate feature_view_id/fold_id/partition/sample_id rows: "
            f"{duplicates.to_dict(orient='records')}"
        )
    return manifest_df, pd.DataFrame(validation_rows).convert_dtypes()


def _deduplicate_source_rows(source_rows: pd.DataFrame, *, feature_view_id: str) -> pd.DataFrame:
    if source_rows.empty:
        return source_rows

    ordered = source_rows.sort_values(["sample_id", "fold_id", "partition"], kind="stable")
    grouped_rows: list[dict[str, object]] = []
    for sample_id, frame in ordered.groupby(ordered["sample_id"].astype("string"), sort=False):
        label_names = frame["label_name"].astype("string").dropna().unique().tolist()
        if len(label_names) != 1:
            raise ValueError(
                f"Frozen source fit requires a single label_name per sample for {feature_view_id}/{sample_id}, "
                f"found {label_names}."
            )
        base = frame.iloc[0].to_dict()
        base["fold_id"] = FINAL_TARGET_FOLD_ID
        base["partition"] = "train"
        base["effective_partition"] = "train"
        base["matched_cohort_id"] = pd.NA
        base["source_fold_ids_json"] = json.dumps(
            sorted(frame["fold_id"].astype("string").dropna().unique().tolist()),
            ensure_ascii=True,
            separators=(",", ":"),
        )
        base["source_partitions_json"] = json.dumps(
            sorted(frame["partition"].astype("string").dropna().unique().tolist()),
            ensure_ascii=True,
            separators=(",", ":"),
        )
        base["source_manifest_role"] = "source_final_fit"
        grouped_rows.append(base)
    return pd.DataFrame(grouped_rows).convert_dtypes()
