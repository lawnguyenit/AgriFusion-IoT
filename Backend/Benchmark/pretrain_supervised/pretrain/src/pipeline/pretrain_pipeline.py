from __future__ import annotations

from pathlib import Path

from Backend.Benchmark.pretrain_supervised.pretrain.src.config.settings import PretrainConfig
from Backend.Benchmark.pretrain_supervised.pretrain.src.data.contracts import DataPipelineResult, PreparedDataset
from Backend.Benchmark.pretrain_supervised.pretrain.src.pipeline.data_pipeline import run_data_pipeline
from Backend.Benchmark.pretrain_supervised.pretrain.src.pipeline.model_pipeline import run_model_pipeline
from Backend.Benchmark.pretrain_supervised.pretrain.src.utils.artifacts import (
    create_run_directory,
    write_json,
    write_yaml,
)

def _build_report(
    *,
    config: PretrainConfig,
    data_result: DataPipelineResult,
    output_dir: Path,
    run_id: str,
    history: dict[str, object],
    artifacts: dict[str, str],
) -> dict[str, object]:
    prepared = data_result.prepared_dataset
    return {
        "benchmark_family": config.benchmark_family,
        "benchmark_version": config.benchmark_version,
        "run_id": run_id,
        "input_csv": str(config.input_csv),
        "output_dir": str(output_dir),
        "feature_columns": prepared.feature_columns,
        "row_counts": prepared.row_counts,
        "split_counts": prepared.split_counts,
        "removal_counts": prepared.removal_counts,
        "quality_report": prepared.quality_report,
        "training": history,
        "artifacts": artifacts,
        "monitoring": {
            "metrics_csv_path": artifacts.get("training_metrics_path"),
            "monitoring_summary_path": artifacts.get("monitoring_summary_path"),
            "run_status_path": artifacts.get("run_status_path"),
        },
    }


def run_pretraining_pipeline(config: PretrainConfig) -> dict[str, object]:
    config.validate()
    run_id, output_dir = create_run_directory(config.output_root, prefix=config.run_label)
    data_result = run_data_pipeline(config=config, output_dir=output_dir)
    config_path = output_dir / "pretrain_config.yaml"
    write_yaml(config_path, config.to_dict())
    model_result = run_model_pipeline(
        config=config,
        data_result=data_result,
        output_dir=output_dir,
        run_id=run_id,
    )

    artifacts = {
        "cleaned_input_path": str(data_result.artifacts.cleaned_input_path),
        "feature_schema_path": str(data_result.artifacts.feature_schema_path),
        "scaler_path": str(data_result.artifacts.scaler_path),
        "pretrain_config_path": str(config_path),
        "checkpoint_path": str(model_result.artifacts.checkpoint_path),
        "validation_reconstruction_loss_path": str(model_result.artifacts.validation_loss_history_path),
        "training_metrics_path": str(model_result.artifacts.training_metrics_path),
        "monitoring_summary_path": str(model_result.artifacts.monitoring_summary_path),
        "run_status_path": str(model_result.artifacts.run_status_path),
    }
    history_payload = model_result.history.to_dict()
    report = _build_report(
        config=config,
        data_result=data_result,
        output_dir=output_dir,
        run_id=run_id,
        history=history_payload,
        artifacts=artifacts,
    )

    report["holdout_scaled_shape"] = data_result.scaled_splits.split_shapes

    report_path = output_dir / "pretrain_report.json"
    artifacts["pretrain_report_path"] = str(report_path)
    write_json(report_path, report)

    return report
