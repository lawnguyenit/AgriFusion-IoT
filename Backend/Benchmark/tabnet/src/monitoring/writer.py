from __future__ import annotations

from pathlib import Path

from Backend.Benchmark.tabnet.src.monitoring.metrics import EpochMetrics
from Backend.Benchmark.tabnet.src.utils.artifacts import write_json


def write_training_metrics_csv(path: Path, rows: list[EpochMetrics]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "epoch",
        "train_loss",
        "validation_loss",
        "best_validation_loss",
        "learning_rate",
        "attention_entropy",
        "mask_density",
        "grad_norm",
        "epoch_seconds",
        "is_best_epoch",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(",".join(header) + "\n")
        for row in rows:
            payload = row.to_dict()
            handle.write(
                ",".join(
                    [
                        str(payload["epoch"]),
                        f"{payload['train_loss']:.10f}",
                        f"{payload['validation_loss']:.10f}",
                        f"{payload['best_validation_loss']:.10f}",
                        f"{payload['learning_rate']:.10f}",
                        f"{payload['attention_entropy']:.10f}",
                        f"{payload['mask_density']:.10f}",
                        f"{payload['grad_norm']:.10f}",
                        f"{payload['epoch_seconds']:.4f}",
                        "1" if payload["is_best_epoch"] else "0",
                    ]
                )
                + "\n"
            )


def write_monitoring_summary(path: Path, payload: dict[str, object]) -> None:
    write_json(path, payload)
