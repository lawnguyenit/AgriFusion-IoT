from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class LowRelativeMoistureThresholds:
    q10: float
    q15: float
    fit_value_count: int
    scope_key: str = "global"


def fit_low_relative_moisture_thresholds(
    values: pd.Series | Iterable[float],
    *,
    scope_key: str = "global",
) -> LowRelativeMoistureThresholds:
    numeric = pd.to_numeric(pd.Series(list(values) if not isinstance(values, pd.Series) else values), errors="coerce").dropna()
    if numeric.empty:
        raise ValueError("Low-relative-moisture threshold fitting requires at least one numeric moisture value.")
    return LowRelativeMoistureThresholds(
        q10=float(numeric.quantile(0.10)),
        q15=float(numeric.quantile(0.15)),
        fit_value_count=int(len(numeric)),
        scope_key=str(scope_key),
    )


def is_low_relative_moisture(
    value: float | int | None,
    thresholds: LowRelativeMoistureThresholds | float,
) -> bool:
    if value is None:
        return False
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return False
    cutoff = thresholds.q10 if isinstance(thresholds, LowRelativeMoistureThresholds) else float(thresholds)
    return float(numeric) <= float(cutoff)
