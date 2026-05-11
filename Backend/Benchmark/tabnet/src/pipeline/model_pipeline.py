from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from Backend.Benchmark.tabnet.src.config.settings import PretrainConfig
from Backend.Benchmark.tabnet.src.data.contracts import DataPipelineResult
from Backend.Benchmark.tabnet.src.model.tabnet_pretrainer import (
    TabNetMaskedPretrainer,
    TrainingHistory,
)
from Backend.Benchmark.tabnet.src.monitoring.writer import (
    write_monitoring_summary,
    write_training_metrics_csv,
)
from Backend.Benchmark.tabnet.src.utils.artifacts import write_json


@dataclass
class ModelPipelineArtifacts:
    checkpoint_path: Path
    validation_loss_history_path: Path
    training_metrics_path: Path
    monitoring_summary_path: Path
    run_status_path: Path


@dataclass
class ModelPipelineResult:
    history: TrainingHistory
    artifacts: ModelPipelineArtifacts


def run_model_pipeline(
    config: PretrainConfig,
    data_result: DataPipelineResult,
    output_dir: Path,
    run_id: str,
) -> ModelPipelineResult:
    scaled_splits = data_result.scaled_splits
    prepared_dataset = data_result.prepared_dataset

    pretrainer = TabNetMaskedPretrainer(
        config=config,
        input_dim=len(prepared_dataset.feature_columns),
    )
    history = pretrainer.fit(
        train_features=scaled_splits.train_features,
        validation_features=scaled_splits.validation_features,
    )

    checkpoint_path = output_dir / "tabnet_pretrainer.pt"
    validation_loss_history_path = output_dir / "validation_loss_history.json"
    training_metrics_path = output_dir / "training_metrics.csv"
    monitoring_summary_path = output_dir / "monitoring_summary.json"
    run_status_path = output_dir / "run_status.json"

    pretrainer.save_checkpoint(
        checkpoint_path=str(checkpoint_path),
        metadata={
            "run_id": run_id,
            "feature_columns": prepared_dataset.feature_columns,
            "scaled_row_counts": scaled_splits.split_shapes,
        },
    )
    write_json(validation_loss_history_path, {"validation_loss": history.validation_loss})
    write_training_metrics_csv(training_metrics_path, pretrainer.epoch_metrics)
    write_monitoring_summary(
        monitoring_summary_path,
        {
            "run_id": run_id,
            "status": "completed",
            "epochs_ran": len(history.validation_loss),
            "best_epoch": history.best_epoch,
            "best_validation_loss": history.best_validation_loss,
            "stopped_early": history.stopped_early,
            "feature_count": len(prepared_dataset.feature_columns),
            "monitoring_fields": [
                "train_loss",
                "validation_loss",
                "best_validation_loss",
                "learning_rate",
                "attention_entropy",
                "mask_density",
                "grad_norm",
                "epoch_seconds",
            ],
        },
    )
    write_json(
        run_status_path,
        {
            "run_id": run_id,
            "status": "completed",
            "checkpoint_path": str(checkpoint_path),
            "metrics_path": str(training_metrics_path),
            "monitoring_summary_path": str(monitoring_summary_path),
        },
    )

    return ModelPipelineResult(
        history=history,
        artifacts=ModelPipelineArtifacts(
            checkpoint_path=checkpoint_path,
            validation_loss_history_path=validation_loss_history_path,
            training_metrics_path=training_metrics_path,
            monitoring_summary_path=monitoring_summary_path,
            run_status_path=run_status_path,
        ),
    )
