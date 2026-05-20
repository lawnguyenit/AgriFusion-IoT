from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import StandardScaler

from Backend.Benchmark.pretrain_supervised.pretrain.src.utils.artifacts import create_run_directory
from Backend.Benchmark.pretrain_supervised.v0.src.config.settings import V0Config
from Backend.Benchmark.pretrain_supervised.v0.src.data.embeddings import build_experiment_embedding_bundle
from Backend.Benchmark.pretrain_supervised.v1.src.data.contracts import ModelResult
from Backend.Benchmark.pretrain_supervised.v1.src.data.labels import build_label_frame, select_label_policy
from Backend.Benchmark.pretrain_supervised.v1.src.model.metrics import summarize_classification
from Backend.Benchmark.pretrain_supervised.v1.src.model.probe import train_torch_probe
from Backend.Benchmark.pretrain_supervised.v1.src.model.sklearn_models import train_model_suite
from Backend.Benchmark.pretrain_supervised.v1.src.utils.artifacts import write_json, write_text


def run_v0_pipeline(config: V0Config) -> dict[str, object]:
    config.validate()
    run_id, output_dir = create_run_directory(config.output_root, prefix=config.benchmark_version)
    experiments_dir = output_dir / "experiments"
    output_dir.mkdir(parents=True, exist_ok=True)
    experiments_dir.mkdir(parents=True, exist_ok=True)

    experiment_reports: list[dict[str, object]] = []
    aggregate_rows: list[dict[str, object]] = []

    for experiment_name in config.experiments:
        experiment_output_dir = experiments_dir / experiment_name
        experiment_output_dir.mkdir(parents=True, exist_ok=True)
        experiment_report, experiment_rows = _run_single_experiment(
            config=config,
            experiment_name=experiment_name,
            output_dir=experiment_output_dir,
        )
        experiment_reports.append(experiment_report)
        aggregate_rows.extend(experiment_rows)

    aggregate_frame = pd.DataFrame(aggregate_rows).sort_values(
        by=["validation_macro_f1", "validation_accuracy"],
        ascending=False,
    )
    aggregate_metrics_path = output_dir / "aggregate_model_metrics.csv"
    aggregate_frame.to_csv(aggregate_metrics_path, index=False)

    best_row = aggregate_frame.iloc[0].to_dict()
    summary_report = {
        "benchmark_family": config.benchmark_family,
        "benchmark_version": config.benchmark_version,
        "run_id": run_id,
        "output_dir": str(output_dir),
        "experiments": config.experiments,
        "best_result": {
            "experiment_name": str(best_row["experiment_name"]),
            "model_name": str(best_row["model_name"]),
            "validation_macro_f1": float(best_row["validation_macro_f1"]),
            "validation_accuracy": float(best_row["validation_accuracy"]),
            "artifact_path": str(best_row["artifact_path"]),
        },
        "experiment_reports": experiment_reports,
    }

    write_json(output_dir / "training_report.json", summary_report)
    write_json(output_dir / "run_config.json", config.to_dict())
    write_json(
        output_dir / "run_status.json",
        {
            "completed": True,
            "output_dir": str(output_dir),
            "best_experiment_name": str(best_row["experiment_name"]),
            "best_model_name": str(best_row["model_name"]),
            "best_validation_macro_f1": float(best_row["validation_macro_f1"]),
        },
    )
    write_text(output_dir / "best_result.txt", f"{best_row['experiment_name']}::{best_row['model_name']}")

    return {
        "benchmark_family": config.benchmark_family,
        "benchmark_version": config.benchmark_version,
        "experiments": config.experiments,
        "best_result": {
            "experiment_name": str(best_row["experiment_name"]),
            "model_name": str(best_row["model_name"]),
            "validation_macro_f1": float(best_row["validation_macro_f1"]),
        },
        "output_dir": str(output_dir),
        "report_path": str(output_dir / "training_report.json"),
        "aggregate_metrics_path": str(aggregate_metrics_path),
    }


def _run_single_experiment(
    *,
    config: V0Config,
    experiment_name: str,
    output_dir: Path,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    models_dir = output_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    embedding_bundle = build_experiment_embedding_bundle(config, experiment_name=experiment_name)
    dataframe = build_label_frame(embedding_bundle.dataframe)
    label_policy = select_label_policy(
        dataframe,
        requested_mode=config.label_mode,
        min_class_support=config.min_class_support,
        min_class_ratio=config.min_class_ratio,
    )

    dataframe["selected_label_name"] = dataframe[label_policy.label_column]
    dataframe["selected_label_id"] = dataframe[label_policy.label_id_column]
    dataframe["embedding_split"] = dataframe["split"]

    embedding_columns = list(embedding_bundle.embedding_columns)
    features = dataframe[embedding_columns].to_numpy(dtype=np.float32)
    labels = dataframe["selected_label_id"].to_numpy(dtype=np.int64)

    train_features = features[embedding_bundle.split_slices["train"]]
    validation_features = features[embedding_bundle.split_slices["validation"]]
    test_features = features[embedding_bundle.split_slices["test"]]
    train_labels = labels[embedding_bundle.split_slices["train"]]
    validation_labels = labels[embedding_bundle.split_slices["validation"]]
    test_labels = labels[embedding_bundle.split_slices["test"]]

    embedding_scaler = StandardScaler()
    train_scaled = embedding_scaler.fit_transform(train_features)
    validation_scaled = embedding_scaler.transform(validation_features)
    test_scaled = embedding_scaler.transform(test_features)
    scaled_all = embedding_scaler.transform(features)

    dataframe_with_scaled = dataframe.copy()
    for index, column in enumerate(embedding_columns):
        dataframe_with_scaled[f"scaled_{column}"] = scaled_all[:, index]

    embedding_dataset_path = output_dir / "embedding_dataset.csv"
    dataframe_with_scaled.to_csv(embedding_dataset_path, index=False)
    embedding_scaler_path = output_dir / "embedding_scaler.pkl"
    joblib.dump(embedding_scaler, embedding_scaler_path)

    torch_probe_result = train_torch_probe(
        train_features=train_scaled,
        train_labels=train_labels,
        validation_features=validation_scaled,
        validation_labels=validation_labels,
        class_names=label_policy.class_names,
        input_dim=train_scaled.shape[1],
        output_dim=len(label_policy.class_names),
        hidden_dim=config.torch_hidden_dim,
        dropout=config.torch_dropout,
        batch_size=config.batch_size,
        learning_rate=config.learning_rate,
        weight_decay=config.weight_decay,
        max_epochs=config.max_epochs,
        patience=config.patience,
        max_grad_norm=config.max_grad_norm,
        seed=config.seed,
        artifact_path=models_dir / "torch_probe.pt",
    )

    sklearn_results = train_model_suite(
        train_features=train_scaled,
        train_labels=train_labels,
        validation_features=validation_scaled,
        validation_labels=validation_labels,
        test_features=test_scaled,
        test_labels=test_labels,
        class_names=label_policy.class_names,
        feature_names=embedding_columns,
        output_dir=output_dir,
        seed=config.seed,
        model_names=config.model_names,
    )

    all_results: list[ModelResult] = []
    probe_device = next(torch_probe_result.model.parameters()).device
    with torch.no_grad():
        torch_validation_predictions = (
            torch_probe_result.model(torch.tensor(validation_scaled, dtype=torch.float32, device=probe_device))
            .argmax(dim=1)
            .cpu()
            .numpy()
        )
        torch_test_predictions = (
            torch_probe_result.model(torch.tensor(test_scaled, dtype=torch.float32, device=probe_device))
            .argmax(dim=1)
            .cpu()
            .numpy()
        )
    torch_validation_metrics = summarize_classification(validation_labels, torch_validation_predictions, label_policy.class_names)
    torch_test_metrics = summarize_classification(test_labels, torch_test_predictions, label_policy.class_names)
    all_results.append(
        ModelResult(
            model_name="torch_probe",
            artifact_path=torch_probe_result.artifact_path,
            metrics={"validation": torch_validation_metrics, "test": torch_test_metrics, "history": torch_probe_result.history},
            notes=f"Best epoch {torch_probe_result.best_epoch}",
        )
    )

    for result in sklearn_results:
        all_results.append(
            ModelResult(
                model_name=result.model_name,
                artifact_path=result.artifact_path,
                metrics=result.metrics,
                available=result.available,
                notes=result.notes,
            )
        )

    model_rows: list[dict[str, object]] = []
    for result in all_results:
        validation_metrics = result.metrics.get("validation", {})
        test_metrics = result.metrics.get("test", {})
        model_rows.append(
            {
                "experiment_name": experiment_name,
                "source_kind": embedding_bundle.source_kind,
                "model_name": result.model_name,
                "available": bool(result.available),
                "notes": result.notes,
                "validation_accuracy": float(validation_metrics.get("accuracy", float("nan"))),
                "validation_balanced_accuracy": float(validation_metrics.get("balanced_accuracy", float("nan"))),
                "validation_macro_f1": float(validation_metrics.get("macro_f1", float("nan"))),
                "validation_weighted_f1": float(validation_metrics.get("weighted_f1", float("nan"))),
                "test_accuracy": float(test_metrics.get("accuracy", float("nan"))),
                "test_balanced_accuracy": float(test_metrics.get("balanced_accuracy", float("nan"))),
                "test_macro_f1": float(test_metrics.get("macro_f1", float("nan"))),
                "test_weighted_f1": float(test_metrics.get("weighted_f1", float("nan"))),
                "artifact_path": str(result.artifact_path),
                "checkpoint_path": str(embedding_bundle.checkpoint_path),
            }
        )

    metrics_frame = pd.DataFrame(model_rows).sort_values(
        by=["validation_macro_f1", "validation_accuracy"], ascending=False
    )
    metrics_path = output_dir / "model_metrics.csv"
    metrics_frame.to_csv(metrics_path, index=False)

    available_results = [result for result in all_results if result.available]
    best_result = max(
        available_results,
        key=lambda result: (
            float(result.metrics.get("validation", {}).get("macro_f1", -1.0)),
            float(result.metrics.get("validation", {}).get("accuracy", -1.0)),
        ),
    )
    best_validation_macro_f1 = float(best_result.metrics.get("validation", {}).get("macro_f1", 0.0))

    label_policy_path = output_dir / "label_policy.json"
    write_json(
        label_policy_path,
        {
            "selected_mode": label_policy.label_mode,
            "label_column": label_policy.label_column,
            "label_id_column": label_policy.label_id_column,
            "class_names": label_policy.class_names,
            "class_to_id": label_policy.class_to_id,
            "class_counts_train": label_policy.class_counts,
            "diagnostics": label_policy.diagnostics,
        },
    )

    training_report = {
        "benchmark_family": config.benchmark_family,
        "benchmark_version": config.benchmark_version,
        "experiment_name": experiment_name,
        "source_kind": embedding_bundle.source_kind,
        "output_dir": str(output_dir),
        "pretrain_checkpoint": str(embedding_bundle.checkpoint_path),
        "pretrain_checkpoint_config": embedding_bundle.checkpoint_config,
        "embedding_dim": embedding_bundle.embedding_dim,
        "input_rows": int(len(dataframe)),
        "split_counts": embedding_bundle.split_counts,
        "split_policy": embedding_bundle.split_manifest,
        "label_merge_report": embedding_bundle.label_merge_report,
        "label_policy": {
            "selected_mode": label_policy.label_mode,
            "label_column": label_policy.label_column,
            "class_names": label_policy.class_names,
            "class_counts_train": label_policy.class_counts,
            "diagnostics": label_policy.diagnostics,
        },
        "selected_model": {
            "model_name": best_result.model_name,
            "artifact_path": str(best_result.artifact_path),
            "validation_macro_f1": best_validation_macro_f1,
        },
        "models": model_rows,
        "torch_probe_history": torch_probe_result.history,
        "embedding_columns": embedding_columns,
        "selected_label_counts_full": {
            name: int((dataframe["selected_label_name"] == name).sum()) for name in label_policy.class_names
        },
    }

    report_path = output_dir / "training_report.json"
    write_json(report_path, training_report)
    write_text(output_dir / "best_model.txt", best_result.model_name)
    write_json(
        output_dir / "run_status.json",
        {
            "completed": True,
            "experiment_name": experiment_name,
            "output_dir": str(output_dir),
            "best_model_name": best_result.model_name,
            "best_validation_macro_f1": best_validation_macro_f1,
            "pretrain_checkpoint": str(embedding_bundle.checkpoint_path),
        },
    )

    return training_report, model_rows

