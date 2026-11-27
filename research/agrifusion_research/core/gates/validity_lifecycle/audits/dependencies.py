from __future__ import annotations

import math

import numpy as np
import pandas as pd


def classify_dependency_relationship(
    *,
    row_count: int,
    unique_ec_count: int,
    conflicting_mapping_count: int,
    pearson_r: float | None,
    spearman_r: float | None,
    r2_linear: float | None,
    max_abs_residual: float | None,
    median_abs_residual: float | None,
) -> str:
    if row_count <= 1 or unique_ec_count <= 1:
        return "INSUFFICIENT_VARIATION"
    if conflicting_mapping_count == 0 and (max_abs_residual is not None and max_abs_residual <= 1e-9):
        return "DETERMINISTIC_EC_DERIVED_PROXY"
    if (
        r2_linear is not None
        and r2_linear >= 0.999
        and median_abs_residual is not None
        and median_abs_residual <= 1.0
    ):
        return "NEAR_DETERMINISTIC_PROXY"
    if max(abs(value) for value in (pearson_r or 0.0, spearman_r or 0.0)) >= 0.8:
        return "CORRELATED_SENSOR_OUTPUT"
    return "INCONCLUSIVE"


def build_ec_npk_dependency_audit(observation_registry: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    environments = ["ALL", *sorted(env for env in observation_registry["environment_id"].astype("string").dropna().unique() if env != "OUT_OF_SCOPE")]
    for environment_id in environments:
        env_frame = observation_registry if environment_id == "ALL" else observation_registry.loc[
            observation_registry["environment_id"].astype("string") == environment_id
        ].copy()
        for nutrient_column in ("npk.n_proxy", "npk.p_proxy", "npk.k_proxy"):
            rows.append(_summarize_ec_proxy_relationship(env_frame, environment_id=environment_id, nutrient_column=nutrient_column))
    audit_df = pd.DataFrame(rows).convert_dtypes()
    overall_rows = audit_df.loc[audit_df["environment_id"].astype("string") == "ALL"].set_index("nutrient_column")
    if not overall_rows.empty:
        audit_df["slope_delta_vs_all"] = audit_df.apply(
            lambda row: _safe_delta(row.get("slope"), overall_rows.loc[row["nutrient_column"], "slope"])
            if row["environment_id"] != "ALL" and row["nutrient_column"] in overall_rows.index
            else pd.NA,
            axis=1,
        )
        audit_df["intercept_delta_vs_all"] = audit_df.apply(
            lambda row: _safe_delta(row.get("intercept"), overall_rows.loc[row["nutrient_column"], "intercept"])
            if row["environment_id"] != "ALL" and row["nutrient_column"] in overall_rows.index
            else pd.NA,
            axis=1,
        )
    return audit_df.convert_dtypes()


def build_ph_measurement_stability_audit(observation_registry: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    ordered_environments = ["ALL", *sorted(env for env in observation_registry["environment_id"].astype("string").dropna().unique() if env != "OUT_OF_SCOPE")]
    previous_median: float | None = None
    for environment_id in ordered_environments:
        env_frame = observation_registry if environment_id == "ALL" else observation_registry.loc[
            observation_registry["environment_id"].astype("string") == environment_id
        ].copy()
        summary = _summarize_ph_stability(env_frame, environment_id=environment_id)
        if previous_median is not None and summary["ph_median"] is not pd.NA and pd.notna(summary["ph_median"]):
            summary["median_shift_vs_previous_environment"] = float(summary["ph_median"] - previous_median)
        else:
            summary["median_shift_vs_previous_environment"] = pd.NA
        if summary["ph_median"] is not pd.NA and pd.notna(summary["ph_median"]):
            previous_median = float(summary["ph_median"])
        rows.append(summary)
    return pd.DataFrame(rows).convert_dtypes()


def _summarize_ec_proxy_relationship(
    frame: pd.DataFrame,
    *,
    environment_id: str,
    nutrient_column: str,
) -> dict[str, object]:
    numeric = frame.loc[:, ["npk.ec", nutrient_column]].apply(pd.to_numeric, errors="coerce").dropna()
    row_count = int(len(numeric))
    unique_ec_count = int(numeric["npk.ec"].nunique()) if not numeric.empty else 0
    unique_pair_count = int(numeric.drop_duplicates().shape[0]) if not numeric.empty else 0
    conflicting_mapping_count = (
        int(numeric.groupby("npk.ec", dropna=False)[nutrient_column].nunique().gt(1).sum())
        if not numeric.empty
        else 0
    )
    slope = intercept = pearson_r = spearman_r = r2_linear = max_abs_residual = median_abs_residual = pd.NA
    if row_count >= 2 and unique_ec_count >= 2:
        x = numeric["npk.ec"].to_numpy(dtype=float)
        y = numeric[nutrient_column].to_numpy(dtype=float)
        slope_value, intercept_value = np.polyfit(x, y, 1)
        predicted = slope_value * x + intercept_value
        residuals = y - predicted
        pearson_value = float(pd.Series(x).corr(pd.Series(y), method="pearson"))
        spearman_value = float(pd.Series(x).corr(pd.Series(y), method="spearman"))
        sst = float(np.sum((y - y.mean()) ** 2))
        sse = float(np.sum(residuals ** 2))
        r2_value = 1.0 if math.isclose(sst, 0.0) and math.isclose(sse, 0.0) else (1.0 - sse / sst if sst > 0 else 0.0)
        slope = float(slope_value)
        intercept = float(intercept_value)
        pearson_r = pearson_value
        spearman_r = spearman_value
        r2_linear = float(r2_value)
        max_abs_residual = float(np.max(np.abs(residuals)))
        median_abs_residual = float(np.median(np.abs(residuals)))
    relationship_class = classify_dependency_relationship(
        row_count=row_count,
        unique_ec_count=unique_ec_count,
        conflicting_mapping_count=conflicting_mapping_count,
        pearson_r=None if pd.isna(pearson_r) else float(pearson_r),
        spearman_r=None if pd.isna(spearman_r) else float(spearman_r),
        r2_linear=None if pd.isna(r2_linear) else float(r2_linear),
        max_abs_residual=None if pd.isna(max_abs_residual) else float(max_abs_residual),
        median_abs_residual=None if pd.isna(median_abs_residual) else float(median_abs_residual),
    )
    return {
        "environment_id": environment_id,
        "nutrient_column": nutrient_column,
        "row_count": row_count,
        "unique_ec_count": unique_ec_count,
        "unique_pair_count": unique_pair_count,
        "conflicting_mapping_count": conflicting_mapping_count,
        "pearson_r": pearson_r,
        "spearman_r": spearman_r,
        "r2_linear": r2_linear,
        "slope": slope,
        "intercept": intercept,
        "max_abs_residual": max_abs_residual,
        "median_abs_residual": median_abs_residual,
        "relationship_class": relationship_class,
    }


def _summarize_ph_stability(frame: pd.DataFrame, *, environment_id: str) -> dict[str, object]:
    ph = pd.to_numeric(frame["npk.ph"], errors="coerce")
    ec = pd.to_numeric(frame["npk.ec"], errors="coerce")
    moisture = pd.to_numeric(frame["npk.soil_moisture_pct"], errors="coerce")
    technical_valid = frame["technical_valid"].fillna(False).astype(bool)
    valid_mask = ph.notna() & technical_valid
    valid_ph = ph.loc[valid_mask]
    missing_count = int(ph.isna().sum())
    invalid_count = int((~technical_valid & ph.notna()).sum())
    dominant_ratio = pd.NA
    max_day_median_jump = median_day_median_jump = pd.NA
    ph_median = pd.NA
    ph_q05 = ph_q95 = pd.NA
    ec_corr = moisture_corr = pd.NA
    unique_value_count = int(valid_ph.nunique()) if not valid_ph.empty else 0
    if not valid_ph.empty:
        ph_median = float(valid_ph.median())
        ph_q05 = float(valid_ph.quantile(0.05))
        ph_q95 = float(valid_ph.quantile(0.95))
        dominant_ratio = float(valid_ph.value_counts(normalize=True, dropna=False).iloc[0])
        valid_frame = frame.loc[valid_mask, ["day_id"]].copy()
        valid_frame["npk.ph"] = valid_ph.to_numpy()
        daily = valid_frame.groupby("day_id", dropna=False, sort=True)["npk.ph"].median()
        if len(daily) >= 2:
            jumps = daily.diff().abs().dropna()
            if not jumps.empty:
                max_day_median_jump = float(jumps.max())
                median_day_median_jump = float(jumps.median())
        if valid_ph.shape[0] >= 2:
            ec_corr = float(valid_ph.corr(ec.loc[valid_mask], method="pearson"))
            moisture_corr = float(valid_ph.corr(moisture.loc[valid_mask], method="pearson"))
    stability_class = _classify_ph_stability(
        valid_count=int(valid_ph.shape[0]),
        unique_value_count=unique_value_count,
        dominant_ratio=None if pd.isna(dominant_ratio) else float(dominant_ratio),
        max_day_median_jump=None if pd.isna(max_day_median_jump) else float(max_day_median_jump),
    )
    return {
        "environment_id": environment_id,
        "row_count": int(len(frame)),
        "valid_count": int(valid_ph.shape[0]),
        "missing_count": missing_count,
        "invalid_count": invalid_count,
        "valid_rate": float(valid_ph.shape[0] / len(frame)) if len(frame) > 0 else pd.NA,
        "ph_min": float(valid_ph.min()) if not valid_ph.empty else pd.NA,
        "ph_max": float(valid_ph.max()) if not valid_ph.empty else pd.NA,
        "ph_median": ph_median,
        "ph_q05": ph_q05,
        "ph_q95": ph_q95,
        "unique_value_count": unique_value_count,
        "dominant_value_ratio": dominant_ratio,
        "max_day_median_jump": max_day_median_jump,
        "median_day_median_jump": median_day_median_jump,
        "ec_corr": ec_corr,
        "moisture_corr": moisture_corr,
        "stability_class": stability_class,
    }


def _classify_ph_stability(
    *,
    valid_count: int,
    unique_value_count: int,
    dominant_ratio: float | None,
    max_day_median_jump: float | None,
) -> str:
    if valid_count < 5:
        return "SPARSE"
    if max_day_median_jump is not None and max_day_median_jump >= 1.0:
        return "STEP_CHANGE"
    if dominant_ratio is not None and dominant_ratio >= 0.95 and unique_value_count <= 2:
        return "HIGH_PERSISTENCE"
    return "STABLE_RANGE"


def _safe_delta(value: object, reference: object) -> float | pd._libs.missing.NAType:
    if pd.isna(value) or pd.isna(reference):
        return pd.NA
    return float(value) - float(reference)
