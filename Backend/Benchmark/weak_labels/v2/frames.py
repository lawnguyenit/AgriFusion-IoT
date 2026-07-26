from __future__ import annotations

import pandas as pd

from Backend.Benchmark.weak_labels.shared.configs import (
    LABEL_STATUS_EXCLUDED_WINDOW,
    LABEL_STATUS_LABELED,
    POINT_LABELS,
    V2_TEMPORAL_EXCLUDED_LABEL,
    V2_TEMPORAL_LABELS,
    WEAK_LABELS_VERSION,
)


def resolve_v2_intrinsic_state(
    *,
    audit_df: pd.DataFrame,
) -> tuple[pd.Series, pd.Series]:
    intrinsic_eligibility = pd.Series([True] * len(audit_df), index=audit_df.index, dtype="boolean")
    exclusion_reason = pd.Series([pd.NA] * len(audit_df), index=audit_df.index, dtype="string")
    eligible = audit_df["eligible_for_training"].fillna(False).astype(bool)
    labeled = audit_df["point_label_status"].astype("string") == LABEL_STATUS_LABELED

    intrinsic_eligibility.loc[~eligible] = False
    exclusion_reason.loc[~eligible] = "insufficient_history"
    intrinsic_eligibility.loc[~labeled] = False
    exclusion_reason.loc[~labeled] = "point_label_not_labeled"
    return intrinsic_eligibility, exclusion_reason


def build_same_y_frame(audit_df: pd.DataFrame, *, task_id: str) -> pd.DataFrame:
    same_y_df = pd.DataFrame(
        {
            "sample_id": audit_df["record.id"].astype("string"),
            "sample_type": pd.Series(["record"] * len(audit_df), dtype="string"),
            "task_id": pd.Series([task_id] * len(audit_df), dtype="string"),
            "label_task_id": pd.Series([task_id] * len(audit_df), dtype="string"),
            "label_name": audit_df["point_train_label_name"].astype("string"),
            "label_status": pd.Series(
                [LABEL_STATUS_LABELED if eligible else LABEL_STATUS_EXCLUDED_WINDOW for eligible in audit_df["intrinsic_eligibility"]],
                dtype="string",
            ),
            "intrinsic_eligibility": audit_df["intrinsic_eligibility"].astype("boolean"),
            "intrinsic_exclusion_reason": audit_df["intrinsic_exclusion_reason"].astype("string"),
            "source_task_id": pd.Series(["v0_point_train"] * len(audit_df), dtype="string"),
            "rule_version": pd.Series([WEAK_LABELS_VERSION] * len(audit_df), dtype="string"),
        }
    ).convert_dtypes()
    same_y_df.loc[~same_y_df["intrinsic_eligibility"].fillna(False).astype(bool), "label_name"] = pd.NA
    return same_y_df


def build_temporal_labels(audit_df: pd.DataFrame, *, task_id: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for row in audit_df.to_dict(orient="records"):
        if not bool(row["intrinsic_eligibility"]):
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
                "label_task_id": task_id,
                "label_name": label_name,
                "label_status": label_status,
                "intrinsic_eligibility": row["intrinsic_eligibility"],
                "intrinsic_exclusion_reason": row["intrinsic_exclusion_reason"],
                "primary_rule_id": "LOW_RUN_ENDING_AT_ANCHOR_GE_3" if label_name == V2_TEMPORAL_LABELS[1] else "POINT_LABEL_TRANSFER",
                "rule_version": WEAK_LABELS_VERSION,
            }
        )
    return pd.DataFrame(rows).convert_dtypes()


def build_matched_cohort_manifest(same_y_df: pd.DataFrame, *, horizon_name: str, task_id: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    eligible_ids = same_y_df.loc[same_y_df["intrinsic_eligibility"].fillna(False).astype(bool), "sample_id"].astype("string").tolist()
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
    merged = temporal_3h_df.loc[:, ["sample_id", "label_name", "intrinsic_eligibility"]].merge(
        temporal_8h_df.loc[:, ["sample_id", "label_name", "intrinsic_eligibility"]],
        on="sample_id",
        how="inner",
        suffixes=("_3h", "_8h"),
    )
    merged = merged.loc[
        merged["intrinsic_eligibility_3h"].fillna(False).astype(bool)
        & merged["intrinsic_eligibility_8h"].fillna(False).astype(bool)
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
