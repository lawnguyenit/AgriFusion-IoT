from __future__ import annotations

import json
from dataclasses import dataclass

import pandas as pd

from Backend.Benchmark.validity_lifecycle.contracts import EnvironmentSpec, ProtocolLifecycleInputs
from Backend.Benchmark.validity_lifecycle.defaults import POINT_TARGET_MAP
from Backend.Benchmark.weak_labels.shared.helpers import coerce_boolean_series, resolve_local_timestamp_series


POINT_VIEW_IDS = ("v0_point", "v1_point")
WINDOW_VIEW_SPECS: tuple[tuple[str, str], ...] = (
    ("v2_same_y_mini_3h", "3h"),
    ("v2_same_y_full_3h", "3h"),
    ("v2_same_y_mini_8h", "8h"),
    ("v2_same_y_full_8h", "8h"),
)


@dataclass(frozen=True)
class ObservationArtifacts:
    observation_registry: pd.DataFrame
    view_observation_registry: pd.DataFrame


def assign_environment_id(
    timestamp_local: pd.Timestamp,
    environment_specs: tuple[EnvironmentSpec, ...],
) -> EnvironmentSpec | None:
    if pd.isna(timestamp_local):
        return None
    for spec in environment_specs:
        if spec.start_local <= timestamp_local < spec.end_local:
            return spec
    return None


def build_observation_artifacts(
    *,
    inputs: ProtocolLifecycleInputs,
    environment_specs: tuple[EnvironmentSpec, ...],
) -> ObservationArtifacts:
    observation_registry = _build_observation_registry(inputs=inputs, environment_specs=environment_specs)
    view_observation_registry = _build_view_observation_registry(observation_registry)
    return ObservationArtifacts(
        observation_registry=observation_registry,
        view_observation_registry=view_observation_registry,
    )


def _build_observation_registry(
    *,
    inputs: ProtocolLifecycleInputs,
    environment_specs: tuple[EnvironmentSpec, ...],
) -> pd.DataFrame:
    working = inputs.canonical_df.copy()
    working["timestamp_local"] = resolve_local_timestamp_series(working)
    deployment_domains = inputs.deployment_domains.rename(columns={"record_id": "record.id"}).loc[
        :,
        ["record.id", "deployment_domain_id", "deployment_domain_name"],
    ]
    point_train = inputs.point_labels_train.loc[
        inputs.point_labels_train["task_id"].astype("string") == "v0_point_train",
        [
            "sample_id",
            "label_name",
            "label_status",
            "intrinsic_eligibility",
            "intrinsic_exclusion_reason",
            "primary_rule_id",
            "rule_version",
        ],
    ].rename(
        columns={
            "sample_id": "record.id",
            "label_name": "point_label_name",
            "label_status": "point_label_status",
            "intrinsic_eligibility": "point_intrinsic_eligibility",
            "intrinsic_exclusion_reason": "point_intrinsic_exclusion_reason",
            "primary_rule_id": "point_primary_rule_id",
            "rule_version": "point_rule_version",
        }
    )
    point_detailed = inputs.point_labels_detailed.loc[
        :,
        ["sample_id", "sensitivity_label_name"],
    ].rename(columns={"sample_id": "record.id"})
    same_y_3h = _rename_same_y_frame(inputs.v2_same_y_labels, task_id="v2_same_y_3h", horizon="3h")
    same_y_8h = _rename_same_y_frame(inputs.v2_same_y_labels, task_id="v2_same_y_8h", horizon="8h")
    evidence_3h = _rename_window_evidence_frame(inputs.v2_temporal_evidence_3h, horizon="3h")
    evidence_8h = _rename_window_evidence_frame(inputs.v2_temporal_evidence_8h, horizon="8h")

    for frame in (
        deployment_domains,
        point_train,
        point_detailed,
        same_y_3h,
        same_y_8h,
        evidence_3h,
        evidence_8h,
    ):
        working = working.merge(frame, on="record.id", how="left", validate="one_to_one")

    technical_valid = (
        coerce_boolean_series(working.get("sht.valid", pd.Series(False, index=working.index)))
        & coerce_boolean_series(working.get("npk.valid", pd.Series(False, index=working.index)))
        & ~coerce_boolean_series(working.get("sensor.any_fault", pd.Series(False, index=working.index)))
    )
    replayed = coerce_boolean_series(working.get("delivery.replayed_raw", pd.Series(False, index=working.index)))
    buffered = coerce_boolean_series(working.get("delivery.was_buffered_raw", pd.Series(False, index=working.index)))
    gap_flag = coerce_boolean_series(working.get("record.gap_flag", pd.Series(False, index=working.index)))
    missing_slot_count = pd.to_numeric(working.get("record.missing_slot_count", pd.Series(0, index=working.index)), errors="coerce").fillna(0).astype(int)
    point_target = working["point_label_name"].astype("string").map(POINT_TARGET_MAP).astype("string")

    environment_rows = [assign_environment_id(timestamp, environment_specs) for timestamp in working["timestamp_local"]]
    working["environment_id"] = pd.Series([row.environment_id if row is not None else "OUT_OF_SCOPE" for row in environment_rows], dtype="string")
    working["environment_stage_name"] = pd.Series([row.stage_name if row is not None else "Out of scope" for row in environment_rows], dtype="string")
    working["environment_boundary_status"] = pd.Series([row.boundary_status if row is not None else "out_of_scope" for row in environment_rows], dtype="string")
    working["environment_boundary_reason"] = pd.Series([row.boundary_reason if row is not None else "Outside configured lifecycle ranges." for row in environment_rows], dtype="string")

    threshold_source = str(
        inputs.protocol_validation_report.get("primary_threshold_policy")
        or "FROZEN_INITIAL_SOURCE"
    )
    working["sample_id"] = working["record.id"].astype("string")
    working["timestamp"] = pd.to_numeric(working["record.ts_sample"], errors="coerce").astype("Int64")
    working["deployment_id"] = working["deployment_domain_id"].fillna(working["deployment_domain_name"]).astype("string")
    working["position_id"] = working["record.node_id"].astype("string")
    working["segment_id"] = working["record.segment_id"].astype("string")
    working["day_id"] = working["timestamp_local"].dt.strftime("%Y-%m-%d").astype("string")
    working["point_target"] = point_target
    working["technical_valid"] = technical_valid.astype("boolean")
    working["eligible_3h"] = working["same_y_3h_intrinsic_eligibility"].fillna(False).astype("boolean")
    working["eligible_8h"] = working["same_y_8h_intrinsic_eligibility"].fillna(False).astype("boolean")
    working["replayed"] = replayed.astype("boolean")
    working["buffered"] = buffered.astype("boolean")
    working["missing_slot_count"] = missing_slot_count.astype("Int64")
    working["gap_flag"] = gap_flag.astype("boolean")
    working["continuity_status"] = _derive_continuity_status(
        technical_valid=technical_valid,
        replayed=replayed,
        buffered=buffered,
        gap_flag=gap_flag,
        missing_slot_count=missing_slot_count,
        segment_boundary_before=coerce_boolean_series(working.get("record.segment_boundary_before", pd.Series(False, index=working.index))),
    ).astype("string")
    working["label_rule_id"] = working["point_primary_rule_id"].astype("string")
    working["threshold_source"] = threshold_source

    selected_columns = [
        "sample_id",
        "timestamp",
        "timestamp_local",
        "environment_id",
        "environment_stage_name",
        "environment_boundary_status",
        "environment_boundary_reason",
        "deployment_id",
        "position_id",
        "segment_id",
        "day_id",
        "point_target",
        "point_label_name",
        "point_label_status",
        "point_intrinsic_eligibility",
        "point_intrinsic_exclusion_reason",
        "technical_valid",
        "eligible_3h",
        "eligible_8h",
        "missing_slot_count",
        "gap_flag",
        "replayed",
        "buffered",
        "continuity_status",
        "label_rule_id",
        "threshold_source",
        "sensitivity_label_name",
        "same_y_3h_label_name",
        "same_y_3h_label_status",
        "same_y_3h_intrinsic_eligibility",
        "same_y_3h_intrinsic_exclusion_reason",
        "same_y_8h_label_name",
        "same_y_8h_label_status",
        "same_y_8h_intrinsic_eligibility",
        "same_y_8h_intrinsic_exclusion_reason",
        "window_3h_eligible_for_training",
        "window_3h_intrinsic_exclusion_reason",
        "window_3h_valid_observation_count",
        "window_3h_actual_window_span_sec",
        "window_3h_max_internal_gap_sec",
        "window_3h_window_reset_reason",
        "window_8h_eligible_for_training",
        "window_8h_intrinsic_exclusion_reason",
        "window_8h_valid_observation_count",
        "window_8h_actual_window_span_sec",
        "window_8h_max_internal_gap_sec",
        "window_8h_window_reset_reason",
        "npk.ec",
        "npk.ph",
        "npk.n_proxy",
        "npk.p_proxy",
        "npk.k_proxy",
        "npk.soil_moisture_pct",
    ]
    return working.loc[:, selected_columns].convert_dtypes()


def _build_view_observation_registry(observation_registry: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for row in observation_registry.to_dict(orient="records"):
        rows.extend(_point_view_rows(row))
        rows.extend(_window_view_rows(row))
    return pd.DataFrame(rows).convert_dtypes()


def _point_view_rows(row: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for view_id in POINT_VIEW_IDS:
        view_eligible = bool(row.get("point_label_status") == "LABELED" and bool(row.get("technical_valid")) and pd.notna(row.get("point_target")))
        rows.append(
            _base_view_row(
                row,
                view_id=view_id,
                horizon="point",
                label_task_id="v0_point_train" if view_id == "v0_point" else "v1_point_train",
                label_name=row.get("point_label_name"),
                label_status=row.get("point_label_status"),
                target_label=row.get("point_target"),
                view_eligible=view_eligible,
                view_exclusion_reason=_first_non_empty(
                    row.get("point_intrinsic_exclusion_reason"),
                    None if view_eligible else row.get("point_label_status"),
                    None if bool(row.get("technical_valid")) else "technical_invalid",
                ),
            )
        )
    return rows


def _window_view_rows(row: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for view_id, horizon in WINDOW_VIEW_SPECS:
        label_name = row.get(f"same_y_{horizon}_label_name")
        label_status = row.get(f"same_y_{horizon}_label_status")
        view_eligible = bool(label_status == "LABELED" and pd.notna(row.get("point_target")))
        rows.append(
            _base_view_row(
                row,
                view_id=view_id,
                horizon=horizon,
                label_task_id=f"v2_same_y_{horizon}",
                label_name=label_name,
                label_status=label_status,
                target_label=row.get("point_target"),
                view_eligible=view_eligible,
                view_exclusion_reason=_first_non_empty(
                    row.get(f"same_y_{horizon}_intrinsic_exclusion_reason"),
                    None if view_eligible else label_status,
                ),
            )
        )
    return rows


def _base_view_row(
    source_row: dict[str, object],
    *,
    view_id: str,
    horizon: str,
    label_task_id: str,
    label_name: object,
    label_status: object,
    target_label: object,
    view_eligible: bool,
    view_exclusion_reason: object,
) -> dict[str, object]:
    return {
        "sample_id": source_row.get("sample_id"),
        "timestamp": source_row.get("timestamp"),
        "timestamp_local": source_row.get("timestamp_local"),
        "environment_id": source_row.get("environment_id"),
        "environment_stage_name": source_row.get("environment_stage_name"),
        "deployment_id": source_row.get("deployment_id"),
        "position_id": source_row.get("position_id"),
        "segment_id": source_row.get("segment_id"),
        "day_id": source_row.get("day_id"),
        "view_id": view_id,
        "view_role": "window" if view_id.startswith("v2_") else "point",
        "view_horizon": horizon,
        "label_task_id": label_task_id,
        "view_label_name": label_name,
        "view_label_status": label_status,
        "target_label": target_label,
        "view_eligible": view_eligible,
        "view_exclusion_reason": view_exclusion_reason,
        "technical_valid": source_row.get("technical_valid"),
        "eligible_3h": source_row.get("eligible_3h"),
        "eligible_8h": source_row.get("eligible_8h"),
        "missing_slot_count": source_row.get("missing_slot_count"),
        "gap_flag": source_row.get("gap_flag"),
        "replayed": source_row.get("replayed"),
        "buffered": source_row.get("buffered"),
        "continuity_status": source_row.get("continuity_status"),
    }


def _rename_same_y_frame(frame: pd.DataFrame, *, task_id: str, horizon: str) -> pd.DataFrame:
    return frame.loc[
        frame["task_id"].astype("string") == task_id,
        [
            "sample_id",
            "label_name",
            "label_status",
            "intrinsic_eligibility",
            "intrinsic_exclusion_reason",
        ],
    ].rename(
        columns={
            "sample_id": "record.id",
            "label_name": f"same_y_{horizon}_label_name",
            "label_status": f"same_y_{horizon}_label_status",
            "intrinsic_eligibility": f"same_y_{horizon}_intrinsic_eligibility",
            "intrinsic_exclusion_reason": f"same_y_{horizon}_intrinsic_exclusion_reason",
        }
    )


def _rename_window_evidence_frame(frame: pd.DataFrame, *, horizon: str) -> pd.DataFrame:
    return frame.loc[
        :,
        [
            "record.id",
            "eligible_for_training",
            "intrinsic_exclusion_reason",
            "valid_observation_count",
            "actual_window_span_sec",
            "max_internal_gap_sec",
            "window_reset_reason",
        ],
    ].rename(
        columns={
            "eligible_for_training": f"window_{horizon}_eligible_for_training",
            "intrinsic_exclusion_reason": f"window_{horizon}_intrinsic_exclusion_reason",
            "valid_observation_count": f"window_{horizon}_valid_observation_count",
            "actual_window_span_sec": f"window_{horizon}_actual_window_span_sec",
            "max_internal_gap_sec": f"window_{horizon}_max_internal_gap_sec",
            "window_reset_reason": f"window_{horizon}_window_reset_reason",
        }
    )


def _derive_continuity_status(
    *,
    technical_valid: pd.Series,
    replayed: pd.Series,
    buffered: pd.Series,
    gap_flag: pd.Series,
    missing_slot_count: pd.Series,
    segment_boundary_before: pd.Series,
) -> pd.Series:
    status = pd.Series(["CONTIGUOUS"] * len(technical_valid), index=technical_valid.index, dtype="string")
    status.loc[segment_boundary_before.fillna(False).astype(bool)] = "RESET"
    status.loc[gap_flag.fillna(False).astype(bool) | missing_slot_count.fillna(0).astype(int).gt(0)] = "GAPPED"
    status.loc[buffered.fillna(False).astype(bool) | replayed.fillna(False).astype(bool)] = "BUFFERED_OR_REPLAYED"
    status.loc[~technical_valid.fillna(False).astype(bool)] = "TECHNICAL_INVALID"
    return status


def _first_non_empty(*values: object) -> object:
    for value in values:
        if value is None or value is pd.NA:
            continue
        text = str(value).strip()
        if text and text.lower() != "nan" and text.lower() != "<na>":
            return value
    return pd.NA
