from pathlib import Path
from typing import Any
import json

import numpy as np
import pandas as pd

from config import settings


"""
Utility functions for preparing tabular datasets for the vanilla TabNet pipeline.

This module groups together the common preprocessing steps used after the
fusion CSV has been created. Its responsibility is to transform a raw fused
time-indexed table into train-ready views.

Main responsibilities:
1. Validate train/valid/test split ratios.
2. Create directories for output artifacts.
3. Sort and split data by time order.
4. Generate time-derived features from `time_key`.
5. Compute and apply missing-value fill rules.
6. Build feature and target views for training.
7. Save intermediate CSV/JSON artifacts.
"""


def validate_ratios(train_ratio: float, valid_ratio: float, test_ratio: float) -> None:
    """
    Validate that the dataset split ratios sum to 1.0.

    Parameters
    ----------
    train_ratio : float
        Fraction of rows assigned to the training split.
    valid_ratio : float
        Fraction of rows assigned to the validation split.
    test_ratio : float
        Fraction of rows assigned to the test split.

    Raises
    ------
    ValueError
        If the three ratios do not sum to 1.0.
    """
    total = train_ratio + valid_ratio + test_ratio
    if not np.isclose(total, 1.0):
        raise ValueError(f"Ratios must sum to 1.0, got {total}")


def ensure_dir(path: Path) -> None:
    """
    Ensure that a directory exists.

    If the target directory does not exist, it will be created together with
    any missing parent directories.

    Parameters
    ----------
    path : Path
        Directory path to create if needed.
    """
    path.mkdir(parents=True, exist_ok=True)


def split_by_time(
    df: pd.DataFrame,
    train_ratio: float,
    valid_ratio: float,
    test_ratio: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Split a dataframe into train, validation, and test sets by row order.

    This function assumes the dataframe has already been sorted by time.
    It does not shuffle rows, so temporal order is preserved.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe sorted in chronological order.
    train_ratio : float
        Fraction of rows assigned to the training split.
    valid_ratio : float
        Fraction of rows assigned to the validation split.
    test_ratio : float
        Fraction of rows assigned to the test split.

    Returns
    -------
    tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]
        A tuple of (train_df, valid_df, test_df).

    Raises
    ------
    ValueError
        If the split ratios are invalid or the dataset is too small.
    """
    validate_ratios(train_ratio, valid_ratio, test_ratio)

    n = len(df)
    if n < 10:
        raise ValueError(f"Dataset too small for split: n={n}")

    train_end = int(n * train_ratio)
    valid_end = train_end + int(n * valid_ratio)

    train_df = df.iloc[:train_end].copy()
    valid_df = df.iloc[train_end:valid_end].copy()
    test_df = df.iloc[valid_end:].copy()

    return train_df, valid_df, test_df


def compute_fill_values(train_df: pd.DataFrame, feature_cols: list[str]) -> dict[str, float]:
    """
    Compute missing-value fill rules from the training split only.

    For each numeric feature column, this function computes the median value.
    If the median is NaN, it falls back to 0.0.

    Parameters
    ----------
    train_df : pd.DataFrame
        Training dataframe used as the source for fill statistics.
    feature_cols : list[str]
        List of feature columns to inspect.

    Returns
    -------
    dict[str, float]
        Mapping from feature column name to fill value.
    """
    fill_values: dict[str, float] = {}

    for col in feature_cols:
        series = train_df[col]

        if pd.api.types.is_numeric_dtype(series):
            median_val = series.median()
            if pd.isna(median_val):
                median_val = 0.0
            fill_values[col] = float(median_val)

    return fill_values


def apply_fill_values(df: pd.DataFrame, fill_values: dict[str, float]) -> pd.DataFrame:
    """
    Apply precomputed fill values to matching columns in a dataframe.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe that may contain missing values.
    fill_values : dict[str, float]
        Mapping from column name to replacement value.

    Returns
    -------
    pd.DataFrame
        A new dataframe with missing numeric values filled where applicable.
    """
    out = df.copy()

    for col, val in fill_values.items():
        if col in out.columns:
            out[col] = out[col].fillna(val)

    return out


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Derive time-based features from the `time_key` column.

    Expected input:
    - `time_key` as Unix timestamp in seconds.

    Produced features:
    - `hour_of_day`
    - `day_of_week`
    - `hour_sin`
    - `hour_cos`
    - `dt_local` (string trace field for debugging/inspection)

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe containing a `time_key` column.

    Returns
    -------
    pd.DataFrame
        A new dataframe with derived time features added.

    Raises
    ------
    KeyError
        If `time_key` is missing from the dataframe.
    """
    if "time_key" not in df.columns:
        raise KeyError("Missing required column: time_key")

    out = df.copy()

    dt_local = pd.to_datetime(out["time_key"], unit="s", utc=True).dt.tz_convert("Asia/Ho_Chi_Minh")

    out["hour_of_day"] = dt_local.dt.hour.astype(int)
    out["day_of_week"] = dt_local.dt.dayofweek.astype(int)

    out["hour_sin"] = np.sin(2 * np.pi * out["hour_of_day"] / 24.0)
    out["hour_cos"] = np.cos(2 * np.pi * out["hour_of_day"] / 24.0)

    out["dt_local"] = dt_local.astype(str)

    return out


def sort_by_time(df: pd.DataFrame) -> pd.DataFrame:
    """
    Sort a dataframe by `time_key` in ascending order.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe containing a `time_key` column.

    Returns
    -------
    pd.DataFrame
        A new dataframe sorted by time and reindexed from 0.
    """
    return df.sort_values("time_key").reset_index(drop=True)


def get_feature_columns(df: pd.DataFrame) -> list[str]:
    """
    Build the final feature column list for model input.

    This function selects:
    1. Base feature columns defined in `settings.BASE_FEATURE_COLS`
    2. Time-derived columns if they exist in the dataframe

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe after time features have been added.

    Returns
    -------
    list[str]
        Ordered list of feature column names to use in training.

    Raises
    ------
    ValueError
        If no valid feature columns are found.
    """
    feature_cols: list[str] = []

    for col in settings.BASE_FEATURE_COLS:
        if col in df.columns:
            feature_cols.append(col)

    for col in ["hour_of_day", "day_of_week", "hour_sin", "hour_cos"]:
        if col in df.columns:
            feature_cols.append(col)

    if not feature_cols:
        raise ValueError("No feature columns found in dataframe.")

    return feature_cols


def build_feature_view(df: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    """
    Extract the feature matrix view from a dataframe.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe containing feature columns.
    feature_cols : list[str]
        Columns to keep in the feature view.

    Returns
    -------
    pd.DataFrame
        Dataframe containing only the selected feature columns.

    Raises
    ------
    KeyError
        If one or more requested feature columns are missing.
    """
    missing = [col for col in feature_cols if col not in df.columns]
    if missing:
        raise KeyError(f"Missing feature columns in dataframe: {missing}")

    return df[feature_cols].copy()


def build_target_view(df: pd.DataFrame, target_col: str | None) -> pd.Series | None:
    """
    Extract the target column from a dataframe.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe containing the target column.
    target_col : str | None
        Target column name. If None, no target is returned.

    Returns
    -------
    pd.Series | None
        The target series if `target_col` is provided, otherwise None.

    Raises
    ------
    KeyError
        If `target_col` is not None but does not exist in the dataframe.
    """
    if target_col is None:
        return None

    if target_col not in df.columns:
        raise KeyError(f"Target column not found: {target_col}")

    return df[target_col].copy()


def save_dataframe(df: pd.DataFrame, path: Path) -> None:
    """
    Save a dataframe to CSV.

    Parameters
    ----------
    df : pd.DataFrame
        Dataframe to save.
    path : Path
        Output CSV path.
    """
    ensure_dir(path.parent)
    df.to_csv(path, index=False)


def save_series(series: pd.Series, path: Path) -> None:
    """
    Save a pandas Series to CSV.

    Parameters
    ----------
    series : pd.Series
        Series to save.
    path : Path
        Output CSV path.
    """
    ensure_dir(path.parent)
    series.to_csv(path, index=False)


def save_manifest(path: Path, payload: dict[str, Any]) -> None:
    """
    Save a JSON manifest file.

    This is typically used to record metadata about the prepared dataset,
    such as row counts, feature names, target column, and fill values.

    Parameters
    ----------
    path : Path
        Output JSON path.
    payload : dict[str, Any]
        Serializable metadata dictionary to write.
    """
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")