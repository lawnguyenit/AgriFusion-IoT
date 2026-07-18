from __future__ import annotations

import pandas as pd

from Backend.Benchmark.weak_labels.shared.configs import DEFAULT_POINT_REQUIRED_EVIDENCE_COLUMNS
from Backend.Benchmark.weak_labels.shared.helpers import compute_vpd_kpa, coerce_boolean_series, resolve_local_timestamp_series


def build_applicability_frame(canonical_df: pd.DataFrame) -> pd.DataFrame:
    applicability = canonical_df.loc[:, ["record.id", "record.ts_sample", "record.segment_id", "record.node_id"]].copy()
    applicability["timestamp_local"] = resolve_local_timestamp_series(canonical_df)

    npk_valid = _resolve_validity(canonical_df, "npk.valid")
    sht_valid = _resolve_validity(canonical_df, "sht.valid")
    applicability["npk.valid"] = npk_valid.astype("boolean")
    applicability["sht.valid"] = sht_valid.astype("boolean")

    applicability["derived.vpd_kpa"] = compute_vpd_kpa(canonical_df["sht.temp_c"], canonical_df["sht.humidity_pct"])
    applicability["low_moisture_applicable"] = (
        npk_valid
        & pd.to_numeric(canonical_df["npk.soil_moisture_pct"], errors="coerce").notna()
    ).astype("boolean")
    applicability["thermal_applicable"] = (
        sht_valid
        & pd.to_numeric(canonical_df["sht.temp_c"], errors="coerce").notna()
        & pd.to_numeric(canonical_df["sht.humidity_pct"], errors="coerce").notna()
    ).astype("boolean")
    applicability["ec_shift_applicable"] = (
        npk_valid
        & pd.to_numeric(canonical_df["npk.ec"], errors="coerce").notna()
    ).astype("boolean")
    applicability["moisture_rise_applicable"] = applicability["low_moisture_applicable"].astype("boolean")

    applicability["time_integrity_ok"] = (
        pd.to_numeric(canonical_df["record.ts_sample"], errors="coerce").notna()
        & canonical_df["record.segment_id"].notna()
    ).astype("boolean")
    applicability["core_environment_fully_evaluable"] = (
        applicability.loc[:, list(DEFAULT_POINT_REQUIRED_EVIDENCE_COLUMNS)]
        .apply(coerce_boolean_series)
        .all(axis=1)
    ).astype("boolean")
    applicability["technical_invalid_reason"] = applicability.apply(_resolve_technical_invalid_reason, axis=1).astype("string")
    return applicability.convert_dtypes()


def _resolve_validity(canonical_df: pd.DataFrame, column: str) -> pd.Series:
    if column not in canonical_df.columns:
        return pd.Series([False] * len(canonical_df), index=canonical_df.index, dtype="boolean")
    return coerce_boolean_series(canonical_df[column]).astype("boolean")


def _resolve_technical_invalid_reason(row: pd.Series) -> str:
    reasons: list[str] = []
    if not bool(row.get("time_integrity_ok", False)):
        reasons.append("time_integrity")
    if not bool(row.get("low_moisture_applicable", False)):
        reasons.append("low_moisture_missing")
    if not bool(row.get("thermal_applicable", False)):
        reasons.append("thermal_missing")
    if not bool(row.get("ec_shift_applicable", False)):
        reasons.append("ec_missing")
    if not bool(row.get("moisture_rise_applicable", False)):
        reasons.append("rise_missing")
    return "|".join(reasons) if reasons else "fully_evaluable"
