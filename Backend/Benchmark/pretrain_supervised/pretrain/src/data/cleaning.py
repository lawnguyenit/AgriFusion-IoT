from __future__ import annotations

import pandas as pd


def validate_required_columns(dataframe: pd.DataFrame, required_columns: list[str]) -> None:
    missing = [column for column in required_columns if column not in dataframe.columns]
    if missing:
        raise KeyError(f"Input CSV is missing required columns: {missing}")


def coerce_numeric_columns(
    dataframe: pd.DataFrame,
    numeric_columns: list[str] | set[str] | tuple[str, ...] | None = None,
) -> pd.DataFrame:
    coerced = dataframe.copy()
    candidate_columns = numeric_columns if numeric_columns is not None else coerced.columns
    for column in candidate_columns:
        if column not in coerced.columns:
            continue
        coerced[column] = pd.to_numeric(coerced[column], errors="coerce")
    return coerced


def remove_invalid_timestamp_rows(dataframe: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    mask = dataframe["timestamp"].isna()
    return dataframe.loc[~mask].copy(), int(mask.sum())


def remove_ph_artifact_rows(dataframe: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    if "pH" not in dataframe.columns:
        return dataframe.copy(), 0
    mask = dataframe["pH"] <= 3.0
    return dataframe.loc[~mask].copy(), int(mask.sum())


def remove_zero_ec_npk_rows(dataframe: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    required_columns = {"EC", "N", "P", "K"}
    if not required_columns.issubset(dataframe.columns):
        return dataframe.copy(), 0
    mask = (
        dataframe["EC"].fillna(0.0).eq(0.0)
        & dataframe["N"].fillna(0.0).eq(0.0)
        & dataframe["P"].fillna(0.0).eq(0.0)
        & dataframe["K"].fillna(0.0).eq(0.0)
    )
    return dataframe.loc[~mask].copy(), int(mask.sum())


def remove_rows_missing_main_features(
    dataframe: pd.DataFrame,
    feature_columns: list[str],
) -> tuple[pd.DataFrame, int]:
    mask = dataframe[feature_columns].notna().all(axis=1)
    return dataframe.loc[mask].copy(), int((~mask).sum())


def add_optional_proxy_feature(
    dataframe: pd.DataFrame,
    split_slices: dict[str, slice],
    proxy_feature_name: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    proxy_columns = ["EC", "N", "P", "K"]
    frame = dataframe.copy()
    train_frame = frame.iloc[split_slices["train"]]
    train_means = train_frame[proxy_columns].mean()
    train_stds = train_frame[proxy_columns].std(ddof=0).replace(0.0, 1.0).fillna(1.0)

    standardized = (frame[proxy_columns] - train_means) / train_stds
    frame[proxy_feature_name] = standardized.mean(axis=1)
    report = {
        "proxy_columns": proxy_columns,
        "train_means": {column: float(value) for column, value in train_means.items()},
        "train_stds": {column: float(value) for column, value in train_stds.items()},
    }
    return frame, report
