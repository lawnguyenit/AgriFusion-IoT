from __future__ import annotations

import math

import pandas as pd

from Backend.Benchmark.protocol_registry.contracts import ProtocolRegistry
from Backend.Benchmark.weak_labels.lifecycle.phase_a_readiness.continuity import STRICT_POLICY_ID


THERMAL_THRESHOLD_KPA = 2.5
RISE_THRESHOLD_PP = 5.0


def build_rule_applicability(e1_df: pd.DataFrame) -> pd.DataFrame:
    working = e1_df.copy()
    sht_packet = _bool_series(working["sht.packet_present"])
    soil_packet = _bool_series(working["npk.packet_present"])
    sht_valid = _bool_series(working["sht.valid"])
    soil_valid = _bool_series(working["npk.valid"])
    moisture = pd.to_numeric(working["npk.soil_moisture_pct"], errors="coerce")
    ec = pd.to_numeric(working["npk.ec"], errors="coerce")
    temp = pd.to_numeric(working["sht.temp_c"], errors="coerce")
    humidity = pd.to_numeric(working["sht.humidity_pct"], errors="coerce")
    working["time_integrity_ok"] = (
        working["sample_time"].notna() & working["record.segment_id"].notna()
    ).astype("boolean")
    working["sht_applicable"] = sht_packet.astype("boolean")
    working["soil_sensor_applicable"] = soil_packet.astype("boolean")
    working["sht_valid"] = sht_valid.astype("boolean")
    working["soil_sensor_valid"] = soil_valid.astype("boolean")
    working["soil_moisture_evaluable"] = (soil_valid & moisture.notna()).astype("boolean")
    working["vpd_evaluable"] = (sht_valid & temp.notna() & humidity.notna()).astype("boolean")
    working["moisture_delta_evaluable"] = (
        working["soil_moisture_evaluable"].fillna(False)
        & working["strictly_consecutive_from_previous"].fillna(False)
        & pd.to_numeric(working["moisture_delta_strict"], errors="coerce").notna()
    ).astype("boolean")
    working["ec_delta_evaluable"] = (
        soil_valid
        & ec.notna()
        & working["strictly_consecutive_from_previous"].fillna(False)
        & pd.to_numeric(working["ec_delta_abs_strict"], errors="coerce").notna()
    ).astype("boolean")
    working["low_rule_applicability"] = working["soil_moisture_evaluable"].astype("boolean")
    working["thermal_rule_applicability"] = working["vpd_evaluable"].astype("boolean")
    working["rise_rule_applicability"] = working["moisture_delta_evaluable"].astype("boolean")
    working["ec_shift_rule_applicability"] = working["ec_delta_evaluable"].astype("boolean")
    working["low_target_eligibility"] = (
        working["time_integrity_ok"].fillna(False) & working["soil_moisture_evaluable"].fillna(False)
    ).astype("boolean")
    working["full_point_ontology_eligibility"] = (
        working["low_target_eligibility"].fillna(False)
        & working["thermal_rule_applicability"].fillna(False)
        & working["rise_rule_applicability"].fillna(False)
        & working["ec_shift_rule_applicability"].fillna(False)
    ).astype("boolean")
    working["derived_vpd_kpa"] = _compute_vpd(temp, humidity)
    return working.convert_dtypes()


def build_candidate_evidence(
    applicability_df: pd.DataFrame,
    *,
    low_q10: float,
    ec_q95: float,
) -> pd.DataFrame:
    working = applicability_df.copy()
    moisture = pd.to_numeric(working["npk.soil_moisture_pct"], errors="coerce")
    vpd = pd.to_numeric(working["derived_vpd_kpa"], errors="coerce")
    rise = pd.to_numeric(working["moisture_delta_strict"], errors="coerce")
    ec_delta = pd.to_numeric(working["ec_delta_abs_strict"], errors="coerce")
    working["low_flag"] = _nullable_flag(working["low_rule_applicability"], moisture.le(low_q10))
    working["thermal_flag"] = _nullable_flag(
        working["thermal_rule_applicability"], vpd.ge(THERMAL_THRESHOLD_KPA)
    )
    working["moisture_rise_flag"] = _nullable_flag(
        working["rise_rule_applicability"], rise.ge(RISE_THRESHOLD_PP)
    )
    working["ec_shift_flag"] = _nullable_flag(
        working["ec_shift_rule_applicability"], ec_delta.ge(ec_q95)
    )
    working["candidate_resolution"] = working.apply(_candidate_resolution, axis=1).astype("string")
    working["candidate_resolution_policy_id"] = "FULL_CONTEXT_V1"
    working["evidence_contract_id"] = "E1_DISCOVERY_Q10_FULL_CONTEXT_V1"
    working["low_threshold_candidate_id"] = "LOW_MOISTURE_Q10_E1_DISCOVERY_CANDIDATE"
    working["ec_shift_threshold_candidate_id"] = "EC_SHIFT_Q95_E1_DISCOVERY_CANDIDATE"
    working["thermal_threshold_id"] = "THERMAL_VPD_FIXED_2_5_REFERENCE"
    working["rise_threshold_id"] = "MOISTURE_RISE_FIXED_5PP_REFERENCE"
    working["strict_policy_candidate_id"] = STRICT_POLICY_ID
    return working.convert_dtypes()


def build_evidence_inventory(
    evidence_df: pd.DataFrame,
    registry: ProtocolRegistry,
    dependency_audit: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    eligible = evidence_df.loc[evidence_df["low_target_eligibility"].fillna(False).astype(bool)].copy()
    unique_inventory = _aggregate_inventory(
        eligible,
        inventory_scope="E1_UNIQUE_RECORD",
        grouping_prefix={
            "environment_id": "E1",
            "protocol_role": "SOURCE_DISCOVERY",
            "fold_policy_id": pd.NA,
            "fold_id": pd.NA,
            "split_role": "UNIQUE_RECORD",
            "visibility_status": "FULL",
        },
        evaluation_eligible_record_ids=None,
    )
    projection_rows: list[pd.DataFrame] = []
    folds = registry.e1_fold_registry.loc[
        registry.e1_fold_registry["evaluation_usable"].fillna(False).astype(bool)
    ]
    for fold in folds.to_dict(orient="records"):
        for split_role in ("train", "validation", "test"):
            start = pd.Timestamp(fold[f"{split_role}_start"])
            end = pd.Timestamp(fold[f"{split_role}_end"])
            projected = eligible.loc[eligible["sample_time"].ge(start) & eligible["sample_time"].lt(end)]
            admissible = dependency_audit.loc[
                (
                    dependency_audit["fold_policy_id"].astype("string")
                    == str(fold["fold_policy_id"])
                )
                & (
                    dependency_audit["fold_id"].astype("string")
                    == str(fold["fold_id"])
                )
                & (
                    dependency_audit["split_role"].astype("string")
                    == split_role
                )
                & dependency_audit["window_horizon_hours"].eq(3)
                & dependency_audit["persistence_k"].eq(3)
                & dependency_audit["evaluation_dependency_eligible"]
                .fillna(False)
                .astype(bool)
            ]
            projection_rows.append(
                _aggregate_inventory(
                    projected,
                    inventory_scope="FOLD_PROJECTION",
                    grouping_prefix={
                        "environment_id": "E1",
                        "protocol_role": "SOURCE_DISCOVERY",
                        "fold_policy_id": fold["fold_policy_id"],
                        "fold_id": fold["fold_id"],
                        "split_role": split_role,
                        "visibility_status": "FULL",
                    },
                    evaluation_eligible_record_ids=set(
                        admissible["record_id"].astype("string").tolist()
                    ),
                )
            )
    fold_inventory = (
        pd.concat(projection_rows, ignore_index=True).convert_dtypes()
        if projection_rows
        else pd.DataFrame(columns=unique_inventory.columns).convert_dtypes()
    )
    dependency_registry = pd.DataFrame(
        [
            {
                "evidence_flag": "low_flag",
                "source_fields": "npk.soil_moisture_pct",
                "threshold_id": "LOW_MOISTURE_Q10_E1_DISCOVERY_CANDIDATE",
                "known_dependencies": "shares soil-sensor validity with rise_flag and ec_shift_flag",
                "independent_vote": False,
            },
            {
                "evidence_flag": "thermal_flag",
                "source_fields": "sht.temp_c|sht.humidity_pct",
                "threshold_id": "THERMAL_VPD_FIXED_2_5_REFERENCE",
                "known_dependencies": "temperature and humidity jointly define VPD",
                "independent_vote": False,
            },
            {
                "evidence_flag": "moisture_rise_flag",
                "source_fields": "npk.soil_moisture_pct|strict_previous_observation",
                "threshold_id": "MOISTURE_RISE_FIXED_5PP_REFERENCE",
                "known_dependencies": "shares moisture source and strict continuity with low_flag",
                "independent_vote": False,
            },
            {
                "evidence_flag": "ec_shift_flag",
                "source_fields": "npk.ec|strict_previous_observation",
                "threshold_id": "EC_SHIFT_Q95_E1_DISCOVERY_CANDIDATE",
                "known_dependencies": "shares soil-sensor validity and strict continuity",
                "independent_vote": False,
            },
        ]
    ).convert_dtypes()
    return unique_inventory, fold_inventory, dependency_registry


def build_candidate_resolution_report(evidence_df: pd.DataFrame) -> pd.DataFrame:
    eligible = evidence_df.loc[evidence_df["low_target_eligibility"].fillna(False).astype(bool)].copy()
    flag_columns = ["low_flag", "thermal_flag", "moisture_rise_flag", "ec_shift_flag"]
    rows: list[dict[str, object]] = []
    for key, group in eligible.groupby(flag_columns, dropna=False, sort=False):
        values = key if isinstance(key, tuple) else (key,)
        resolution_counts = group["candidate_resolution"].astype("string").value_counts()
        rows.append(
            {
                **{column: value for column, value in zip(flag_columns, values)},
                "candidate_resolution": resolution_counts.index[0],
                "support_count": len(group),
                "day_count": group["sample_time"].dt.date.nunique(),
                "observed_cluster_count": group["observed_low_run_id"].dropna().astype("string").nunique(),
                "missing_evidence_pattern": "|".join(
                    column for column, value in zip(flag_columns, values) if pd.isna(value)
                )
                or "NONE",
                "counterexample_count": int((group["full_point_ontology_eligibility"].fillna(False) == False).sum()),
                "open_question": "PHASE_B_MUST_LOCK_REQUIRED_CONTEXT_AND_RESOLVER",
                "candidate_only": True,
            }
        )
    return pd.DataFrame(rows).convert_dtypes()


def _aggregate_inventory(
    dataframe: pd.DataFrame,
    *,
    inventory_scope: str,
    grouping_prefix: dict[str, object],
    evaluation_eligible_record_ids: set[str] | None,
) -> pd.DataFrame:
    flag_columns = ["low_flag", "thermal_flag", "moisture_rise_flag", "ec_shift_flag"]
    rows: list[dict[str, object]] = []
    for key, group in dataframe.groupby(flag_columns, dropna=False, sort=False):
        values = key if isinstance(key, tuple) else (key,)
        rows.append(
            {
                "inventory_scope": inventory_scope,
                **grouping_prefix,
                "evidence_contract_id": "E1_DISCOVERY_Q10_FULL_CONTEXT_V1",
                "low_threshold_candidate_id": "LOW_MOISTURE_Q10_E1_DISCOVERY_CANDIDATE",
                "ec_shift_threshold_candidate_id": "EC_SHIFT_Q95_E1_DISCOVERY_CANDIDATE",
                "thermal_threshold_id": "THERMAL_VPD_FIXED_2_5_REFERENCE",
                "rise_threshold_id": "MOISTURE_RISE_FIXED_5PP_REFERENCE",
                "strict_policy_candidate_id": STRICT_POLICY_ID,
                **{column: value for column, value in zip(flag_columns, values)},
                "row_count": len(group),
                "day_count": group["sample_time"].dt.date.nunique(),
                "observed_cluster_count": group["observed_low_run_id"].dropna().astype("string").nunique(),
                "evaluation_cluster_count": (
                    group.loc[
                        group["record.id"].astype("string").isin(
                            evaluation_eligible_record_ids
                        ),
                        "strict_continuity_id",
                    ]
                    .astype("string")
                    .nunique()
                    if evaluation_eligible_record_ids is not None
                    else pd.NA
                ),
            }
        )
    return pd.DataFrame(rows).convert_dtypes()


def _candidate_resolution(row: pd.Series) -> str:
    if not bool(row.get("low_target_eligibility", False)):
        return "POINT_NOT_EVALUABLE"
    if row.get("low_flag") is True or str(row.get("low_flag")).lower() == "true":
        return "LOW"
    auxiliary = [row.get("thermal_flag"), row.get("moisture_rise_flag"), row.get("ec_shift_flag")]
    if any(value is True or str(value).lower() == "true" for value in auxiliary):
        return "UNRESOLVED"
    if any(pd.isna(value) for value in auxiliary):
        return "UNRESOLVED"
    return "REFERENCE"


def _nullable_flag(applicable: pd.Series, condition: pd.Series) -> pd.Series:
    result = pd.Series([pd.NA] * len(applicable), index=applicable.index, dtype="boolean")
    mask = applicable.fillna(False).astype(bool)
    result.loc[mask] = condition.loc[mask].fillna(False).astype(bool)
    return result


def _compute_vpd(temp_c: pd.Series, humidity_pct: pd.Series) -> pd.Series:
    saturation = 0.6108 * (17.27 * temp_c / (temp_c + 237.3)).map(math.exp)
    return saturation * (1 - humidity_pct / 100.0)


def _bool_series(series: pd.Series) -> pd.Series:
    if str(series.dtype) in {"bool", "boolean"}:
        return series.fillna(False).astype(bool)
    return series.astype("string").str.strip().str.lower().isin({"true", "1", "yes"})
