from __future__ import annotations

import pandas as pd

from Backend.Benchmark.tabnet.src.config.settings import RAW_REQUIRED_COLUMNS


BASE_NUMERIC_COLUMNS = [
    "soil_temp",
    "soil_humidity",
    "air_temp",
    "air_humidity",
    "EC",
    "pH",
    "N",
    "P",
    "K",
    "ec_npk_consistency_score",
    "ec_npk_consistency_flag",
]


def validate_required_columns(dataframe: pd.DataFrame) -> None:
    missing = [column for column in RAW_REQUIRED_COLUMNS if column not in dataframe.columns]
    if missing:
        raise KeyError(f"Input CSV is missing required columns: {missing}")


def coerce_numeric_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    coerced = dataframe.copy()
    coerced["timestamp"] = pd.to_numeric(coerced["timestamp"], errors="coerce")
    for column in BASE_NUMERIC_COLUMNS:
        coerced[column] = pd.to_numeric(coerced[column], errors="coerce")
    return coerced


def remove_invalid_timestamp_rows(dataframe: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    mask = dataframe["timestamp"].isna()
    return dataframe.loc[~mask].copy(), int(mask.sum())


def remove_ph_artifact_rows(dataframe: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    mask = dataframe["pH"] <= 3.0
    return dataframe.loc[~mask].copy(), int(mask.sum())


def remove_zero_ec_npk_rows(dataframe: pd.DataFrame) -> tuple[pd.DataFrame, int]:
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
