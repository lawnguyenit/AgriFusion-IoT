from __future__ import annotations

import numpy as np
import pandas as pd

from Backend.Benchmark.dataset_views.configs import V2_SENSOR_VALIDITY_COLUMNS


def coerce_boolean_series(series: pd.Series) -> pd.Series:
    if str(series.dtype) == "boolean":
        return series.fillna(False)
    normalized = series.replace({"true": True, "false": False, "True": True, "False": False})
    return normalized.fillna(False).astype(bool)


def build_masked_measurements(
    canonical_df: pd.DataFrame,
    measurement_columns: tuple[str, ...],
) -> pd.DataFrame:
    masked: dict[str, pd.Series] = {}
    for measurement_column in measurement_columns:
        numeric = pd.to_numeric(canonical_df[measurement_column], errors="coerce")
        validity_column = resolve_validity_column(measurement_column)
        if validity_column is None:
            masked[measurement_column] = numeric.astype(float)
            continue
        valid_mask = coerce_boolean_series(canonical_df[validity_column])
        masked[measurement_column] = numeric.where(valid_mask, np.nan).astype(float)
    return pd.DataFrame(masked, index=canonical_df.index)


def resolve_validity_column(measurement_column: str) -> str | None:
    for prefix, validity_column in V2_SENSOR_VALIDITY_COLUMNS.items():
        if measurement_column.startswith(prefix):
            return validity_column
    return None
