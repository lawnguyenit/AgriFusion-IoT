from __future__ import annotations

import json

import pandas as pd

from Backend.Benchmark.weak_labels.native_engine.contracts import NativeContract, deterministic_id


RULES = (
    ("LOW_RELATIVE_MOISTURE", "low_moisture_applicability", "npk.soil_moisture_pct", "LOW_MOISTURE_Q10"),
    ("THERMAL_CONTEXT", "thermal_applicability", "derived.vpd_kpa", "THERMAL_VPD_2_5_LEGACY_CONTEXT"),
    ("MOISTURE_RISE", "rise_applicability", "moisture_rise_delta", "MOISTURE_RISE_5PP_LEGACY_CONTEXT"),
    ("EC_SHIFT", "ec_shift_applicability", "ec_shift_delta_abs", "EC_SHIFT_Q95_6_DISCOVERY"),
)


def evaluate_point_rules(frame: pd.DataFrame, contract: NativeContract, operationalization: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    q_contract = str(operationalization["q_contract_id"])
    q_threshold = _resolve_q_threshold(contract, q_contract)
    vpd_threshold = _resolve_threshold(contract, "THERMAL_VPD_2_5_LEGACY_CONTEXT", fallback=2.5)
    rise_threshold = _resolve_threshold(contract, "MOISTURE_RISE_5PP_LEGACY_CONTEXT", fallback=5.0)
    ec_threshold = _resolve_threshold(contract, "EC_SHIFT_Q95_6_DISCOVERY", fallback=6.0)
    rows: list[dict[str, object]] = []
    evidence_rows: list[dict[str, object]] = []
    for row in frame.to_dict(orient="records"):
        sample_id = str(row["record.id"])
        values = {
            "LOW_RELATIVE_MOISTURE": (row.get("npk.soil_moisture_pct"), q_threshold, "<=", "LOW_MOISTURE_Q10"),
            "THERMAL_CONTEXT": (row.get("derived.vpd_kpa"), vpd_threshold, ">=", "THERMAL_VPD_2_5_LEGACY_CONTEXT"),
            "MOISTURE_RISE": (row.get("moisture_rise_delta"), rise_threshold, ">=", "MOISTURE_RISE_5PP_LEGACY_CONTEXT"),
            "EC_SHIFT": (row.get("ec_shift_delta_abs"), ec_threshold, ">=", "EC_SHIFT_Q95_6_DISCOVERY"),
        }
        for rule_id, applicability_column, evidence_field, threshold_id in RULES:
            value, threshold, operator, _ = values[rule_id]
            applicable = _rule_applicable(row, rule_id)
            state = "NOT_EVALUABLE" if applicable and pd.isna(value) else "NOT_APPLICABLE" if not applicable else "NEGATIVE"
            result = False
            if state != "NOT_EVALUABLE" and state != "NOT_APPLICABLE":
                result = float(value) <= threshold if operator == "<=" else float(value) >= threshold
                state = "POSITIVE" if result else "NEGATIVE"
            firing_id = deterministic_id(
                {
                    "object_type": "RULE_FIRING",
                    "schema_version": "native.rule-firing.v1",
                    "semantic_contract_hash": contract.semantic_contract_hash,
                    "operationalization_id": str(operationalization["operationalization_id"]),
                    "task_id": "POINT",
                    "horizon_id": "NONE",
                    "sample_id": sample_id,
                    "rule_id": rule_id,
                    "evaluation_instance_key": "POINT",
                }
            )
            evidence_rows.append(
                {
                    "rule_firing_id": firing_id,
                    "sample_id": sample_id,
                    "task_id": "POINT",
                    "operationalization_id": str(operationalization["operationalization_id"]),
                    "rule_id": rule_id,
                    "applicability_status": "APPLICABLE" if applicable else "NOT_APPLICABLE",
                    "applicability_reason": str(applicability_column),
                    "evidence_state": state if applicable else pd.NA,
                    "not_evaluable_reason": "MISSING_INPUT" if state == "NOT_EVALUABLE" else pd.NA,
                    "evidence_field": evidence_field,
                    "evidence_value": value,
                    "comparison_operator": operator,
                    "threshold_id": threshold_id,
                    "threshold_value": threshold,
                    "dependency_interval_start": row.get("derived_dependency_interval_start", row.get("sample_time_utc")),
                    "dependency_interval_end": row.get("derived_dependency_interval_end", row.get("sample_time_utc")),
                }
            )
        rows.append({"sample_id": sample_id, "low_state": _state(evidence_rows, sample_id, "LOW_RELATIVE_MOISTURE"), "thermal_state": _state(evidence_rows, sample_id, "THERMAL_CONTEXT"), "rise_state": _state(evidence_rows, sample_id, "MOISTURE_RISE"), "ec_state": _state(evidence_rows, sample_id, "EC_SHIFT")})
    return pd.DataFrame(rows).convert_dtypes(), pd.DataFrame(evidence_rows).convert_dtypes()


def _rule_applicable(row: dict[str, object], rule_id: str) -> bool:
    if not bool(row.get("time_integrity_ok", False)):
        return False
    if rule_id == "LOW_RELATIVE_MOISTURE":
        return pd.notna(row.get("npk.soil_moisture_pct"))
    if rule_id == "THERMAL_CONTEXT":
        return pd.notna(row.get("derived.vpd_kpa"))
    if rule_id == "MOISTURE_RISE":
        return bool(row.get("strictly_consecutive_from_previous", False))
    if rule_id == "EC_SHIFT":
        return bool(row.get("strictly_consecutive_from_previous", False))
    return False


def _state(rows: list[dict[str, object]], sample_id: str, rule_id: str) -> str:
    for row in reversed(rows):
        if row["sample_id"] == sample_id and row["rule_id"] == rule_id:
            return str(row["evidence_state"]) if pd.notna(row["evidence_state"]) else "NOT_EVALUABLE"
    return "NOT_EVALUABLE"


def _resolve_q_threshold(contract: NativeContract, q_contract: str) -> float:
    candidates = [f"{q_contract}_DISCOVERY", q_contract, "LOW_MOISTURE_Q10"]
    for candidate in candidates:
        rows = contract.q_registry.loc[contract.q_registry["threshold_id"].astype("string") == candidate]
        if len(rows) == 1:
            return float(rows.iloc[0]["threshold_value"])
    q_rows = contract.q_registry.loc[contract.q_registry["threshold_id"].astype("string").str.contains(q_contract, na=False)]
    if len(q_rows) == 1:
        return float(q_rows.iloc[0]["threshold_value"])
    raise ValueError(f"No unique frozen threshold found for {q_contract}.")


def _resolve_threshold(contract: NativeContract, threshold_id: str, *, fallback: float) -> float:
    rows = contract.q_registry.loc[contract.q_registry["threshold_id"].astype("string") == threshold_id]
    return fallback if len(rows) == 0 else float(rows.iloc[0]["threshold_value"])

