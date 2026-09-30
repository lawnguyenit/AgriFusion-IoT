from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


def normalize_column_names(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result.columns = [str(column).replace("\ufeff", "").strip() for column in result.columns]
    return result


def require_columns(frame: pd.DataFrame, required: Iterable[str], *, source_name: str) -> None:
    missing = sorted(set(required).difference(frame.columns))
    if missing:
        raise ValueError(f"{source_name} is missing required columns: {missing}")


def reject_duplicate_keys(frame: pd.DataFrame, keys: list[str], *, source_name: str) -> None:
    duplicated = frame.duplicated(keys, keep=False)
    if duplicated.any():
        examples = frame.loc[duplicated, keys].head(5).to_dict(orient="records")
        raise ValueError(f"{source_name} has ambiguous duplicate keys {keys}: {examples}")


def parse_millisecond_timestamps(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return pd.to_datetime(numeric, unit="ms", utc=True, errors="coerce")


def stable_timestamp_sort(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.sort_values(["timestamp", "source_row_number"], kind="stable").reset_index(drop=True)
