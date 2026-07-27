from __future__ import annotations

import numpy as np
import pandas as pd


def add_datetime_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    frame = dataframe.copy()
    frame["timestamp"] = pd.to_numeric(frame["timestamp"], errors="coerce")
    frame = frame.dropna(subset=["timestamp"]).sort_values("timestamp", kind="stable").reset_index(drop=True)
    frame["timestamp"] = frame["timestamp"].astype("int64")
    frame["timestamp_dt"] = pd.to_datetime(frame["timestamp"], unit="s", utc=True)
    frame["gap_hours_since_prev"] = frame["timestamp_dt"].diff().dt.total_seconds().div(3600.0).fillna(0.0).clip(lower=0.0)
    return frame


def delta_1step(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.diff()


def rolling_time_mean(
    series: pd.Series,
    timestamp_index: pd.Series | pd.Index,
    window_hours: int,
    min_points: int = 1,
) -> pd.Series:
    indexed = _indexed_numeric_series(series, timestamp_index)
    return indexed.rolling(f"{int(window_hours)}h", min_periods=min_points).mean().reset_index(drop=True)


def rolling_time_min(
    series: pd.Series,
    timestamp_index: pd.Series | pd.Index,
    window_hours: int,
    min_points: int = 1,
) -> pd.Series:
    indexed = _indexed_numeric_series(series, timestamp_index)
    return indexed.rolling(f"{int(window_hours)}h", min_periods=min_points).min().reset_index(drop=True)


def rolling_time_max(
    series: pd.Series,
    timestamp_index: pd.Series | pd.Index,
    window_hours: int,
    min_points: int = 1,
) -> pd.Series:
    indexed = _indexed_numeric_series(series, timestamp_index)
    return indexed.rolling(f"{int(window_hours)}h", min_periods=min_points).max().reset_index(drop=True)


def rolling_time_range(
    series: pd.Series,
    timestamp_index: pd.Series | pd.Index,
    window_hours: int,
    min_points: int = 2,
) -> pd.Series:
    rolling_max = rolling_time_max(series, timestamp_index, window_hours, min_points=min_points)
    rolling_min = rolling_time_min(series, timestamp_index, window_hours, min_points=min_points)
    return rolling_max - rolling_min


def rolling_time_slope(
    series: pd.Series,
    timestamp_index: pd.Series | pd.Index,
    window_hours: int,
    min_points: int = 3,
) -> pd.Series:
    indexed = _indexed_numeric_series(series, timestamp_index)

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

    return indexed.rolling(f"{int(window_hours)}h", min_periods=min_points).apply(_fit, raw=False).reset_index(drop=True)


def rolling_condition_duration_hours(
    condition: pd.Series | np.ndarray,
    timestamp_index: pd.Series | pd.Index,
    gap_hours_since_prev: pd.Series,
    window_hours: int,
) -> pd.Series:
    flag = pd.Series(condition, dtype=float).reset_index(drop=True).clip(lower=0.0, upper=1.0)
    weighted = flag * pd.to_numeric(gap_hours_since_prev, errors="coerce").fillna(0.0).reset_index(drop=True)
    indexed = pd.Series(weighted.to_numpy(dtype=float), index=pd.DatetimeIndex(timestamp_index))
    return indexed.rolling(f"{int(window_hours)}h", min_periods=1).sum().reset_index(drop=True)


def rolling_condition_ratio(
    condition: pd.Series | np.ndarray,
    timestamp_index: pd.Series | pd.Index,
    window_hours: int,
) -> pd.Series:
    frame = pd.DataFrame(
        {
            "flag": pd.Series(condition, dtype=float).reset_index(drop=True).clip(lower=0.0, upper=1.0),
        }
    )
    frame["timestamp_dt"] = pd.DatetimeIndex(timestamp_index)
    frame["gap_hours_since_prev"] = frame["timestamp_dt"].diff().dt.total_seconds().div(3600.0).fillna(0.0).clip(lower=0.0)
    duration = rolling_condition_duration_hours(
        frame["flag"],
        frame["timestamp_dt"],
        frame["gap_hours_since_prev"],
        window_hours=window_hours,
    )
    return (duration / float(window_hours)).clip(lower=0.0, upper=1.0)


def _indexed_numeric_series(
    series: pd.Series,
    timestamp_index: pd.Series | pd.Index,
) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").to_numpy()
    return pd.Series(values, index=pd.DatetimeIndex(timestamp_index))
