from __future__ import annotations

import json

import pandas as pd


CONTINUOUS_SHIFT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("sht.temp_c", "sht.valid"),
    ("sht.humidity_pct", "sht.valid"),
    ("npk.soil_temp_c", "npk.valid"),
    ("npk.soil_moisture_pct", "npk.valid"),
    ("npk.ph", "npk.valid"),
    ("npk.ec", "npk.valid"),
    ("npk.n_proxy", "npk.valid"),
    ("npk.p_proxy", "npk.valid"),
    ("npk.k_proxy", "npk.valid"),
    ("record.delta_prev_sec", None),
)

DISCRETE_SHIFT_COLUMNS: tuple[str, ...] = (
    "npk.valid",
    "sht.valid",
    "record.gap_flag",
    "record.missing_slot_count",
)


def build_cross_position_feature_shift_raw(canonical_df: pd.DataFrame) -> pd.DataFrame:
    return _build_cross_position_feature_shift(canonical_df, mask_invalid=False)


def build_cross_position_feature_shift_isr(canonical_df: pd.DataFrame) -> pd.DataFrame:
    return _build_cross_position_feature_shift(canonical_df, mask_invalid=True)


def _build_cross_position_feature_shift(canonical_df: pd.DataFrame, *, mask_invalid: bool) -> pd.DataFrame:
    p1 = canonical_df.loc[canonical_df["deployment_domain_name"].astype("string") == "P1_SOURCE"].copy()
    p2 = canonical_df.loc[canonical_df["deployment_domain_name"].astype("string") == "P2_TARGET"].copy()
    rows: list[dict[str, object]] = []
    for column_name, validity_column in CONTINUOUS_SHIFT_COLUMNS:
        p1_values = _resolve_feature_series(p1, column_name, validity_column, mask_invalid=mask_invalid)
        p2_values = _resolve_feature_series(p2, column_name, validity_column, mask_invalid=mask_invalid)
        rows.append(
            {
                "data_variant": "isr_masked" if mask_invalid else "raw_canonical",
                "feature_name": column_name,
                "p1_count": int(p1_values.notna().sum()),
                "p2_count": int(p2_values.notna().sum()),
                "p1_valid_count": int(p1_values.notna().sum()),
                "p2_valid_count": int(p2_values.notna().sum()),
                "p1_missing_rate": float(1.0 - p1_values.notna().mean()) if len(p1) else pd.NA,
                "p2_missing_rate": float(1.0 - p2_values.notna().mean()) if len(p2) else pd.NA,
                "p1_median": _safe_stat(p1_values, "median"),
                "p2_median": _safe_stat(p2_values, "median"),
                "p1_iqr": _safe_iqr(p1_values),
                "p2_iqr": _safe_iqr(p2_values),
                "p1_min": _safe_stat(p1_values, "min"),
                "p2_min": _safe_stat(p2_values, "min"),
                "p1_max": _safe_stat(p1_values, "max"),
                "p2_max": _safe_stat(p2_values, "max"),
                "p1_q05": _safe_quantile(p1_values, 0.05),
                "p2_q05": _safe_quantile(p2_values, 0.05),
                "p1_q10": _safe_quantile(p1_values, 0.10),
                "p2_q10": _safe_quantile(p2_values, 0.10),
                "p1_q25": _safe_quantile(p1_values, 0.25),
                "p2_q25": _safe_quantile(p2_values, 0.25),
                "p1_q50": _safe_quantile(p1_values, 0.50),
                "p2_q50": _safe_quantile(p2_values, 0.50),
                "p1_q75": _safe_quantile(p1_values, 0.75),
                "p2_q75": _safe_quantile(p2_values, 0.75),
                "p1_q90": _safe_quantile(p1_values, 0.90),
                "p2_q90": _safe_quantile(p2_values, 0.90),
                "p1_q95": _safe_quantile(p1_values, 0.95),
                "p2_q95": _safe_quantile(p2_values, 0.95),
                "median_shift": _safe_shift(p1_values, p2_values),
                "robust_median_shift_norm_p1_iqr": _robust_shift(p1_values, p2_values),
                "p1_zero_count": int((p1_values.fillna(1) == 0).sum()),
                "p2_zero_count": int((p2_values.fillna(1) == 0).sum()),
            }
        )
    for column_name in DISCRETE_SHIFT_COLUMNS:
        p1_values = _resolve_feature_series(p1, column_name, None, mask_invalid=False)
        p2_values = _resolve_feature_series(p2, column_name, None, mask_invalid=False)
        rows.append(
            {
                "data_variant": "isr_masked" if mask_invalid else "raw_canonical",
                "feature_name": column_name,
                "p1_count": int(len(p1)),
                "p2_count": int(len(p2)),
                "p1_valid_count": int(p1_values.notna().sum()),
                "p2_valid_count": int(p2_values.notna().sum()),
                "p1_missing_rate": float(1.0 - p1_values.notna().mean()) if len(p1) else pd.NA,
                "p2_missing_rate": float(1.0 - p2_values.notna().mean()) if len(p2) else pd.NA,
                "p1_positive_count": int((p1_values.fillna(0) > 0).sum()),
                "p2_positive_count": int((p2_values.fillna(0) > 0).sum()),
                "p1_positive_rate": float((p1_values.fillna(0) > 0).mean()) if len(p1) else pd.NA,
                "p2_positive_rate": float((p2_values.fillna(0) > 0).mean()) if len(p2) else pd.NA,
                "p1_invalid_count": int((p1_values.fillna(1) == 0).sum()) if column_name in {"npk.valid", "sht.valid"} else pd.NA,
                "p2_invalid_count": int((p2_values.fillna(1) == 0).sum()) if column_name in {"npk.valid", "sht.valid"} else pd.NA,
                "p1_invalid_rate": float((p1_values.fillna(1) == 0).mean()) if len(p1) and column_name in {"npk.valid", "sht.valid"} else pd.NA,
                "p2_invalid_rate": float((p2_values.fillna(1) == 0).mean()) if len(p2) and column_name in {"npk.valid", "sht.valid"} else pd.NA,
                "p1_sum": float(p1_values.fillna(0).sum()) if column_name == "record.missing_slot_count" else pd.NA,
                "p2_sum": float(p2_values.fillna(0).sum()) if column_name == "record.missing_slot_count" else pd.NA,
            }
        )
    return pd.DataFrame(rows).convert_dtypes()


def build_cross_position_label_transport(
    *,
    point_labels: pd.DataFrame,
    v2_temporal_3h: pd.DataFrame,
    v2_temporal_8h: pd.DataFrame,
    v6_events: pd.DataFrame,
    v6_blocks: pd.DataFrame,
    frozen_low_threshold: float,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for domain_name, frame in _domain_frames(point_labels):
        transport_summary = _build_transport_summary(
            frame=frame,
            excluded_label_names={"<NA>", "excluded_technical_invalid", "insufficient_window_context", "insufficient_coverage_block"},
            reference_label_names={"normal_point"},
        )
        rows.append(
            {
                "deployment_domain": domain_name,
                "artifact_name": "point_labels",
                "metric_name": "label_distribution",
                "metric_value": json.dumps(transport_summary["label_counts"], ensure_ascii=False, separators=(",", ":")),
                "sample_count": transport_summary["total_count"],
                "eligible_count": transport_summary["eligible_count"],
                "excluded_count": transport_summary["excluded_count"],
                "majority_class": transport_summary["majority_class"],
                "majority_prevalence_among_eligible": transport_summary["majority_prevalence_among_eligible"],
                "reference_class_missing": transport_summary["reference_class_missing"],
                "collapse_indicator": transport_summary["collapse_indicator"],
                "collapse_reason": transport_summary["collapse_reason"],
                "notes": f"Frozen low-moisture threshold q0.10 = {frozen_low_threshold:.4f}",
            }
        )
    for view_name, frame in (("v2_temporal_3h", v2_temporal_3h), ("v2_temporal_8h", v2_temporal_8h)):
        for domain_name, domain_frame in _domain_frames(frame):
            transport_summary = _build_transport_summary(
                frame=domain_frame,
                excluded_label_names={"insufficient_window_context"},
                reference_label_names={"normal_window_context"},
            )
            rows.append(
                {
                    "deployment_domain": domain_name,
                    "artifact_name": view_name,
                    "metric_name": "label_distribution",
                    "metric_value": json.dumps(transport_summary["label_counts"], ensure_ascii=False, separators=(",", ":")),
                    "sample_count": transport_summary["total_count"],
                    "eligible_count": transport_summary["eligible_count"],
                    "excluded_count": transport_summary["excluded_count"],
                    "majority_class": transport_summary["majority_class"],
                    "majority_prevalence_among_eligible": transport_summary["majority_prevalence_among_eligible"],
                    "reference_class_missing": transport_summary["reference_class_missing"],
                    "collapse_indicator": transport_summary["collapse_indicator"],
                    "collapse_reason": transport_summary["collapse_reason"],
                    "notes": "Frozen same-threshold temporal distribution.",
                }
            )
    for artifact_name, frame in (("v6_events", v6_events), ("v6_blocks", v6_blocks)):
        for domain_name, domain_frame in _domain_frames(frame):
            transport_summary = _build_transport_summary(
                frame=domain_frame,
                excluded_label_names={"insufficient_coverage_block"},
                reference_label_names={"normal", "normal_block"},
            )
            duration_hours = pd.NA
            if "event_start_local" in domain_frame.columns and "event_end_local" in domain_frame.columns:
                start = pd.to_datetime(domain_frame["event_start_local"], errors="coerce")
                end = pd.to_datetime(domain_frame["event_end_local"], errors="coerce")
                duration_hours = float((end - start).dt.total_seconds().sum() / 3600.0) if len(domain_frame) else pd.NA
            rows.append(
                {
                    "deployment_domain": domain_name,
                    "artifact_name": artifact_name,
                    "metric_name": "label_distribution",
                    "metric_value": json.dumps(transport_summary["label_counts"], ensure_ascii=False, separators=(",", ":")),
                    "sample_count": transport_summary["total_count"],
                    "eligible_count": transport_summary["eligible_count"],
                    "excluded_count": transport_summary["excluded_count"],
                    "majority_class": transport_summary["majority_class"],
                    "majority_prevalence_among_eligible": transport_summary["majority_prevalence_among_eligible"],
                    "reference_class_missing": transport_summary["reference_class_missing"],
                    "collapse_indicator": transport_summary["collapse_indicator"],
                    "collapse_reason": transport_summary["collapse_reason"],
                    "notes": f"aggregate_duration_hours={duration_hours}",
                }
            )
    return pd.DataFrame(rows).convert_dtypes()


def _domain_frames(frame: pd.DataFrame):
    for domain_name, group in frame.groupby("deployment_domain_name", sort=False, dropna=False):
        yield str(domain_name), group.copy()


def _safe_stat(series: pd.Series, op: str):
    values = series.dropna()
    if values.empty:
        return pd.NA
    return float(getattr(values, op)())


def _safe_quantile(series: pd.Series, q: float):
    values = series.dropna()
    if values.empty:
        return pd.NA
    return float(values.quantile(q))


def _safe_iqr(series: pd.Series):
    values = series.dropna()
    if values.empty:
        return pd.NA
    return float(values.quantile(0.75) - values.quantile(0.25))


def _safe_shift(p1: pd.Series, p2: pd.Series):
    if p1.dropna().empty or p2.dropna().empty:
        return pd.NA
    return float(p2.dropna().median() - p1.dropna().median())


def _robust_shift(p1: pd.Series, p2: pd.Series):
    p1_values = p1.dropna()
    p2_values = p2.dropna()
    if p1_values.empty or p2_values.empty:
        return pd.NA
    p1_iqr = float(p1_values.quantile(0.75) - p1_values.quantile(0.25))
    if p1_iqr == 0:
        return pd.NA
    return float((p2_values.median() - p1_values.median()) / p1_iqr)


def _coerce_numeric_series(series: pd.Series) -> pd.Series:
    if str(series.dtype) == "boolean" or pd.api.types.is_bool_dtype(series):
        return series.astype("Int64").astype("Float64")
    return pd.to_numeric(series, errors="coerce")


def _string_count_dict(series: pd.Series) -> dict[str, int]:
    return {
        str(label): int(count)
        for label, count in series.astype("string").value_counts(dropna=False).items()
    }


def _resolve_feature_series(
    frame: pd.DataFrame,
    feature_name: str,
    validity_column: str | None,
    *,
    mask_invalid: bool,
) -> pd.Series:
    if feature_name not in frame.columns:
        return pd.Series(dtype="float64")
    series = _coerce_numeric_series(frame[feature_name])
    if not mask_invalid or validity_column is None or validity_column not in frame.columns:
        return series
    validity = frame[validity_column].fillna(False)
    if str(validity.dtype) != "boolean":
        validity = validity.astype("boolean")
    return series.where(validity.astype(bool), pd.NA)


def _build_transport_summary(
    *,
    frame: pd.DataFrame,
    excluded_label_names: set[str],
    reference_label_names: set[str],
) -> dict[str, object]:
    label_counts = _string_count_dict(frame["label_name"])
    if "label_status" in frame.columns:
        eligible_mask = frame["label_status"].astype("string") == "LABELED"
    elif "effective_partition" in frame.columns:
        eligible_mask = frame["effective_partition"].astype("string") != "excluded"
    else:
        eligible_mask = ~frame["label_name"].astype("string").isin(excluded_label_names)
    eligible_frame = frame.loc[eligible_mask].copy()
    eligible_counts = _string_count_dict(eligible_frame["label_name"]) if not eligible_frame.empty else {}
    eligible_count = int(len(eligible_frame))
    total_count = int(len(frame))
    excluded_count = total_count - eligible_count
    majority_class = pd.NA
    majority_prevalence = pd.NA
    if eligible_counts:
        majority_class = max(eligible_counts, key=eligible_counts.get)
        majority_prevalence = float(eligible_counts[str(majority_class)] / max(eligible_count, 1))
    reference_class_missing = bool(
        eligible_count > 0
        and all(eligible_counts.get(reference_label_name, 0) == 0 for reference_label_name in reference_label_names)
    )
    prevalence_collapse = bool(pd.notna(majority_prevalence) and float(majority_prevalence) >= 0.90)
    collapse_indicator = bool(reference_class_missing or prevalence_collapse)
    collapse_reasons: list[str] = []
    if reference_class_missing:
        collapse_reasons.append("reference_class_missing")
    if prevalence_collapse:
        collapse_reasons.append("majority_prevalence_ge_0.90")
    return {
        "label_counts": label_counts,
        "eligible_count": eligible_count,
        "excluded_count": excluded_count,
        "total_count": total_count,
        "majority_class": majority_class,
        "majority_prevalence_among_eligible": majority_prevalence,
        "reference_class_missing": reference_class_missing,
        "collapse_indicator": collapse_indicator,
        "collapse_reason": "|".join(collapse_reasons) if collapse_reasons else pd.NA,
    }
