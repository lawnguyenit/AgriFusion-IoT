from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from Backend.Benchmark.common.digests import stable_digest
from Backend.Benchmark.weak_labels.runtime.contracts import ThresholdRecord
from Backend.Benchmark.weak_labels.shared.configs import (
    LABEL_STATUS_ABSTAIN,
    LABEL_STATUS_EXCLUDED_TIME,
    LABEL_STATUS_EXCLUDED_WINDOW,
    LABEL_STATUS_LABELED,
    POINT_LABELS,
    V2_TEMPORAL_EXCLUDED_LABEL,
    V2_TEMPORAL_LABELS,
    WEAK_LABELS_VERSION,
)


POINT_PRIORITY_PATH = "TECHNICAL_VALIDITY>LOW_RELATIVE_MOISTURE>ENVIRONMENTAL_EVIDENCE>NORMAL_DEFAULT"
TEMPORAL_PRIORITY_PATH = (
    "WINDOW_ELIGIBILITY>PERSISTENT_LOW_RUN>LOW_INSUFFICIENT_PERSISTENCE>POINT_UNKNOWN_TRANSFER>NORMAL_DEFAULT"
)

ASSIGNMENT_MODE_EXCLUDED = "EXCLUDED"
ASSIGNMENT_MODE_LABEL_TRANSFER = "LABEL_TRANSFER"
ASSIGNMENT_MODE_RULE_EVALUATION = "RULE_EVALUATION"

POINT_RESOLUTION_LOW = "POINT_LOW_RELATIVE_MOISTURE"
POINT_RESOLUTION_UNKNOWN = "POINT_UNKNOWN_ENVIRONMENT"
POINT_RESOLUTION_NORMAL = "POINT_NORMAL_DEFAULT"
POINT_RESOLUTION_TECHNICAL_INVALID = "POINT_TECHNICAL_INVALID_GATE"
POINT_RESOLUTION_CORE_ENVIRONMENT_INELIGIBLE = "POINT_CORE_ENVIRONMENT_NOT_FULLY_EVALUABLE"

SAME_Y_RESOLUTION_TRANSFER = "SAME_Y_POINT_LABEL_TRANSFER"

TEMPORAL_RESOLUTION_PERSISTENT_LOW = "TEMPORAL_PERSISTENT_LOW"
TEMPORAL_RESOLUTION_UNKNOWN_INSUFFICIENT_PERSISTENCE = "TEMPORAL_UNKNOWN_INSUFFICIENT_PERSISTENCE"
TEMPORAL_RESOLUTION_POINT_UNKNOWN_TRANSFER = "TEMPORAL_POINT_UNKNOWN_TRANSFER"
TEMPORAL_RESOLUTION_NORMAL = "TEMPORAL_NORMAL_DEFAULT"
TEMPORAL_RESOLUTION_WINDOW_INELIGIBLE = "TEMPORAL_WINDOW_INELIGIBLE"

POINT_TASK_SCOPE = "POINT"
SAME_Y_TASK_SCOPE = "SAME_Y"
TEMPORAL_TASK_SCOPE = "TEMPORAL"
POINT_ASSIGNMENT_TASK_ID = "v0_v1_point_detailed"


def build_tranche0_audit_artifacts(
    *,
    point_enriched_df: pd.DataFrame,
    point_labels_detailed: pd.DataFrame,
    v2_same_y_labels: pd.DataFrame,
    v2_temporal_labels_3h: pd.DataFrame,
    v2_temporal_labels_8h: pd.DataFrame,
    v2_temporal_evidence_3h: pd.DataFrame,
    v2_temporal_evidence_8h: pd.DataFrame,
    threshold_records: tuple[ThresholdRecord, ...],
    weak_labels_repo_root: Path,
) -> dict[str, pd.DataFrame]:
    threshold_lookup = {record.threshold_id: record for record in threshold_records}
    point_label_assignment = _build_point_label_assignment(point_enriched_df, point_labels_detailed)
    point_assignment_lookup = point_label_assignment[
        [
            "sample_id",
            "assignment_id",
            "target_label",
            "technical_valid",
            "assignment_status",
        ]
    ].copy()
    same_y_assignment = _build_same_y_label_assignment(
        v2_same_y_labels,
        point_assignment_lookup=point_assignment_lookup,
    )
    temporal_assignment_3h = _build_temporal_label_assignment(
        v2_temporal_labels_3h,
        evidence_df=v2_temporal_evidence_3h,
        point_assignment_lookup=point_assignment_lookup,
        horizon_name="3h",
    )
    temporal_assignment_8h = _build_temporal_label_assignment(
        v2_temporal_labels_8h,
        evidence_df=v2_temporal_evidence_8h,
        point_assignment_lookup=point_assignment_lookup,
        horizon_name="8h",
    )
    label_assignment = pd.concat(
        [
            point_label_assignment,
            same_y_assignment,
            temporal_assignment_3h,
            temporal_assignment_8h,
        ],
        ignore_index=True,
    ).convert_dtypes()
    rule_firings = pd.concat(
        [
            _build_point_rule_firings(point_enriched_df, threshold_lookup),
            _build_temporal_rule_firings(v2_temporal_evidence_3h, horizon_name="3h"),
            _build_temporal_rule_firings(v2_temporal_evidence_8h, horizon_name="8h"),
        ],
        ignore_index=True,
    ).convert_dtypes()
    return {
        "label_assignment": label_assignment,
        "rule_firings": rule_firings,
        "rule_registry": _build_rule_registry(),
        "threshold_registry": _build_threshold_registry(
            threshold_records=threshold_records,
            weak_labels_repo_root=weak_labels_repo_root,
        ),
        "label_source_dependency": _build_label_source_dependency(),
    }


def _build_point_label_assignment(
    point_enriched_df: pd.DataFrame,
    point_labels_detailed: pd.DataFrame,
) -> pd.DataFrame:
    merged = point_labels_detailed.merge(
        point_enriched_df[
            [
                "record.id",
                "time_integrity_ok",
                "core_environment_fully_evaluable",
                "technical_invalid_reason",
                "low_relative_moisture_flag",
                "thermal_evidence_flag",
                "moisture_rise_evidence_flag",
                "ec_shift_evidence_flag",
                "positive_environmental_evidence_count",
                "point_train_label_name",
            ]
        ].rename(columns={"record.id": "sample_id"}),
        on="sample_id",
        how="left",
        validate="one_to_one",
    )
    rows: list[dict[str, object]] = []
    for row in merged.to_dict(orient="records"):
        technical_valid = bool(row.get("time_integrity_ok", False) and row.get("core_environment_fully_evaluable", False))
        low_flag = bool(row.get("low_relative_moisture_flag", False))
        unknown_rule_result = any(
            bool(row.get(column, False))
            for column in ("thermal_evidence_flag", "moisture_rise_evidence_flag", "ec_shift_evidence_flag")
        )
        assignment_status, train_inclusion_status, exclusion_reason = _resolve_assignment_contract(
            label_status=row.get("label_status"),
            label_name=row.get("label_name"),
            intrinsic_exclusion_reason=row.get("intrinsic_exclusion_reason"),
            technical_invalid_reason=row.get("technical_invalid_reason"),
        )
        fired_rule_ids = _point_semantic_fired_rule_ids(
            technical_valid=technical_valid,
            low_flag=low_flag,
            unknown_rule_result=unknown_rule_result,
        )
        primary_fired_rule_id = fired_rule_ids[0] if fired_rule_ids else pd.NA
        resolution_id = _point_resolution_id(
            technical_valid=technical_valid,
            low_flag=low_flag,
            unknown_rule_result=unknown_rule_result,
            technical_invalid_reason=row.get("technical_invalid_reason"),
        )
        assignment_mode = ASSIGNMENT_MODE_RULE_EVALUATION if technical_valid else ASSIGNMENT_MODE_EXCLUDED
        sample_id = str(row["sample_id"])
        label_task_id = POINT_ASSIGNMENT_TASK_ID
        target_label = row.get("point_train_label_name", row.get("label_name", pd.NA))
        rows.append(
            {
                "assignment_id": _assignment_id(sample_id=sample_id, label_task_id=label_task_id),
                "sample_id": sample_id,
                "label_task_id": label_task_id,
                "target": target_label,
                "target_label": target_label,
                "ontology_id": "point_ontology_v1",
                "primary_rule_id": resolution_id,
                "primary_fired_rule_id": primary_fired_rule_id,
                "fired_rule_ids": _json_list(fired_rule_ids),
                "resolution_id": resolution_id,
                "assignment_mode": assignment_mode,
                "priority_path": POINT_PRIORITY_PATH,
                "technical_valid": technical_valid,
                "ambiguity_code": (
                    "multiple_environmental_evidence"
                    if pd.notna(row.get("positive_environmental_evidence_count"))
                    and int(row["positive_environmental_evidence_count"]) > 1
                    else "none"
                ),
                "assignment_status": assignment_status,
                "train_inclusion_status": train_inclusion_status,
                "exclusion_reason": exclusion_reason,
                "source_task": pd.NA,
                "source_task_id": pd.NA,
                "target_task": POINT_TASK_SCOPE,
                "target_task_id": label_task_id,
                "source_assignment_id": pd.NA,
                "source_label": pd.NA,
                "eligibility_provenance": _eligibility_provenance_json(
                    technical_valid=technical_valid,
                    intrinsic_eligibility=row.get("intrinsic_eligibility"),
                    intrinsic_exclusion_reason=row.get("intrinsic_exclusion_reason"),
                    technical_invalid_reason=row.get("technical_invalid_reason"),
                ),
            }
        )
    return pd.DataFrame(rows).convert_dtypes()


def _build_same_y_label_assignment(
    same_y_labels: pd.DataFrame,
    *,
    point_assignment_lookup: pd.DataFrame,
) -> pd.DataFrame:
    merged = same_y_labels.merge(
        point_assignment_lookup.rename(
            columns={
                "assignment_id": "point_assignment_id",
                "target_label": "point_target_label",
                "technical_valid": "point_technical_valid",
                "assignment_status": "point_assignment_status",
            }
        ),
        on="sample_id",
        how="left",
        validate="many_to_one",
    )
    rows: list[dict[str, object]] = []
    for row in merged.to_dict(orient="records"):
        assignment_status, train_inclusion_status, exclusion_reason = _resolve_assignment_contract(
            label_status=row.get("label_status"),
            label_name=row.get("label_name"),
            intrinsic_exclusion_reason=row.get("intrinsic_exclusion_reason"),
            technical_invalid_reason=None,
        )
        sample_id = str(row["sample_id"])
        label_task_id = str(row["label_task_id"])
        target_label = row.get("label_name", pd.NA)
        rows.append(
            {
                "assignment_id": _assignment_id(sample_id=sample_id, label_task_id=label_task_id),
                "sample_id": sample_id,
                "label_task_id": label_task_id,
                "target": target_label,
                "target_label": target_label,
                "ontology_id": "point_ontology_v1",
                "primary_rule_id": SAME_Y_RESOLUTION_TRANSFER,
                "primary_fired_rule_id": pd.NA,
                "fired_rule_ids": _json_list(()),
                "resolution_id": SAME_Y_RESOLUTION_TRANSFER,
                "assignment_mode": ASSIGNMENT_MODE_LABEL_TRANSFER,
                "priority_path": "LABEL_TRANSFER",
                "technical_valid": bool(row.get("point_technical_valid", False)),
                "ambiguity_code": "none",
                "assignment_status": assignment_status,
                "train_inclusion_status": train_inclusion_status,
                "exclusion_reason": exclusion_reason,
                "source_task": POINT_TASK_SCOPE,
                "source_task_id": POINT_ASSIGNMENT_TASK_ID,
                "target_task": SAME_Y_TASK_SCOPE,
                "target_task_id": label_task_id,
                "source_assignment_id": row.get("point_assignment_id", pd.NA),
                "source_label": row.get("point_target_label", pd.NA),
                "eligibility_provenance": _eligibility_provenance_json(
                    technical_valid=row.get("point_technical_valid"),
                    intrinsic_eligibility=row.get("intrinsic_eligibility"),
                    intrinsic_exclusion_reason=row.get("intrinsic_exclusion_reason"),
                    point_assignment_status=row.get("point_assignment_status"),
                ),
            }
        )
    return pd.DataFrame(rows).convert_dtypes()


def _build_temporal_label_assignment(
    temporal_labels: pd.DataFrame,
    *,
    evidence_df: pd.DataFrame,
    point_assignment_lookup: pd.DataFrame,
    horizon_name: str,
) -> pd.DataFrame:
    merged = temporal_labels.merge(
        evidence_df[
            [
                "record.id",
                "intrinsic_eligibility",
                "intrinsic_exclusion_reason",
                "point_train_label_name",
                "low_run_length_ending_at_point",
                "positive_environmental_evidence_count",
                "eligible_for_training",
            ]
        ].rename(
            columns={
                "record.id": "sample_id",
                "intrinsic_eligibility": "window_intrinsic_eligibility",
                "intrinsic_exclusion_reason": "window_intrinsic_exclusion_reason",
            }
        ),
        on="sample_id",
        how="left",
        validate="one_to_one",
    ).merge(
        point_assignment_lookup.rename(
            columns={
                "assignment_id": "point_assignment_id",
                "target_label": "point_target_label",
                "technical_valid": "point_technical_valid",
                "assignment_status": "point_assignment_status",
            }
        ),
        on="sample_id",
        how="left",
        validate="many_to_one",
    )
    rows: list[dict[str, object]] = []
    for row in merged.to_dict(orient="records"):
        assignment_status, train_inclusion_status, exclusion_reason = _resolve_assignment_contract(
            label_status=row.get("label_status"),
            label_name=row.get("label_name"),
            intrinsic_exclusion_reason=row.get("window_intrinsic_exclusion_reason", row.get("intrinsic_exclusion_reason")),
            technical_invalid_reason=None,
        )
        low_run_length = _coerce_int(row.get("low_run_length_ending_at_point"))
        point_label_name = str(row.get("point_train_label_name")) if pd.notna(row.get("point_train_label_name")) else ""
        intrinsic_eligibility = bool(row.get("window_intrinsic_eligibility", row.get("intrinsic_eligibility", False)))
        persistent_low = point_label_name == POINT_LABELS[1] and low_run_length >= 3
        insufficient_persistence = point_label_name == POINT_LABELS[1] and low_run_length < 3
        point_unknown_transfer = point_label_name == POINT_LABELS[2]
        fired_rule_ids = ["LOW_RUN_ENDING_AT_ANCHOR_GE_3"] if persistent_low else []
        primary_fired_rule_id = fired_rule_ids[0] if fired_rule_ids else pd.NA
        resolution_id, assignment_mode = _temporal_resolution_and_mode(
            intrinsic_eligibility=intrinsic_eligibility,
            persistent_low=persistent_low,
            insufficient_persistence=insufficient_persistence,
            point_unknown_transfer=point_unknown_transfer,
        )
        sample_id = str(row["sample_id"])
        label_task_id = str(row["label_task_id"])
        target_label = row.get("label_name", pd.NA)
        is_transfer = assignment_mode == ASSIGNMENT_MODE_LABEL_TRANSFER
        rows.append(
            {
                "assignment_id": _assignment_id(sample_id=sample_id, label_task_id=label_task_id),
                "sample_id": sample_id,
                "label_task_id": label_task_id,
                "target": target_label,
                "target_label": target_label,
                "ontology_id": f"temporal_window_{horizon_name}_ontology_v1",
                "primary_rule_id": resolution_id,
                "primary_fired_rule_id": primary_fired_rule_id,
                "fired_rule_ids": _json_list(fired_rule_ids),
                "resolution_id": resolution_id,
                "assignment_mode": assignment_mode,
                "priority_path": TEMPORAL_PRIORITY_PATH,
                "technical_valid": bool(row.get("point_technical_valid", False)),
                "ambiguity_code": "none",
                "assignment_status": assignment_status,
                "train_inclusion_status": train_inclusion_status,
                "exclusion_reason": exclusion_reason,
                "source_task": POINT_TASK_SCOPE if is_transfer else pd.NA,
                "source_task_id": POINT_ASSIGNMENT_TASK_ID if is_transfer else pd.NA,
                "target_task": TEMPORAL_TASK_SCOPE,
                "target_task_id": label_task_id,
                "source_assignment_id": row.get("point_assignment_id", pd.NA) if is_transfer else pd.NA,
                "source_label": row.get("point_target_label", pd.NA) if is_transfer else pd.NA,
                "eligibility_provenance": _eligibility_provenance_json(
                    technical_valid=row.get("point_technical_valid"),
                    intrinsic_eligibility=row.get("window_intrinsic_eligibility", row.get("intrinsic_eligibility")),
                    intrinsic_exclusion_reason=row.get(
                        "window_intrinsic_exclusion_reason",
                        row.get("intrinsic_exclusion_reason"),
                    ),
                    eligible_for_training=row.get("eligible_for_training"),
                    point_assignment_status=row.get("point_assignment_status"),
                    point_label_name=row.get("point_train_label_name"),
                    low_run_length_ending_at_point=row.get("low_run_length_ending_at_point"),
                    positive_environmental_evidence_count=row.get("positive_environmental_evidence_count"),
                ),
            }
        )
    return pd.DataFrame(rows).convert_dtypes()


def _build_point_rule_firings(
    point_enriched_df: pd.DataFrame,
    threshold_lookup: dict[str, ThresholdRecord],
) -> pd.DataFrame:
    low_threshold_id = next(
        (threshold_id for threshold_id in threshold_lookup if threshold_id.startswith("low_relative_moisture_q10_")),
        "low_relative_moisture_q10_global",
    )
    ec_threshold_id = "ec_shift_abs_delta_q95_global"
    rows: list[dict[str, object]] = []
    for row in point_enriched_df.to_dict(orient="records"):
        sample_id = str(row["record.id"])
        technical_validity = bool(row.get("time_integrity_ok", False) and row.get("core_environment_fully_evaluable", False))
        low_flag = bool(row.get("low_relative_moisture_flag", False))
        thermal_flag = bool(row.get("thermal_evidence_flag", False))
        rise_flag = bool(row.get("moisture_rise_evidence_flag", False))
        ec_flag = bool(row.get("ec_shift_evidence_flag", False))
        unknown_rule_result = thermal_flag or rise_flag or ec_flag
        primary_semantic_rule_id = _point_primary_semantic_rule_id(
            technical_validity=technical_validity,
            low_flag=low_flag,
            unknown_rule_result=unknown_rule_result,
        )
        rows.extend(
            [
                _rule_row(
                    sample_id=sample_id,
                    label_task_id=POINT_ASSIGNMENT_TASK_ID,
                    rule_id="POINT_TECHNICAL_VALIDITY",
                    condition_id="time_integrity_ok",
                    condition_group_id="POINT_TECHNICAL_VALIDITY",
                    logical_operator="AND",
                    evidence_field="time_integrity_ok",
                    evidence_value=row.get("time_integrity_ok"),
                    comparison_operator="==",
                    threshold_id=pd.NA,
                    condition_result=bool(row.get("time_integrity_ok", False)),
                    rule_result=technical_validity,
                    priority_rank=0,
                    suppressed_by_rule_id=pd.NA,
                ),
                _rule_row(
                    sample_id=sample_id,
                    label_task_id=POINT_ASSIGNMENT_TASK_ID,
                    rule_id="POINT_TECHNICAL_VALIDITY",
                    condition_id="core_environment_fully_evaluable",
                    condition_group_id="POINT_TECHNICAL_VALIDITY",
                    logical_operator="AND",
                    evidence_field="core_environment_fully_evaluable",
                    evidence_value=row.get("core_environment_fully_evaluable"),
                    comparison_operator="==",
                    threshold_id=pd.NA,
                    condition_result=bool(row.get("core_environment_fully_evaluable", False)),
                    rule_result=technical_validity,
                    priority_rank=0,
                    suppressed_by_rule_id=pd.NA,
                ),
                _rule_row(
                    sample_id=sample_id,
                    label_task_id=POINT_ASSIGNMENT_TASK_ID,
                    rule_id="LOW_RELATIVE_MOISTURE_Q10",
                    condition_id="low_relative_moisture_q10",
                    condition_group_id="LOW_RELATIVE_MOISTURE_Q10",
                    logical_operator="AND",
                    evidence_field="npk.soil_moisture_pct",
                    evidence_value=row.get("npk.soil_moisture_pct"),
                    comparison_operator="<=",
                    threshold_id=low_threshold_id,
                    condition_result=low_flag,
                    rule_result=low_flag,
                    priority_rank=1,
                    suppressed_by_rule_id=pd.NA,
                ),
                _rule_row(
                    sample_id=sample_id,
                    label_task_id=POINT_ASSIGNMENT_TASK_ID,
                    rule_id="ENVIRONMENTAL_EVIDENCE_PRESENT",
                    condition_id="thermal_vpd_threshold_kpa",
                    condition_group_id="ENVIRONMENTAL_EVIDENCE_PRESENT",
                    logical_operator="OR",
                    evidence_field="derived.vpd_kpa",
                    evidence_value=row.get("derived.vpd_kpa"),
                    comparison_operator=">=",
                    threshold_id="thermal_vpd_threshold_kpa",
                    condition_result=thermal_flag,
                    rule_result=unknown_rule_result,
                    priority_rank=2,
                    suppressed_by_rule_id=(
                        "LOW_RELATIVE_MOISTURE_Q10"
                        if unknown_rule_result and primary_semantic_rule_id == "LOW_RELATIVE_MOISTURE_Q10"
                        else pd.NA
                    ),
                ),
                _rule_row(
                    sample_id=sample_id,
                    label_task_id=POINT_ASSIGNMENT_TASK_ID,
                    rule_id="ENVIRONMENTAL_EVIDENCE_PRESENT",
                    condition_id="rapid_wetting_delta_pp",
                    condition_group_id="ENVIRONMENTAL_EVIDENCE_PRESENT",
                    logical_operator="OR",
                    evidence_field="moisture_rise_delta",
                    evidence_value=row.get("moisture_rise_delta"),
                    comparison_operator=">=",
                    threshold_id="rapid_wetting_delta_pp",
                    condition_result=rise_flag,
                    rule_result=unknown_rule_result,
                    priority_rank=2,
                    suppressed_by_rule_id=(
                        "LOW_RELATIVE_MOISTURE_Q10"
                        if unknown_rule_result and primary_semantic_rule_id == "LOW_RELATIVE_MOISTURE_Q10"
                        else pd.NA
                    ),
                ),
                _rule_row(
                    sample_id=sample_id,
                    label_task_id=POINT_ASSIGNMENT_TASK_ID,
                    rule_id="ENVIRONMENTAL_EVIDENCE_PRESENT",
                    condition_id="ec_shift_abs_delta_q95_global",
                    condition_group_id="ENVIRONMENTAL_EVIDENCE_PRESENT",
                    logical_operator="OR",
                    evidence_field="ec_shift_delta_abs",
                    evidence_value=row.get("ec_shift_delta_abs"),
                    comparison_operator=">=",
                    threshold_id=ec_threshold_id,
                    condition_result=ec_flag,
                    rule_result=unknown_rule_result,
                    priority_rank=2,
                    suppressed_by_rule_id=(
                        "LOW_RELATIVE_MOISTURE_Q10"
                        if unknown_rule_result and primary_semantic_rule_id == "LOW_RELATIVE_MOISTURE_Q10"
                        else pd.NA
                    ),
                ),
            ]
        )
    return pd.DataFrame(rows).convert_dtypes()


def _build_temporal_rule_firings(
    evidence_df: pd.DataFrame,
    *,
    horizon_name: str,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for row in evidence_df.to_dict(orient="records"):
        sample_id = str(row["record.id"])
        intrinsic_eligibility = bool(row.get("intrinsic_eligibility", False))
        persistent_low = (
            row.get("point_train_label_name") == POINT_LABELS[1]
            and pd.notna(row.get("low_run_length_ending_at_point"))
            and int(row["low_run_length_ending_at_point"]) >= 3
        )
        rows.extend(
            [
                _rule_row(
                    sample_id=sample_id,
                    label_task_id=f"v2_temporal_{horizon_name}",
                    rule_id=f"WINDOW_ELIGIBILITY_{horizon_name}",
                    condition_id=f"window_eligibility_{horizon_name}",
                    condition_group_id=f"WINDOW_ELIGIBILITY_{horizon_name}",
                    logical_operator="AND",
                    evidence_field="eligible_for_training",
                    evidence_value=row.get("eligible_for_training"),
                    comparison_operator="==",
                    threshold_id=pd.NA,
                    condition_result=intrinsic_eligibility,
                    rule_result=intrinsic_eligibility,
                    priority_rank=0,
                    suppressed_by_rule_id=pd.NA,
                ),
                _rule_row(
                    sample_id=sample_id,
                    label_task_id=f"v2_temporal_{horizon_name}",
                    rule_id="LOW_RUN_ENDING_AT_ANCHOR_GE_3",
                    condition_id="low_run_length_ending_at_point",
                    condition_group_id="LOW_RUN_ENDING_AT_ANCHOR_GE_3",
                    logical_operator="AND",
                    evidence_field="low_run_length_ending_at_point",
                    evidence_value=row.get("low_run_length_ending_at_point"),
                    comparison_operator=">=",
                    threshold_id="persistent_low_run_min_steps",
                    condition_result=persistent_low,
                    rule_result=persistent_low,
                    priority_rank=1,
                    suppressed_by_rule_id=pd.NA,
                ),
            ]
        )
    return pd.DataFrame(rows).convert_dtypes()


def _build_rule_registry() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "rule_id": "POINT_TECHNICAL_VALIDITY",
                "label_scope": POINT_ASSIGNMENT_TASK_ID,
                "priority_rank": 0,
                "condition_logic": "AND",
                "rule_version": WEAK_LABELS_VERSION,
                "scientific_role": "technical_validity_gate",
            },
            {
                "rule_id": "LOW_RELATIVE_MOISTURE_Q10",
                "label_scope": POINT_ASSIGNMENT_TASK_ID,
                "priority_rank": 1,
                "condition_logic": "AND",
                "rule_version": WEAK_LABELS_VERSION,
                "scientific_role": "direct_rule_source",
            },
            {
                "rule_id": "ENVIRONMENTAL_EVIDENCE_PRESENT",
                "label_scope": POINT_ASSIGNMENT_TASK_ID,
                "priority_rank": 2,
                "condition_logic": "OR",
                "rule_version": WEAK_LABELS_VERSION,
                "scientific_role": "unknown_environment_gate",
            },
            {
                "rule_id": "WINDOW_ELIGIBILITY_3h",
                "label_scope": "v2_temporal_3h",
                "priority_rank": 0,
                "condition_logic": "AND",
                "rule_version": WEAK_LABELS_VERSION,
                "scientific_role": "window_eligibility_gate",
            },
            {
                "rule_id": "WINDOW_ELIGIBILITY_8h",
                "label_scope": "v2_temporal_8h",
                "priority_rank": 0,
                "condition_logic": "AND",
                "rule_version": WEAK_LABELS_VERSION,
                "scientific_role": "window_eligibility_gate",
            },
            {
                "rule_id": "LOW_RUN_ENDING_AT_ANCHOR_GE_3",
                "label_scope": "v2_temporal",
                "priority_rank": 1,
                "condition_logic": "AND",
                "rule_version": WEAK_LABELS_VERSION,
                "scientific_role": "temporal_history_persistence",
            },
        ]
    ).convert_dtypes()


def _build_threshold_registry(
    *,
    threshold_records: tuple[ThresholdRecord, ...],
    weak_labels_repo_root: Path,
) -> pd.DataFrame:
    code_hash = stable_digest({"weak_labels_version": WEAK_LABELS_VERSION, "repo_root": str(weak_labels_repo_root)})
    rows: list[dict[str, object]] = []
    for record in threshold_records:
        statistic = record.threshold_statistic
        if statistic is None:
            if "q10" in record.threshold_id:
                statistic = "quantile_0.10"
            elif "q95" in record.threshold_id:
                statistic = "quantile_0.95"
            else:
                statistic = "fixed_value"
        parameters = record.threshold_parameters_json
        if parameters is None:
            parameters = json.dumps(
                {
                    "value": record.value,
                    "segment_scope": record.segment_scope,
                    "source_fields": list(record.source_fields),
                },
                ensure_ascii=True,
                separators=(",", ":"),
            )
        rows.append(
            {
                "threshold_id": record.threshold_id,
                "threshold_version": record.threshold_version,
                "fit_mode": record.fit_mode,
                "source_fields_json": json.dumps(list(record.source_fields), ensure_ascii=True, separators=(",", ":")),
                "fit_partition": record.fit_partition,
                "fit_record_count": record.fit_record_count,
                "fit_record_hash": record.fit_record_hash,
                "segment_scope": record.segment_scope,
                "threshold_value": record.value,
                "notes": record.notes,
                "threshold_fit_sample_hash": record.threshold_fit_sample_hash or record.fit_record_hash,
                "threshold_fit_start": record.threshold_fit_start,
                "threshold_fit_end": record.threshold_fit_end,
                "threshold_statistic": statistic,
                "threshold_parameters_json": parameters,
                "code_hash": record.code_hash or code_hash,
            }
        )
    return pd.DataFrame(rows).convert_dtypes()


def _build_label_source_dependency() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "label_task_id": POINT_ASSIGNMENT_TASK_ID,
                "root_measurement_source": "npk.soil_moisture_pct",
                "source_role": "direct_rule_source",
                "dependency_status": "PRIMARY",
            },
            {
                "label_task_id": POINT_ASSIGNMENT_TASK_ID,
                "root_measurement_source": "derived.vpd_kpa",
                "source_role": "rule_metadata_source",
                "dependency_status": "PRIMARY",
            },
            {
                "label_task_id": POINT_ASSIGNMENT_TASK_ID,
                "root_measurement_source": "ec_shift_delta_abs",
                "source_role": "proxy_rule_source",
                "dependency_status": "SUPPORTING",
            },
            {
                "label_task_id": "v2_same_y_3h",
                "root_measurement_source": "v0_v1_point_detailed.target_label",
                "source_role": "label_transfer_source",
                "dependency_status": "PRIMARY",
            },
            {
                "label_task_id": "v2_same_y_8h",
                "root_measurement_source": "v0_v1_point_detailed.target_label",
                "source_role": "label_transfer_source",
                "dependency_status": "PRIMARY",
            },
            {
                "label_task_id": "v2_temporal_3h",
                "root_measurement_source": "low_run_length_ending_at_point",
                "source_role": "derived_history_source",
                "dependency_status": "PRIMARY",
            },
            {
                "label_task_id": "v2_temporal_3h",
                "root_measurement_source": "v0_v1_point_detailed.target_label",
                "source_role": "label_transfer_source",
                "dependency_status": "PRIMARY",
            },
            {
                "label_task_id": "v2_temporal_8h",
                "root_measurement_source": "low_run_length_ending_at_point",
                "source_role": "derived_history_source",
                "dependency_status": "PRIMARY",
            },
            {
                "label_task_id": "v2_temporal_8h",
                "root_measurement_source": "v0_v1_point_detailed.target_label",
                "source_role": "label_transfer_source",
                "dependency_status": "PRIMARY",
            },
        ]
    ).convert_dtypes()


def _resolve_assignment_contract(
    *,
    label_status: object,
    label_name: object,
    intrinsic_exclusion_reason: object,
    technical_invalid_reason: object,
) -> tuple[str, str, object]:
    label_status_str = str(label_status) if pd.notna(label_status) else ""
    label_name_str = str(label_name) if pd.notna(label_name) else ""
    if technical_invalid_reason is not None and pd.notna(technical_invalid_reason):
        return "technical_invalid", "excluded", technical_invalid_reason
    if label_status_str == LABEL_STATUS_EXCLUDED_TIME:
        return "technical_invalid", "excluded", "time_integrity_invalid"
    if label_status_str in {LABEL_STATUS_ABSTAIN, LABEL_STATUS_EXCLUDED_WINDOW}:
        exclusion_reason = intrinsic_exclusion_reason if pd.notna(intrinsic_exclusion_reason) else "rule_abstention"
        return "rule_abstention", "excluded", exclusion_reason
    if label_name_str == V2_TEMPORAL_EXCLUDED_LABEL:
        return "rule_abstention", "excluded", "insufficient_history"
    if not label_name_str or label_name_str.lower() == "nan":
        return "missing_target", "excluded", intrinsic_exclusion_reason if pd.notna(intrinsic_exclusion_reason) else "missing_target"
    if "unknown" in label_name_str:
        return "weak_label_unknown", "included", pd.NA
    return "assigned", "included", pd.NA


def _point_semantic_fired_rule_ids(
    *,
    technical_valid: bool,
    low_flag: bool,
    unknown_rule_result: bool,
) -> list[str]:
    if not technical_valid:
        return []
    fired_rule_ids: list[str] = []
    if low_flag:
        fired_rule_ids.append("LOW_RELATIVE_MOISTURE_Q10")
    if unknown_rule_result:
        fired_rule_ids.append("ENVIRONMENTAL_EVIDENCE_PRESENT")
    return fired_rule_ids


def _point_primary_semantic_rule_id(
    *,
    technical_validity: bool,
    low_flag: bool,
    unknown_rule_result: bool,
) -> str | None:
    fired_rule_ids = _point_semantic_fired_rule_ids(
        technical_valid=technical_validity,
        low_flag=low_flag,
        unknown_rule_result=unknown_rule_result,
    )
    return fired_rule_ids[0] if fired_rule_ids else None


def _point_resolution_id(
    *,
    technical_valid: bool,
    low_flag: bool,
    unknown_rule_result: bool,
    technical_invalid_reason: object,
) -> str:
    if not technical_valid:
        return (
            POINT_RESOLUTION_TECHNICAL_INVALID
            if technical_invalid_reason is not None and pd.notna(technical_invalid_reason)
            else POINT_RESOLUTION_CORE_ENVIRONMENT_INELIGIBLE
        )
    if low_flag:
        return POINT_RESOLUTION_LOW
    if unknown_rule_result:
        return POINT_RESOLUTION_UNKNOWN
    return POINT_RESOLUTION_NORMAL


def _temporal_resolution_and_mode(
    *,
    intrinsic_eligibility: bool,
    persistent_low: bool,
    insufficient_persistence: bool,
    point_unknown_transfer: bool,
) -> tuple[str, str]:
    if not intrinsic_eligibility:
        return TEMPORAL_RESOLUTION_WINDOW_INELIGIBLE, ASSIGNMENT_MODE_EXCLUDED
    if persistent_low:
        return TEMPORAL_RESOLUTION_PERSISTENT_LOW, ASSIGNMENT_MODE_RULE_EVALUATION
    if insufficient_persistence:
        return TEMPORAL_RESOLUTION_UNKNOWN_INSUFFICIENT_PERSISTENCE, ASSIGNMENT_MODE_RULE_EVALUATION
    if point_unknown_transfer:
        return TEMPORAL_RESOLUTION_POINT_UNKNOWN_TRANSFER, ASSIGNMENT_MODE_LABEL_TRANSFER
    return TEMPORAL_RESOLUTION_NORMAL, ASSIGNMENT_MODE_RULE_EVALUATION


def _assignment_id(*, sample_id: str, label_task_id: str) -> str:
    return f"{label_task_id}::{sample_id}"


def _eligibility_provenance_json(**kwargs: object) -> str:
    payload: dict[str, object] = {}
    for key, value in kwargs.items():
        if value is None or pd.isna(value):
            payload[key] = None
        elif isinstance(value, pd.Timestamp):
            payload[key] = value.isoformat()
        elif isinstance(value, (bool, int, float, str)):
            payload[key] = value
        else:
            payload[key] = str(value)
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _json_list(values: list[str] | tuple[str, ...]) -> str:
    return json.dumps(list(values), ensure_ascii=True, separators=(",", ":"))


def _coerce_int(value: object) -> int:
    if value is None or pd.isna(value):
        return 0
    return int(value)


def _rule_row(
    *,
    sample_id: str,
    label_task_id: str,
    rule_id: str,
    condition_id: str,
    condition_group_id: str,
    logical_operator: str,
    evidence_field: str,
    evidence_value: object,
    comparison_operator: str,
    threshold_id: object,
    condition_result: bool,
    rule_result: bool,
    priority_rank: int,
    suppressed_by_rule_id: object,
) -> dict[str, object]:
    return {
        "sample_id": sample_id,
        "label_task_id": label_task_id,
        "rule_id": rule_id,
        "condition_id": condition_id,
        "condition_group_id": condition_group_id,
        "logical_operator": logical_operator,
        "evidence_field": evidence_field,
        "evidence_value": _normalize_evidence_value(evidence_value),
        "comparison_operator": comparison_operator,
        "threshold_id": threshold_id,
        "condition_result": condition_result,
        "rule_result": rule_result,
        "priority_rank": priority_rank,
        "suppressed_by_rule_id": suppressed_by_rule_id,
    }


def _normalize_evidence_value(value: object) -> object:
    if value is None or pd.isna(value):
        return pd.NA
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return format(float(value), ".15g")
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), default=str)
