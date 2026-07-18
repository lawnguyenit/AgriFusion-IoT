from __future__ import annotations

import pandas as pd

from Backend.Benchmark.weak_labels.shared.configs import (
    LABEL_STATUS_EXCLUDED_WINDOW,
    LABEL_STATUS_LABELED,
    POINT_LABELS,
    V2_TEMPORAL_EXCLUDED_LABEL,
    V2_TEMPORAL_LABELS,
)


def resolve_v2_effective_partition(
    *,
    audit_df: pd.DataFrame,
    boundary_timestamps: dict[str, int],
    purge_seconds: int,
) -> tuple[pd.Series, pd.Series]:
    effective_partition = audit_df["base_partition"].astype("string").copy()
    exclusion_reason = pd.Series([pd.NA] * len(audit_df), index=audit_df.index, dtype="string")
    eligible = audit_df["eligible_for_training"].fillna(False).astype(bool)
    labeled = audit_df["point_label_status"].astype("string") == LABEL_STATUS_LABELED

    effective_partition.loc[~eligible] = "excluded"
    exclusion_reason.loc[~eligible] = "insufficient_history"
    effective_partition.loc[~labeled] = "excluded"
    exclusion_reason.loc[~labeled] = "point_label_not_labeled"

    timestamps = pd.to_numeric(audit_df["record.ts_sample"], errors="coerce")
    for partition_name, boundary_ts in boundary_timestamps.items():
        if partition_name not in {"validation", "test"}:
            continue
        partition_mask = audit_df["base_partition"].astype("string") == partition_name
        purge_mask = partition_mask & (timestamps < int(boundary_ts) + int(purge_seconds))
        effective_partition.loc[purge_mask] = "excluded"
        exclusion_reason.loc[purge_mask] = "purge_boundary"
    return effective_partition, exclusion_reason


def build_same_y_frame(audit_df: pd.DataFrame, *, task_id: str) -> pd.DataFrame:
    same_y_df = pd.DataFrame(
        {
            "sample_id": audit_df["record.id"].astype("string"),
            "sample_type": pd.Series(["record"] * len(audit_df), dtype="string"),
            "task_id": pd.Series([task_id] * len(audit_df), dtype="string"),
            "label_name": audit_df["point_train_label_name"].astype("string"),
            "label_status": pd.Series(
                [LABEL_STATUS_LABELED if partition != "excluded" else LABEL_STATUS_EXCLUDED_WINDOW for partition in audit_df["effective_partition"]],
                dtype="string",
            ),
            "base_partition": audit_df["base_partition"].astype("string"),
            "effective_partition": audit_df["effective_partition"].astype("string"),
            "exclusion_reason": audit_df["exclusion_reason"].astype("string"),
            "source_task_id": pd.Series(["v0_point_train"] * len(audit_df), dtype="string"),
        }
    ).convert_dtypes()
    same_y_df.loc[same_y_df["effective_partition"] == "excluded", "label_name"] = pd.NA
    return same_y_df


def build_temporal_labels(audit_df: pd.DataFrame, *, task_id: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for row in audit_df.to_dict(orient="records"):
        if row["effective_partition"] == "excluded":
            label_name = V2_TEMPORAL_EXCLUDED_LABEL
            label_status = LABEL_STATUS_EXCLUDED_WINDOW
        elif row["point_train_label_name"] == POINT_LABELS[1] and int(row["low_run_length_ending_at_point"]) >= 3:
            label_name = V2_TEMPORAL_LABELS[1]
            label_status = LABEL_STATUS_LABELED
        elif row["point_train_label_name"] == POINT_LABELS[2] or int(row["positive_environmental_evidence_count"]) > 0:
            label_name = V2_TEMPORAL_LABELS[2]
            label_status = LABEL_STATUS_LABELED
        else:
            label_name = V2_TEMPORAL_LABELS[0]
            label_status = LABEL_STATUS_LABELED
        rows.append(
            {
                "sample_id": str(row["record.id"]),
                "sample_type": "record",
                "task_id": task_id,
                "label_name": label_name,
                "label_status": label_status,
                "base_partition": row["base_partition"],
                "effective_partition": row["effective_partition"],
                "exclusion_reason": row["exclusion_reason"],
                "primary_rule_id": "LOW_RUN_ENDING_AT_ANCHOR_GE_3" if label_name == V2_TEMPORAL_LABELS[1] else "POINT_LABEL_TRANSFER",
            }
        )
    return pd.DataFrame(rows).convert_dtypes()


def build_matched_cohort_manifest(same_y_df: pd.DataFrame, *, horizon_name: str, task_id: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    eligible_ids = same_y_df.loc[same_y_df["effective_partition"] != "excluded", "sample_id"].astype("string").tolist()
    for point_task_id in ("v0_point_train", "v1_point_train"):
        for record_id in eligible_ids:
            rows.append(
                {
                    "record.id": record_id,
                    "horizon_name": horizon_name,
                    "v2_task_id": task_id,
                    "point_task_id": point_task_id,
                }
            )
    return pd.DataFrame(rows).convert_dtypes()


def build_label_agreement(temporal_3h_df: pd.DataFrame, temporal_8h_df: pd.DataFrame) -> pd.DataFrame:
    merged = temporal_3h_df.loc[:, ["sample_id", "label_name", "effective_partition"]].merge(
        temporal_8h_df.loc[:, ["sample_id", "label_name", "effective_partition"]],
        on="sample_id",
        how="inner",
        suffixes=("_3h", "_8h"),
    )
    merged = merged.loc[
        (merged["effective_partition_3h"] != "excluded") & (merged["effective_partition_8h"] != "excluded")
    ].copy()
    if merged.empty:
        return pd.DataFrame(
            [{"comparison": "3h_vs_8h", "shared_labeled_rows": 0, "agreement_count": 0, "agreement_ratio": pd.NA}]
        ).convert_dtypes()
    agreement_count = int((merged["label_name_3h"] == merged["label_name_8h"]).sum())
    return pd.DataFrame(
        [
            {
                "comparison": "3h_vs_8h",
                "shared_labeled_rows": int(len(merged)),
                "agreement_count": agreement_count,
                "agreement_ratio": float(agreement_count / len(merged)),
            }
        ]
    ).convert_dtypes()
