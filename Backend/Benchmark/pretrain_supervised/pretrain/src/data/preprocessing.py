from __future__ import annotations

import numpy as np

import pandas as pd

from Backend.Benchmark.pretrain_supervised.pretrain.src.config.settings import PretrainConfig
from Backend.Benchmark.pretrain_supervised.pretrain.src.data.cleaning import (
    add_optional_proxy_feature,
    coerce_numeric_columns,
    remove_invalid_timestamp_rows,
    remove_ph_artifact_rows,
    remove_rows_missing_main_features,
    remove_zero_ec_npk_rows,
    validate_required_columns,
)
from Backend.Benchmark.pretrain_supervised.pretrain.src.data.contracts import PreparedDataset
from Backend.Benchmark.pretrain_supervised.pretrain.src.data.feature_engineering import (
    build_gap_minutes_since_prev,
    build_local_time_features,
)
from Backend.Benchmark.pretrain_supervised.pretrain.src.data.io import load_input_dataframe
from Backend.Benchmark.pretrain_supervised.pretrain.src.data.splitting import build_split_slices


def prepare_pretraining_dataframe(config: PretrainConfig) -> PreparedDataset:
    source_df = load_input_dataframe(config.input_csv)
    validate_required_columns(source_df, config.required_columns)

    row_counts: dict[str, int] = {"before_cleaning": int(len(source_df))}
    removal_counts: dict[str, int] = {}

    dataframe = coerce_numeric_columns(source_df)
    dataframe, removal_counts["invalid_timestamp_rows"] = remove_invalid_timestamp_rows(dataframe)

    dataframe = dataframe.sort_values("timestamp", kind="stable").reset_index(drop=True)
    timestamp_utc = pd.to_datetime(dataframe["timestamp"], unit="s", utc=True)
    local_datetime = timestamp_utc.dt.tz_convert(config.timezone)

    dataframe["local_datetime"] = local_datetime.dt.strftime("%Y-%m-%d %H:%M:%S%z")
    time_feature_df = build_local_time_features(local_datetime)
    dataframe[time_feature_df.columns] = time_feature_df

    dataframe["gap_minutes_since_prev"] = build_gap_minutes_since_prev(timestamp_utc)

    dataframe, removal_counts["ph_leq_3_rows"] = remove_ph_artifact_rows(dataframe)
    dataframe, removal_counts["all_zero_ec_npk_rows"] = remove_zero_ec_npk_rows(dataframe)
    dataframe, removal_counts["missing_main_feature_rows"] = remove_rows_missing_main_features(
        dataframe,
        config.feature_columns,
    )
    dataframe = dataframe.reset_index(drop=True)

    split_slices = build_split_slices(
        row_count=len(dataframe),
        train_ratio=config.train_ratio,
        validation_ratio=config.validation_ratio,
    )

    feature_columns = list(config.feature_columns)
    proxy_report: dict[str, object] | None = None
    if config.include_npk_proxy:
        dataframe, proxy_report = add_optional_proxy_feature(
            dataframe=dataframe,
            split_slices=split_slices,
            proxy_feature_name=config.optional_proxy_feature,
        )
        feature_columns.append(config.optional_proxy_feature)

    row_counts["after_cleaning"] = int(len(dataframe))
    split_labels = np.empty(len(dataframe), dtype=object)
    split_labels[split_slices["train"]] = "train"
    split_labels[split_slices["validation"]] = "validation"
    split_labels[split_slices["test"]] = "test"
    dataframe["split"] = split_labels

    split_counts = {
        split_name: int(split_slice.stop - split_slice.start)
        for split_name, split_slice in split_slices.items()
    }

    quality_report = {
        "consistency_flag_distribution": _build_consistency_flag_distribution(dataframe),
        "consistency_score": _build_consistency_score_summary(dataframe),
        "optional_proxy": proxy_report,
    }

    return PreparedDataset(
        dataframe=dataframe,
        feature_columns=feature_columns,
        split_counts=split_counts,
        row_counts=row_counts,
        removal_counts=removal_counts,
        quality_report=quality_report,
        split_slices=split_slices,
    )


def _build_consistency_flag_distribution(dataframe: pd.DataFrame) -> dict[str, int] | None:
    if "ec_npk_consistency_flag" not in dataframe.columns:
        return None
    return {
        str(int(flag)): int(count)
        for flag, count in dataframe["ec_npk_consistency_flag"].value_counts(dropna=False).sort_index().items()
    }


def _build_consistency_score_summary(dataframe: pd.DataFrame) -> dict[str, float] | None:
    if "ec_npk_consistency_score" not in dataframe.columns:
        return None
    return {
        "min": float(dataframe["ec_npk_consistency_score"].min()),
        "max": float(dataframe["ec_npk_consistency_score"].max()),
        "mean": float(dataframe["ec_npk_consistency_score"].mean()),
    }
