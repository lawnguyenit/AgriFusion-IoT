from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd


def clamp01(value: float | int | None) -> float:
    if value is None or math.isnan(float(value)):
        return 0.0
    return float(max(0.0, min(1.0, float(value))))


def clip01_series(series: pd.Series) -> pd.Series:
    return series.fillna(0.0).clip(lower=0.0, upper=1.0)


def left_shoulder_series(series: pd.Series, one_at_or_below: float, zero_at_or_above: float) -> pd.Series:
    denominator = max(zero_at_or_above - one_at_or_below, 1e-9)
    values = (zero_at_or_above - series.astype(float)) / denominator
    return values.clip(lower=0.0, upper=1.0).fillna(0.0)


def right_shoulder_series(series: pd.Series, zero_at_or_below: float, one_at_or_above: float) -> pd.Series:
    denominator = max(one_at_or_above - zero_at_or_below, 1e-9)
    values = (series.astype(float) - zero_at_or_below) / denominator
    return values.clip(lower=0.0, upper=1.0).fillna(0.0)


def band_context_risk_series(
    series: pd.Series,
    *,
    safe_low: float,
    safe_high: float,
    warning_low: float,
    warning_high: float,
    critical_low: float,
    critical_high: float,
) -> pd.Series:
    values = pd.Series(0.0, index=series.index, dtype=float)
    numeric = series.astype(float)

    lower_warning_mask = (numeric < safe_low) & (numeric >= warning_low)
    values.loc[lower_warning_mask] = 0.5 * (safe_low - numeric.loc[lower_warning_mask]) / max(safe_low - warning_low, 1e-9)

    lower_critical_mask = numeric < warning_low
    values.loc[lower_critical_mask] = 0.5 + 0.5 * (warning_low - numeric.loc[lower_critical_mask]) / max(warning_low - critical_low, 1e-9)

    upper_warning_mask = (numeric > safe_high) & (numeric <= warning_high)
    values.loc[upper_warning_mask] = 0.5 * (numeric.loc[upper_warning_mask] - safe_high) / max(warning_high - safe_high, 1e-9)

    upper_critical_mask = numeric > warning_high
    values.loc[upper_critical_mask] = 0.5 + 0.5 * (numeric.loc[upper_critical_mask] - warning_high) / max(critical_high - warning_high, 1e-9)

    return values.clip(lower=0.0, upper=1.0).fillna(0.0)


def weighted_sum_series(parts: Iterable[tuple[pd.Series, float]]) -> pd.Series:
    result: pd.Series | None = None
    for series, weight in parts:
        weighted = series.astype(float).fillna(0.0) * float(weight)
        result = weighted if result is None else result.add(weighted, fill_value=0.0)
    if result is None:
        return pd.Series(dtype=float)
    return result.clip(lower=0.0, upper=1.0)


def piecewise_score(value: float, thresholds: tuple[float, float, float]) -> float:
    watch_start, warning_start, critical_start = thresholds
    if value <= watch_start:
        return clamp01((value / max(watch_start, 1e-9)) * 0.25)
    if value <= warning_start:
        span = max(warning_start - watch_start, 1e-9)
        return clamp01(0.25 + ((value - watch_start) / span) * 0.20)
    if value <= critical_start:
        span = max(critical_start - warning_start, 1e-9)
        return clamp01(0.45 + ((value - warning_start) / span) * 0.20)
    extra = min(1.0, (value - critical_start) / max(critical_start, 1e-9))
    return clamp01(0.65 + extra * 0.35)


def piecewise_score_series(series: pd.Series, thresholds: tuple[float, float, float]) -> pd.Series:
    return series.apply(lambda value: piecewise_score(float(value), thresholds) if pd.notna(value) else 0.0)
