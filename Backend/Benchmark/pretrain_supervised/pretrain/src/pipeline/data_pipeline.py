from __future__ import annotations

from pathlib import Path

import joblib

from Backend.Benchmark.pretrain_supervised.pretrain.src.config.settings import PretrainConfig
from Backend.Benchmark.pretrain_supervised.pretrain.src.data.contracts import (
    DataPipelineArtifacts,
    DataPipelineResult,
)
from Backend.Benchmark.pretrain_supervised.pretrain.src.data.preprocessing import prepare_pretraining_dataframe
from Backend.Benchmark.pretrain_supervised.pretrain.src.data.scaling import export_scaler_stats, scale_dataset_splits
from Backend.Benchmark.pretrain_supervised.pretrain.src.utils.artifacts import write_json


def build_feature_schema(
    config: PretrainConfig,
    feature_columns: list[str],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "objective": "self_supervised_masked_feature_reconstruction",
        "feature_columns": feature_columns,
        "base_feature_columns": list(config.feature_columns),
        "optional_feature_columns": (
            [config.optional_proxy_feature] if config.include_npk_proxy else []
        ),
        "excluded_from_model": {
            "timestamp": "Used only for sorting, local time derivation, and chronological splitting.",
            "N": "Excluded from the main feature set when the source schema still contains N.",
            "P": "Excluded from the main feature set when the source schema still contains P.",
            "K": "Excluded from the main feature set when the source schema still contains K.",
            "ec_npk_consistency_flag": "Used only for reporting and data-quality inspection when present.",
            "ec_npk_consistency_score": "Used only for reporting and data-quality inspection when present.",
        },
        "include_npk_proxy": config.include_npk_proxy,
    }


def run_data_pipeline(config: PretrainConfig, output_dir: Path) -> DataPipelineResult:
    prepared_dataset = prepare_pretraining_dataframe(config)
    scaled_splits = scale_dataset_splits(prepared_dataset)
    feature_schema = build_feature_schema(config, prepared_dataset.feature_columns)

    cleaned_pretrain_input_path = output_dir / "cleaned_input.csv"
    feature_schema_path = output_dir / "feature_schema.json"
    scaler_path = output_dir / "scaler.pkl"
    scaler_stats_path = output_dir / "scaler_stats.json"

    prepared_dataset.dataframe.to_csv(cleaned_pretrain_input_path, index=False)
    write_json(feature_schema_path, feature_schema)
    joblib.dump(scaled_splits.scaler, scaler_path)
    write_json(scaler_stats_path, export_scaler_stats(scaled_splits.scaler, prepared_dataset.feature_columns))

    artifacts = DataPipelineArtifacts(
        cleaned_input_path=cleaned_pretrain_input_path,
        feature_schema_path=feature_schema_path,
        scaler_path=scaler_path,
        scaler_stats_path=scaler_stats_path,
    )
    return DataPipelineResult(
        prepared_dataset=prepared_dataset,
        scaled_splits=scaled_splits,
        feature_schema=feature_schema,
        artifacts=artifacts,
    )
