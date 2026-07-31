from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from Backend.Benchmark.common.digests import dataframe_digest, file_sha256, stable_digest
from Backend.Benchmark.protocol_registry.contracts import ProtocolRegistry


def build_threshold_diagnostics(
    e1_df: pd.DataFrame,
    registry: ProtocolRegistry,
    *,
    baseline_run_dir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, float]]:
    cohort = registry.threshold_fit_cohort_manifest.loc[
        registry.threshold_fit_cohort_manifest["threshold_fit_cohort_id"].astype("string")
        == "E1_DISCOVERY_TRAIN_V1"
    ].iloc[0]
    start = pd.Timestamp(cohort["start_time"])
    end = pd.Timestamp(cohort["end_time"])
    moisture = pd.to_numeric(e1_df["npk.soil_moisture_pct"], errors="coerce")
    npk_valid = _bool_series(e1_df["npk.valid"])
    cohort_mask = e1_df["sample_time"].ge(start) & e1_df["sample_time"].lt(end) & npk_valid & moisture.notna()
    cohort_records = e1_df.loc[cohort_mask, ["record.id", "sample_time"]].copy()
    cohort_records["npk.soil_moisture_pct"] = moisture.loc[cohort_mask].astype(float)
    cohort_records = cohort_records.rename(columns={"record.id": "record_id"}).sort_values("record_id", kind="stable")
    cohort_hash = dataframe_digest(
        cohort_records,
        columns=["record_id", "sample_time", "npk.soil_moisture_pct"],
        sort_columns=["record_id"],
    )
    values = cohort_records["npk.soil_moisture_pct"]
    if values.empty:
        raise ValueError("E1 discovery cohort contains no valid moisture values.")
    quantiles = {f"q{int(q * 100):02d}": float(values.quantile(q, interpolation="linear")) for q in (0.05, 0.10, 0.15, 0.20)}

    ec_values = pd.to_numeric(e1_df.loc[cohort_mask, "ec_delta_abs_strict"], errors="coerce").dropna()
    ec_q95 = float(ec_values.quantile(0.95, interpolation="linear")) if not ec_values.empty else float("nan")
    ec_zero_fraction = float(ec_values.eq(0).mean()) if not ec_values.empty else float("nan")
    legacy = _load_legacy_reference(baseline_run_dir)
    candidate_code_hash = file_sha256(Path(__file__))

    threshold_registry = pd.DataFrame(
        [
            {
                "threshold_id": "LOW_MOISTURE_Q10_E1_DISCOVERY_CANDIDATE",
                "threshold_role": "PHASE_A_CANDIDATE",
                "threshold_value": quantiles["q10"],
                "fit_environment_id": "E1",
                "fit_protocol_role": "SOURCE_DISCOVERY",
                "fit_cohort_id": "E1_DISCOVERY_TRAIN_V1",
                "apply_environment_ids": "E1|E2|E3_TARGET_PREEXPOSED|E4_FUTURE_TARGET",
                "contract_freeze_id": pd.NA,
                "contract_hash": pd.NA,
                "frozen_from_run_id": pd.NA,
                "quantile_method": "PANDAS_LINEAR",
                "fit_record_count": len(cohort_records),
                "fit_record_hash": cohort_hash,
                "code_hash": candidate_code_hash,
            },
            {
                "threshold_id": "LEGACY_REFERENCE_Q10_60_3",
                "threshold_role": "LEGACY_REFERENCE_ONLY",
                "threshold_value": legacy["threshold_value"],
                "fit_environment_id": "MIXED_LEGACY_CHRONOLOGICAL_PREFIX",
                "fit_protocol_role": "PRE_PROTOCOL_REGISTRY",
                "fit_cohort_id": "LEGACY_WEAK_LABEL_70PCT_TRAIN",
                "apply_environment_ids": "LEGACY_ALL",
                "contract_freeze_id": pd.NA,
                "contract_hash": pd.NA,
                "frozen_from_run_id": legacy["reference_run_id"],
                "quantile_method": "PANDAS_LINEAR",
                "fit_record_count": legacy["fit_record_count"],
                "fit_record_hash": legacy["fit_record_hash"],
                "code_hash": legacy["code_hash"],
            },
            {
                "threshold_id": "EC_SHIFT_Q95_E1_DISCOVERY_CANDIDATE",
                "threshold_role": "PHASE_A_CANDIDATE",
                "threshold_value": ec_q95,
                "fit_environment_id": "E1",
                "fit_protocol_role": "SOURCE_DISCOVERY",
                "fit_cohort_id": "E1_DISCOVERY_TRAIN_V1",
                "apply_environment_ids": "E1|E2|E3_TARGET_PREEXPOSED|E4_FUTURE_TARGET",
                "contract_freeze_id": pd.NA,
                "contract_hash": pd.NA,
                "frozen_from_run_id": pd.NA,
                "quantile_method": "PANDAS_LINEAR",
                "fit_record_count": len(ec_values),
                "fit_record_hash": dataframe_digest(
                    e1_df.loc[cohort_mask & e1_df["ec_delta_abs_strict"].notna(), ["record.id", "ec_delta_abs_strict"]]
                    .rename(columns={"record.id": "record_id"}),
                    columns=["record_id", "ec_delta_abs_strict"],
                    sort_columns=["record_id"],
                )
                if not ec_values.empty
                else "EMPTY",
                "code_hash": candidate_code_hash,
            },
        ]
    ).convert_dtypes()
    sensitivity = pd.DataFrame(
        [
            {
                "threshold_family": "LOW_MOISTURE",
                "fit_cohort_id": "E1_DISCOVERY_TRAIN_V1",
                "fit_record_count": len(values),
                **quantiles,
                "legacy_reference_q10": legacy["threshold_value"],
                "q10_delta_from_legacy": quantiles["q10"] - float(legacy["threshold_value"]),
                "comparison_status": "EXPECTED_COHORT_DIFFERENCE"
                if quantiles["q10"] != float(legacy["threshold_value"])
                else "EXACT_MATCH",
            },
            {
                "threshold_family": "EC_SHIFT_ABS_DELTA",
                "fit_cohort_id": "E1_DISCOVERY_TRAIN_V1",
                "fit_record_count": len(ec_values),
                "q05": float(ec_values.quantile(0.05)) if not ec_values.empty else pd.NA,
                "q10": float(ec_values.quantile(0.10)) if not ec_values.empty else pd.NA,
                "q15": float(ec_values.quantile(0.15)) if not ec_values.empty else pd.NA,
                "q20": float(ec_values.quantile(0.20)) if not ec_values.empty else pd.NA,
                "legacy_reference_q10": pd.NA,
                "q10_delta_from_legacy": pd.NA,
                "comparison_status": "DEGENERATE_ZERO_MASS_REPORTED"
                if pd.notna(ec_zero_fraction) and ec_zero_fraction >= 0.5
                else "MEASURED",
            },
        ]
    ).convert_dtypes()
    provenance = {
        **legacy,
        "reference_fit_cohort_id": "LEGACY_WEAK_LABEL_70PCT_TRAIN",
        "reference_quantile_method": "PANDAS_LINEAR",
        "reference_config_hash": legacy["config_hash"],
        "candidate_fit_cohort_id": "E1_DISCOVERY_TRAIN_V1",
        "candidate_fit_record_hash": cohort_hash,
        "candidate_fit_record_count": len(cohort_records),
        "candidate_quantiles": quantiles,
        "ec_shift_q95_candidate": ec_q95,
        "ec_shift_zero_fraction": ec_zero_fraction,
        "threshold_behavior_modified": False,
    }
    return threshold_registry, sensitivity, cohort_records.convert_dtypes(), provenance


def _load_legacy_reference(baseline_run_dir: Path) -> dict[str, object]:
    baseline_run_dir = baseline_run_dir.resolve()
    threshold_registry = pd.read_csv(baseline_run_dir / "audit" / "threshold_registry.csv")
    row = threshold_registry.loc[
        threshold_registry["threshold_id"].astype("string") == "low_relative_moisture_q10_global"
    ].iloc[0]
    run_manifest = json.loads((baseline_run_dir / "run_metadata" / "run_manifest.json").read_text(encoding="utf-8"))
    return {
        "reference_run_id": baseline_run_dir.name,
        "threshold_value": float(row["threshold_value"]),
        "fit_record_count": int(row["fit_record_count"]),
        "fit_record_hash": str(row["fit_record_hash"]),
        "code_hash": str(row["code_hash"]),
        "config_hash": stable_digest(run_manifest.get("config", {})),
    }


def _bool_series(series: pd.Series) -> pd.Series:
    if str(series.dtype) in {"bool", "boolean"}:
        return series.fillna(False).astype(bool)
    return series.astype("string").str.strip().str.lower().isin({"true", "1", "yes"})
