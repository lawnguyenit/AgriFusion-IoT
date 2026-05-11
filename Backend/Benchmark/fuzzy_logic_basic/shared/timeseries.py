from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

try:
    from Backend.Config.IO.io_csv import load_csv
except ImportError:
    from ...Config.IO.io_csv import load_csv


def load_alignment_csv(csv_path: Path) -> pd.DataFrame:
    df = load_csv(csv_path)
    if "timestamp" not in df.columns:
        raise KeyError(f"Missing required 'timestamp' column in {csv_path}")

    df = df.copy()
    df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
    df["timestamp"] = df["timestamp"].astype("int64")
    df["timestamp_dt"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    return df


def attach_master_timeline_features(df: pd.DataFrame) -> pd.DataFrame:
    output = df.copy().sort_values("timestamp_dt").reset_index(drop=True)
    output["source_sample_count"] = 1
    output["hours_since_observation"] = 0.0
    output["observed_in_window"] = 1
    output["dt_hours"] = output["timestamp_dt"].diff().dt.total_seconds().div(3600.0).fillna(0.0)
    return output


def rolling_slope(series: pd.Series, window_points: int, min_points: int | None = None) -> pd.Series:
    minimum = min_points if min_points is not None else max(2, min(window_points, 3))

    def _fit(values: np.ndarray) -> float:
        valid_mask = np.isfinite(values)
        valid = values[valid_mask]
        if valid.size < minimum:
            return np.nan
        x = np.arange(valid.size, dtype=float)
        x_mean = x.mean()
        y_mean = valid.mean()
        variance = ((x - x_mean) ** 2).sum()
        if variance <= 1e-9:
            return 0.0
        covariance = ((x - x_mean) * (valid - y_mean)).sum()
        return float(covariance / variance)

    return series.astype(float).rolling(window=window_points, min_periods=minimum).apply(_fit, raw=True)


def rolling_time_slope(
    series: pd.Series,
    timestamp_index: pd.Series | pd.Index,
    window_hours: int,
    min_points: int = 3,
) -> pd.Series:
    
    # tạo ra index bởi timestamp_index
    datetime_index = pd.DatetimeIndex(timestamp_index)

    # tạo ra series mới với giá trị đã được chuyển đổi sang số và index là datetime_index
    indexed = pd.Series(pd.to_numeric(series, errors="coerce").to_numpy(), index=datetime_index)

    def _fit(window: pd.Series) -> float:
        numeric_window = window.dropna()
        if len(numeric_window) < min_points:
            return np.nan
        x = (numeric_window.index - numeric_window.index[0]).total_seconds() / 3600.0
        x = np.asarray(x, dtype=float)
        y = numeric_window.to_numpy(dtype=float)
        variance = ((x - x.mean()) ** 2).sum()
        if variance <= 1e-9:
            return 0.0
        covariance = ((x - x.mean()) * (y - y.mean())).sum()
        return float(covariance / variance)

    window = f"{int(window_hours)}h"
    return indexed.rolling(window, min_periods=min_points).apply(_fit, raw=False).reset_index(drop=True)


def rolling_time_mean(
    series: pd.Series,
    timestamp_index: pd.Series | pd.Index,
    window_hours: int,
    min_points: int = 1,
) -> pd.Series:
    indexed = pd.Series(pd.to_numeric(series, errors="coerce").to_numpy(), index=pd.DatetimeIndex(timestamp_index))
    return indexed.rolling(f"{int(window_hours)}h", min_periods=min_points).mean().reset_index(drop=True)


def rolling_time_max(
    series: pd.Series,
    timestamp_index: pd.Series | pd.Index,
    window_hours: int,
    min_points: int = 1,
) -> pd.Series:
    indexed = pd.Series(pd.to_numeric(series, errors="coerce").to_numpy(), index=pd.DatetimeIndex(timestamp_index))
    return indexed.rolling(f"{int(window_hours)}h", min_periods=min_points).max().reset_index(drop=True)


def lag_at_or_before_hours(
    series: pd.Series,
    timestamp_index: pd.Series | pd.Index,
    lag_hours: float,
) -> pd.Series:
    datetime_index = pd.DatetimeIndex(timestamp_index)
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    order = np.argsort(datetime_index.values)
    sorted_times = datetime_index.values[order]
    sorted_values = values[order]

    target_times = (datetime_index - pd.to_timedelta(float(lag_hours), unit="h")).values
    positions = np.searchsorted(sorted_times, target_times, side="right") - 1

    output = np.full(len(datetime_index), np.nan, dtype=float)
    valid = positions >= 0
    if np.any(valid):
        output[valid] = sorted_values[positions[valid]]
    return pd.Series(output, index=pd.RangeIndex(len(output)))


def rolling_max(series: pd.Series, window_points: int, min_points: int = 1) -> pd.Series:
    return series.astype(float).rolling(window=window_points, min_periods=min_points).max()


def rolling_mean(series: pd.Series, window_points: int, min_points: int = 1) -> pd.Series:
    return series.astype(float).rolling(window=window_points, min_periods=min_points).mean()
