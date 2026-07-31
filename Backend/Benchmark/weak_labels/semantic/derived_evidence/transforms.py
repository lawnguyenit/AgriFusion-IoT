from __future__ import annotations

import math

import numpy as np
import pandas as pd

from Backend.Benchmark.weak_labels.contracts.native import NativeContract, NativeContractError


def build_derived_evidence(frame: pd.DataFrame, contract: NativeContract) -> pd.DataFrame:
    working = frame.copy()
    specs = {str(row["derived_evidence_id"]): row for row in contract.derived_evidence_registry.to_dict(orient="records")}
    _require_spec(specs, "VPD_MAGNUS_V1")
    _require_spec(specs, "MOISTURE_RISE_V1")
    _require_spec(specs, "EC_SHIFT_ABS_V1")
    _assert_formula(specs["VPD_MAGNUS_V1"], "VPD_MAGNUS")
    _assert_formula(specs["MOISTURE_RISE_V1"], "CURRENT_MINUS_STRICT_PREVIOUS")
    _assert_formula(specs["EC_SHIFT_ABS_V1"], "ABS_CURRENT_MINUS_STRICT_PREVIOUS")

    temperature = pd.to_numeric(working.get("sht.temp_c"), errors="coerce")
    humidity = pd.to_numeric(working.get("sht.humidity_pct"), errors="coerce")
    humidity_policy = _required_policy(specs["VPD_MAGNUS_V1"], "clipping_policy")
    if humidity_policy == "CLIP_0_100":
        humidity_for_formula = humidity.clip(lower=0, upper=100)
    else:
        humidity_for_formula = humidity.where(humidity.between(0, 100))
    saturation = 0.6108 * np.exp((17.27 * temperature) / (temperature + 237.3))
    working["derived.vpd_kpa"] = saturation * (1.0 - humidity_for_formula / 100.0)
    working.loc[temperature.isna() | humidity_for_formula.isna(), "derived.vpd_kpa"] = np.nan
    previous_moisture = pd.to_numeric(working["npk.soil_moisture_pct"], errors="coerce").groupby(working["deployment_segment_id"], dropna=False).shift(1)
    previous_ec = pd.to_numeric(working["npk.ec"], errors="coerce").groupby(working["deployment_segment_id"], dropna=False).shift(1)
    strict = working["strictly_consecutive_from_previous"].fillna(False).astype(bool)
    moisture = pd.to_numeric(working["npk.soil_moisture_pct"], errors="coerce")
    ec = pd.to_numeric(working["npk.ec"], errors="coerce")
    working["moisture_rise_delta"] = (moisture - previous_moisture).where(strict)
    working["ec_shift_delta_abs"] = (ec - previous_ec).abs().where(strict)
    working.loc[~strict, ["moisture_rise_delta", "ec_shift_delta_abs"]] = np.nan
    working["vpd_evaluable"] = working["derived.vpd_kpa"].notna().astype("boolean")
    working["moisture_delta_evaluable"] = working["moisture_rise_delta"].notna().astype("boolean")
    working["ec_delta_evaluable"] = working["ec_shift_delta_abs"].notna().astype("boolean")
    dependency_start = working["previous_sample_time_utc"].where(strict, working["sample_time_utc"])
    working["derived_dependency_interval_start"] = dependency_start
    working["derived_dependency_interval_end"] = working["sample_time_utc"]
    return working.convert_dtypes()


def _require_spec(specs: dict[str, dict[str, object]], evidence_id: str) -> None:
    if evidence_id not in specs:
        raise NativeContractError(f"Derived-evidence contract is missing {evidence_id}.")
    row = specs[evidence_id]
    if not str(row.get("formula_expression_or_formula_id", "")).strip():
        raise NativeContractError(f"Derived-evidence contract has no formula for {evidence_id}.")


def _assert_formula(row: dict[str, object], expected_token: str) -> None:
    formula = str(row.get("formula_expression_or_formula_id", ""))
    transform = str(row.get("transform_id", ""))
    if expected_token not in formula and expected_token not in transform:
        raise NativeContractError(
            f"Derived-evidence contract formula {formula!r}/{transform!r} is not implemented by the native engine."
        )
    if not str(row.get("source_units", "")).strip() or not str(row.get("output_unit", "")).strip():
        raise NativeContractError("Derived-evidence contract must declare source and output units.")


def _required_policy(row: dict[str, object], key: str) -> str:
    value = row.get(key)
    if value is None or not str(value).strip():
        raise NativeContractError(f"Derived-evidence contract must declare {key}.")
    return str(value)
