from __future__ import annotations

import json

import pandas as pd

from Backend.Benchmark.evaluation_protocols.pipeline.metrics import summarize_protocol_classification


def build_stage_run_frames(
    *,
    stage_spec: dict[str, object],
    task_training_manifest: pd.DataFrame,
    comparison_training_manifest: pd.DataFrame,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    stage_id = str(stage_spec["stage_id"])
    stage_feature_views = set(stage_spec["feature_views"])
    stage_fold_ids = set(stage_spec["fold_ids"])
    stage_comparison_ids = set(stage_spec["comparison_ids"])
    validation_rows: list[dict[str, object]] = []

    if stage_comparison_ids:
        comparison_frame = comparison_training_manifest.loc[
            comparison_training_manifest["comparison_id"].astype("string").isin(stage_comparison_ids)
            & comparison_training_manifest["fold_id"].astype("string").isin(stage_fold_ids)
            & comparison_training_manifest["feature_view_id"].astype("string").isin(stage_feature_views)
        ].copy()
        validation_rows.append(
            {
                "stage_id": stage_id,
                "scope": "comparison_gate",
                "passed": not comparison_frame.empty,
                "details": json.dumps(
                    {
                        "comparison_ids": sorted(stage_comparison_ids),
                        "resolved_rows": int(len(comparison_frame)),
                    },
                    ensure_ascii=True,
                    separators=(",", ":"),
                ),
            }
        )
        if comparison_frame.empty:
            return [], validation_rows
        validation_rows.extend(_build_comparison_alignment_validation(stage_id, comparison_frame))
        run_frames: list[dict[str, object]] = []
        for (comparison_id, comparison_side, feature_view_id, fold_id), frame in comparison_frame.groupby(
            ["comparison_id", "comparison_side", "feature_view_id", "fold_id"],
            dropna=False,
            sort=False,
        ):
            run_frames.append(
                {
                    "run_scope": "comparison",
                    "comparison_id": str(comparison_id),
                    "comparison_side": str(comparison_side),
                    "feature_view_id": str(feature_view_id),
                    "fold_id": str(fold_id),
                    "task_rows": _order_task_rows(frame),
                }
            )
        return run_frames, validation_rows

    task_frame = task_training_manifest.loc[
        task_training_manifest["feature_view_id"].astype("string").isin(stage_feature_views)
        & task_training_manifest["fold_id"].astype("string").isin(stage_fold_ids)
    ].copy()
    validation_rows.append(
        {
            "stage_id": stage_id,
            "scope": "comparison_gate",
            "passed": True,
            "details": json.dumps(
                {
                    "comparison_ids": [],
                    "resolved_rows": 0,
                },
                ensure_ascii=True,
                separators=(",", ":"),
            ),
        }
    )
    run_frames = []
    for (feature_view_id, fold_id), frame in task_frame.groupby(
        ["feature_view_id", "fold_id"],
        dropna=False,
        sort=False,
    ):
        run_frames.append(
            {
                "run_scope": "task",
                "comparison_id": None,
                "comparison_side": None,
                "feature_view_id": str(feature_view_id),
                "fold_id": str(fold_id),
                "task_rows": _order_task_rows(frame),
            }
        )
    return run_frames, validation_rows


def build_prediction_rows(
    *,
    stage_id: str,
    run_scope: str,
    comparison_id: str | None,
    comparison_side: str | None,
    feature_view_id: str,
    feature_source_view_id: str,
    fold_id: str,
    partition: str,
    partition_rows: pd.DataFrame,
    y_true: list[int],
    y_pred: list[int],
    y_proba: list[list[float]] | None,
    class_names: list[str],
) -> list[dict[str, object]]:
    class_names_json = json.dumps(class_names, ensure_ascii=True, separators=(",", ":"))
    rows: list[dict[str, object]] = []
    ordered = _order_task_rows(partition_rows).reset_index(drop=True)
    for index, row in enumerate(ordered.to_dict(orient="records")):
        probability_payload = None
        if y_proba is not None:
            probability_payload = {
                class_name: float(probability)
                for class_name, probability in zip(class_names, y_proba[index], strict=True)
            }
        rows.append(
            {
                "stage_id": stage_id,
                "run_scope": run_scope,
                "comparison_id": comparison_id if comparison_id is not None else pd.NA,
                "comparison_side": comparison_side if comparison_side is not None else pd.NA,
                "feature_view_id": feature_view_id,
                "feature_source_view_id": feature_source_view_id,
                "fold_id": fold_id,
                "partition": partition,
                "sample_id": str(row["sample_id"]),
                "label_name_true": str(row["label_name"]),
                "label_name_pred": class_names[y_pred[index]],
                "y_true_index": int(y_true[index]),
                "y_pred_index": int(y_pred[index]),
                "class_names_json": class_names_json,
                "prediction_probability_json": (
                    json.dumps(probability_payload, ensure_ascii=True, separators=(",", ":"))
                    if probability_payload is not None
                    else pd.NA
                ),
                "matched_cohort_id": row.get("matched_cohort_id", pd.NA),
                "record_id_order": row.get("record_id_order", pd.NA),
                "record_set_hash": row.get("record_set_hash", pd.NA),
                "environment_id": row.get("environment_id", pd.NA),
                "eligibility_status": row.get("eligibility_status", pd.NA),
                "day_id": row.get("day_id", row.get("date_local", pd.NA)),
                "segment_id": row.get("segment_id", row.get("record.segment_id", pd.NA)),
                "gap_regime": row.get("gap_regime", pd.NA),
                "ontology_id": row.get("ontology_id", pd.NA),
            }
        )
    return rows


def build_pooled_prediction_summary(predictions_df: pd.DataFrame) -> pd.DataFrame:
    if predictions_df.empty:
        return pd.DataFrame().convert_dtypes()
    rows: list[dict[str, object]] = []
    group_columns = [
        "stage_id",
        "run_scope",
        "comparison_id",
        "comparison_side",
        "feature_view_id",
        "feature_source_view_id",
        "partition",
    ]
    for keys, frame in predictions_df.groupby(group_columns, dropna=False, sort=False):
        class_names_values = frame["class_names_json"].astype("string").dropna().unique().tolist()
        if len(class_names_values) != 1:
            raise ValueError(
                "Pooled smoke prediction group must resolve exactly one class_names_json value: "
                f"{dict(zip(group_columns, keys, strict=True))}"
            )
        class_names = json.loads(class_names_values[0])
        metrics = summarize_protocol_classification(
            frame["y_true_index"].astype(int).to_numpy(),
            frame["y_pred_index"].astype(int).to_numpy(),
            class_names,
        )
        row = {
            column: value for column, value in zip(group_columns, keys, strict=True)
        }
        row.update(
            {
                "pooled_row_count": int(len(frame)),
                "fold_count": int(frame["fold_id"].astype("string").nunique()),
                "class_names_json": class_names_values[0],
                "accuracy": float(metrics["accuracy"]),
                "supported_class_balanced_accuracy": float(metrics["supported_class_balanced_accuracy"]),
                "supported_class_macro_f1": float(metrics["supported_class_macro_f1"]),
                "fixed_ontology_macro_f1": float(metrics["fixed_ontology_macro_f1"]),
                "weighted_f1": float(metrics["weighted_f1"]),
                "unsupported_classes_json": json.dumps(metrics["unsupported_classes"], ensure_ascii=True, separators=(",", ":")),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows).convert_dtypes()


def build_frozen_target_run_frames(
    frozen_target_manifest: pd.DataFrame,
    *,
    feature_view_ids: tuple[str, ...],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    validation_rows: list[dict[str, object]] = []
    run_frames: list[dict[str, object]] = []
    for feature_view_id in feature_view_ids:
        frame = frozen_target_manifest.loc[
            frozen_target_manifest["feature_view_id"].astype("string") == feature_view_id
        ].copy()
        source_count = int(frame["partition"].astype("string").eq("train").sum()) if not frame.empty else 0
        target_count = int(frame["partition"].astype("string").eq("target_test").sum()) if not frame.empty else 0
        validation_rows.append(
            {
                "stage_id": "frozen_target_holdout",
                "scope": f"frozen_target_gate::{feature_view_id}",
                "passed": bool(source_count > 0 and target_count > 0),
                "details": json.dumps(
                    {
                        "feature_view_id": feature_view_id,
                        "source_final_train_count": source_count,
                        "target_test_count": target_count,
                    },
                    ensure_ascii=True,
                    separators=(",", ":"),
                ),
            }
        )
        if source_count == 0 or target_count == 0:
            continue
        run_frames.append(
            {
                "run_scope": "task",
                "comparison_id": None,
                "comparison_side": None,
                "feature_view_id": feature_view_id,
                "fold_id": "source_final_fit__p2_target_holdout",
                "task_rows": _order_task_rows(frame),
            }
        )
    return run_frames, validation_rows


def _build_comparison_alignment_validation(
    stage_id: str,
    comparison_frame: pd.DataFrame,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for (comparison_id, fold_id, partition), frame in comparison_frame.groupby(
        ["comparison_id", "fold_id", "partition"],
        dropna=False,
        sort=False,
    ):
        ordered_by_side = {
            str(side): _order_task_rows(side_frame)["sample_id"].astype("string").tolist()
            for side, side_frame in frame.groupby("comparison_side", dropna=False, sort=False)
        }
        if "label_name" in frame.columns:
            labels_by_side = {
                str(side): _order_task_rows(side_frame)["label_name"].astype("string").tolist()
                for side, side_frame in frame.groupby("comparison_side", dropna=False, sort=False)
            }
        else:
            labels_by_side = {}
        unique_hashes = sorted(frame["record_set_hash"].astype("string").dropna().unique().tolist())
        counts_by_side = {
            str(side): int(len(side_frame))
            for side, side_frame in frame.groupby("comparison_side", dropna=False, sort=False)
        }
        unique_feature_views = sorted(frame["feature_view_id"].astype("string").dropna().unique().tolist())
        ordered_lists = list(ordered_by_side.values())
        ordered_label_lists = list(labels_by_side.values())
        labels_aligned = (
            not ordered_label_lists
            or (len(ordered_label_lists) == 2 and all(candidate == ordered_label_lists[0] for candidate in ordered_label_lists[1:]))
        )
        aligned = (
            len(ordered_by_side) == 2
            and len(unique_hashes) == 1
            and len(set(counts_by_side.values())) == 1
            and all(candidate == ordered_lists[0] for candidate in ordered_lists[1:])
            and labels_aligned
        )
        rows.append(
            {
                "stage_id": stage_id,
                "scope": f"comparison_alignment::{comparison_id}::{fold_id}::{partition}",
                "passed": aligned,
                "details": json.dumps(
                    {
                        "feature_views": unique_feature_views,
                        "counts_by_side": counts_by_side,
                        "record_set_hashes": unique_hashes,
                        "same_y_labels_aligned": labels_aligned,
                    },
                    ensure_ascii=True,
                    separators=(",", ":"),
                ),
            }
        )
    return rows


def _order_task_rows(frame: pd.DataFrame) -> pd.DataFrame:
    ordered = frame.copy()
    sort_columns: list[str] = []
    if "partition" in ordered.columns:
        sort_columns.append("partition")
    if "record_id_order" in ordered.columns:
        sort_columns.append("record_id_order")
    if "sample_id" in ordered.columns:
        sort_columns.append("sample_id")
    if not sort_columns:
        return ordered.reset_index(drop=True)
    return ordered.sort_values(sort_columns, kind="stable").reset_index(drop=True)
