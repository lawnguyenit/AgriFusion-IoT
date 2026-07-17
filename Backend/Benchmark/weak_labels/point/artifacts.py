from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from Backend.Benchmark.shared.weak_rules import is_low_relative_moisture
from Backend.Benchmark.weak_labels.point.thresholds import ThresholdContext
from Backend.Benchmark.weak_labels.shared.configs import (
    LABEL_STATUS_ABSTAIN,
    LABEL_STATUS_EXCLUDED_TIME,
    LABEL_STATUS_LABELED,
    POINT_LABELS,
    POINT_SENSITIVITY_LABEL,
    V6_RISE_DELTA_PP,
    V6_THERMAL_THRESHOLD_KPA,
    WEAK_LABELS_VERSION,
)
from Backend.Benchmark.weak_labels.shared.helpers import json_dumps_compact


@dataclass(frozen=True)
class PointLabelArtifacts:
    enriched_df: pd.DataFrame
    point_evidence_flags: pd.DataFrame
    point_labels_detailed: pd.DataFrame
    point_labels_train: pd.DataFrame
    technical_labels_audit: pd.DataFrame


def build_point_label_artifacts(
    continuity_df: pd.DataFrame,
    *,
    threshold_context: ThresholdContext,
) -> PointLabelArtifacts:
    enriched = continuity_df.copy()
    low_flags: list[bool] = []
    thermal_flags: list[bool] = []
    rise_flags: list[bool] = []
    ec_flags: list[bool] = []
    status_values: list[str] = []
    train_label_values: list[object] = []
    detailed_label_values: list[object] = []
    sensitivity_label_values: list[object] = []
    positive_counts: list[int] = []
    low_run_lengths: list[int] = []
    train_label_by_record_id: dict[str, object] = {}

    previous_low_run_by_chunk: dict[str, int] = {}
    for _, row in enriched.iterrows():
        record_id = str(row.get("record.id"))
        chunk_id = str(row.get("record.continuity_chunk_id", ""))
        threshold = threshold_context.resolve_low_moisture_threshold(str(row.get("record.segment_id", "")))
        low_flag = bool(row.get("low_moisture_applicable", False)) and is_low_relative_moisture(
            pd.to_numeric(pd.Series([row.get("npk.soil_moisture_pct")]), errors="coerce").iloc[0],
            threshold,
        )
        thermal_flag = bool(row.get("thermal_applicable", False)) and (
            pd.to_numeric(pd.Series([row.get("derived.vpd_kpa")]), errors="coerce").iloc[0]
            >= V6_THERMAL_THRESHOLD_KPA
        )
        rise_delta = pd.to_numeric(pd.Series([row.get("moisture_rise_delta")]), errors="coerce").iloc[0]
        rise_flag = bool(row.get("moisture_rise_applicable", False)) and pd.notna(rise_delta) and float(rise_delta) >= V6_RISE_DELTA_PP
        ec_delta = pd.to_numeric(pd.Series([row.get("ec_shift_delta_abs")]), errors="coerce").iloc[0]
        ec_flag = (
            bool(row.get("ec_shift_applicable", False))
            and threshold_context.ec_shift_abs_delta_q95 is not None
            and pd.notna(ec_delta)
            and float(ec_delta) >= float(threshold_context.ec_shift_abs_delta_q95)
        )

        low_run_length = previous_low_run_by_chunk.get(chunk_id, 0) + 1 if low_flag else 0
        previous_low_run_by_chunk[chunk_id] = low_run_length
        low_run_lengths.append(low_run_length)

        if not bool(row.get("time_integrity_ok", False)):
            label_status = LABEL_STATUS_EXCLUDED_TIME
            train_label = pd.NA
            detailed_label = "excluded_technical_invalid"
        elif not bool(row.get("core_environment_fully_evaluable", False)):
            label_status = LABEL_STATUS_ABSTAIN
            train_label = pd.NA
            detailed_label = "excluded_technical_invalid"
        else:
            label_status = LABEL_STATUS_LABELED
            if low_flag:
                train_label = POINT_LABELS[1]
            elif thermal_flag or rise_flag or ec_flag:
                train_label = POINT_LABELS[2]
            else:
                train_label = POINT_LABELS[0]
            detailed_label = train_label
        positive_count = int(low_flag) + int(thermal_flag) + int(rise_flag) + int(ec_flag)

        low_flags.append(low_flag)
        thermal_flags.append(thermal_flag)
        rise_flags.append(rise_flag)
        ec_flags.append(ec_flag)
        status_values.append(label_status)
        train_label_values.append(train_label)
        detailed_label_values.append(detailed_label)
        sensitivity_label_values.append(POINT_SENSITIVITY_LABEL if rise_flag else pd.NA)
        positive_counts.append(positive_count)
        train_label_by_record_id[record_id] = train_label

    enriched["low_relative_moisture_flag"] = pd.Series(low_flags, dtype="boolean")
    enriched["thermal_evidence_flag"] = pd.Series(thermal_flags, dtype="boolean")
    enriched["moisture_rise_evidence_flag"] = pd.Series(rise_flags, dtype="boolean")
    enriched["ec_shift_evidence_flag"] = pd.Series(ec_flags, dtype="boolean")
    enriched["point_label_status"] = pd.Series(status_values, dtype="string")
    enriched["point_train_label_name"] = pd.Series(train_label_values, dtype="string")
    enriched["point_detailed_label_name"] = pd.Series(detailed_label_values, dtype="string")
    enriched["point_sensitivity_label_name"] = pd.Series(sensitivity_label_values, dtype="string")
    enriched["positive_environmental_evidence_count"] = pd.Series(positive_counts, dtype="Int64")
    enriched["low_run_length_ending_at_point"] = pd.Series(low_run_lengths, dtype="Int64")

    intrinsic_eligibility = enriched["point_label_status"].astype("string") == LABEL_STATUS_LABELED
    intrinsic_exclusion_reason = pd.Series([pd.NA] * len(enriched), dtype="string")
    intrinsic_exclusion_reason.loc[enriched["point_label_status"].astype("string") == LABEL_STATUS_EXCLUDED_TIME] = "time_integrity_invalid"
    intrinsic_exclusion_reason.loc[enriched["point_label_status"].astype("string") == LABEL_STATUS_ABSTAIN] = "core_environment_not_fully_evaluable"
    point_evidence_flags = pd.DataFrame(
        {
            "record.id": enriched["record.id"].astype("string"),
            "record.ts_sample": enriched["record.ts_sample"].astype("int64"),
            "record.segment_id": enriched["record.segment_id"].astype("string"),
            "intrinsic_eligibility": intrinsic_eligibility.astype("boolean"),
            "intrinsic_exclusion_reason": intrinsic_exclusion_reason.astype("string"),
            "low_moisture_applicable": enriched["low_moisture_applicable"].astype("boolean"),
            "thermal_applicable": enriched["thermal_applicable"].astype("boolean"),
            "ec_shift_applicable": enriched["ec_shift_applicable"].astype("boolean"),
            "moisture_rise_applicable": enriched["moisture_rise_applicable"].astype("boolean"),
            "low_relative_moisture_flag": enriched["low_relative_moisture_flag"].astype("boolean"),
            "thermal_evidence_flag": enriched["thermal_evidence_flag"].astype("boolean"),
            "moisture_rise_evidence_flag": enriched["moisture_rise_evidence_flag"].astype("boolean"),
            "ec_shift_evidence_flag": enriched["ec_shift_evidence_flag"].astype("boolean"),
            "positive_environmental_evidence_count": enriched["positive_environmental_evidence_count"].astype("Int64"),
            "low_run_length_ending_at_point": enriched["low_run_length_ending_at_point"].astype("Int64"),
            "point_label_status": enriched["point_label_status"].astype("string"),
            "rule_version": pd.Series([WEAK_LABELS_VERSION] * len(enriched), dtype="string"),
            "direct_source_fields": pd.Series(
                [
                    json_dumps_compact(["npk.soil_moisture_pct", "npk.ec", "sht.temp_c", "sht.humidity_pct"])
                    for _ in range(len(enriched))
                ],
                dtype="string",
            ),
            "proxy_fields": pd.Series(
                [json_dumps_compact([]) for _ in range(len(enriched))],
                dtype="string",
            ),
        }
    ).convert_dtypes()

    point_labels_detailed = pd.DataFrame(
        {
            "sample_id": enriched["record.id"].astype("string"),
            "sample_type": pd.Series(["record"] * len(enriched), dtype="string"),
            "task_id": pd.Series(["v0_v1_point_detailed"] * len(enriched), dtype="string"),
            "label_task_id": pd.Series(["v0_v1_point_detailed"] * len(enriched), dtype="string"),
            "label_name": enriched["point_detailed_label_name"].astype("string"),
            "label_status": enriched["point_label_status"].astype("string"),
            "intrinsic_eligibility": intrinsic_eligibility.astype("boolean"),
            "intrinsic_exclusion_reason": intrinsic_exclusion_reason.astype("string"),
            "primary_rule_id": pd.Series(
                [
                    "LOW_RELATIVE_MOISTURE_Q10"
                    if label == POINT_LABELS[1]
                    else "ENVIRONMENTAL_EVIDENCE_PRESENT"
                    if label == POINT_LABELS[2]
                    else "ALL_REQUIRED_RULES_NEGATIVE"
                    if label == POINT_LABELS[0]
                    else "TECHNICAL_INVALID"
                    for label in enriched["point_detailed_label_name"].tolist()
                ],
                dtype="string",
            ),
            "sensitivity_label_name": enriched["point_sensitivity_label_name"].astype("string"),
            "rule_version": pd.Series([WEAK_LABELS_VERSION] * len(enriched), dtype="string"),
        }
    ).convert_dtypes()

    point_labels_train_rows: list[dict[str, object]] = []
    for task_id in ("v0_point_train", "v1_point_train"):
        for row in point_labels_detailed.itertuples(index=False):
            point_labels_train_rows.append(
                {
                    "sample_id": row.sample_id,
                    "sample_type": row.sample_type,
                    "task_id": task_id,
                    "label_task_id": task_id,
                    "label_name": train_label_by_record_id.get(str(row.sample_id), pd.NA),
                    "label_status": row.label_status,
                    "intrinsic_eligibility": row.intrinsic_eligibility,
                    "intrinsic_exclusion_reason": row.intrinsic_exclusion_reason,
                    "primary_rule_id": row.primary_rule_id,
                    "rule_version": row.rule_version,
                }
            )
    point_labels_train = pd.DataFrame(point_labels_train_rows).convert_dtypes()

    technical_labels_audit = pd.DataFrame(
        {
            "record.id": enriched["record.id"].astype("string"),
            "record.segment_id": enriched["record.segment_id"].astype("string"),
            "time_integrity_ok": enriched["time_integrity_ok"].astype("boolean"),
            "core_environment_fully_evaluable": enriched["core_environment_fully_evaluable"].astype("boolean"),
            "technical_invalid_reason": enriched["technical_invalid_reason"].astype("string"),
            "point_label_status": enriched["point_label_status"].astype("string"),
            "rule_version": pd.Series([WEAK_LABELS_VERSION] * len(enriched), dtype="string"),
        }
    ).convert_dtypes()

    return PointLabelArtifacts(
        enriched_df=enriched,
        point_evidence_flags=point_evidence_flags,
        point_labels_detailed=point_labels_detailed,
        point_labels_train=point_labels_train,
        technical_labels_audit=technical_labels_audit,
    )
