from __future__ import annotations

from pathlib import Path

import pandas as pd
import torch

from Backend.Benchmark.tabular_benchmark.src.config.settings import (
    DirectBenchmarkConfig,
    DirectBenchmarkTrainConfig,
)
from Backend.Benchmark.tabular_benchmark.src.data.training_io import (
    PreparedDirectExperimentBundle,
    load_build_manifest,
    load_prepared_direct_experiment,
)
from Backend.Benchmark.tabular_benchmark.src.pipeline.build_pipeline import run_build_pipeline
from Backend.Benchmark.models.ft_transformer_classifier import (
    FTTransformerClassifierConfig,
    train_ft_transformer_classifier,
)
from Backend.Benchmark.models.sklearn_suite import train_model_suite
from Backend.Benchmark.models.tabnet_classifier import (
    DirectTabNetClassifierConfig,
    train_direct_tabnet_classifier,
)
from Backend.Benchmark.shared.artifacts import create_run_directory, write_json, write_text
from Backend.Benchmark.shared.contracts import ModelResult
from Backend.Benchmark.shared.metrics import summarize_classification


def run_direct_pipeline(config: DirectBenchmarkConfig) -> dict[str, object]:
    config.validate()
    build_config = config.to_build_config()
    build_report = run_build_pipeline(build_config)
    effective_label_mode = build_report["label_mode"]
    train_config = config.to_train_config(Path(build_report["output_dir"]), effective_label_mode=effective_label_mode)
    return run_training_pipeline(train_config)


def run_training_pipeline(config: DirectBenchmarkTrainConfig) -> dict[str, object]:
    config.validate()
    run_id, output_dir = create_run_directory(config.output_root, prefix="direct_train")
    experiments_dir = output_dir / "experiments"
    output_dir.mkdir(parents=True, exist_ok=True)
    experiments_dir.mkdir(parents=True, exist_ok=True)

    build_manifest = load_build_manifest(config.build_run_dir)
    build_label_mode = str(build_manifest.get("label_mode", ""))
    if build_label_mode and build_label_mode != config.label_mode:
        raise ValueError(
            f"Build run label mode mismatch: build uses {build_label_mode}, train config uses {config.label_mode}."
        )

    experiment_reports: list[dict[str, object]] = []
    aggregate_rows: list[dict[str, object]] = []
    print(
        f"[tabular_benchmark:train] label_mode={config.label_mode} run_id={run_id} output_dir={output_dir}"
    )

    for experiment_index, experiment_name in enumerate(config.experiments, start=1):
        print(
            f"[tabular_benchmark:train] experiment {experiment_index}/{len(config.experiments)} -> {experiment_name}"
        )
        experiment_output_dir = experiments_dir / experiment_name
        experiment_output_dir.mkdir(parents=True, exist_ok=True)
        experiment_report, experiment_rows = _run_single_experiment(
            config=config,
            build_run_dir=config.build_run_dir,
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
        "label_mode": config.label_mode,
        "build_run_dir": str(config.build_run_dir),
        "output_dir": str(output_dir),
        "experiments": config.experiments,
        "active_models": config.model_names,
        "best_result": {
            "experiment_name": str(best_row["experiment_name"]),
            "model_name": str(best_row["model_name"]),
            "validation_macro_f1": float(best_row["validation_macro_f1"]),
            "validation_accuracy": float(best_row["validation_accuracy"]),
            "artifact_path": str(best_row["artifact_path"]),
        },
        "build_manifest_path": str(config.build_run_dir / "dataset_manifest.json"),
        "build_manifest": build_manifest,
        "experiment_reports": experiment_reports,
    }
    write_json(output_dir / "training_report.json", summary_report)
    write_json(output_dir / "run_config.json", config.to_dict())
    write_json(
        output_dir / "run_status.json",
        {
            "completed": True,
            "output_dir": str(output_dir),
            "label_mode": config.label_mode,
            "best_experiment_name": str(best_row["experiment_name"]),
            "best_model_name": str(best_row["model_name"]),
            "best_validation_macro_f1": float(best_row["validation_macro_f1"]),
        },
    )
    write_text(output_dir / "best_result.txt", f"{best_row['experiment_name']}::{best_row['model_name']}")
    print(
        f"[tabular_benchmark:train] best={best_row['experiment_name']}/{best_row['model_name']} "
        f"val_macro_f1={float(best_row['validation_macro_f1']):.4f}"
    )
    return {
        "benchmark_family": config.benchmark_family,
        "benchmark_version": config.benchmark_version,
        "label_mode": config.label_mode,
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
    config: DirectBenchmarkTrainConfig,
    build_run_dir: Path,
    experiment_name: str,
    output_dir: Path,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    models_dir = output_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    data_bundle = load_prepared_direct_experiment(build_run_dir, experiment_name)

    dataframe = data_bundle.dataframe.copy()
    dataframe.to_csv(output_dir / "direct_dataset.csv", index=False)
    write_json(
        output_dir / "feature_schema.json",
        {
            "experiment_name": experiment_name,
            "source_kind": data_bundle.source_kind,
            "feature_columns": data_bundle.feature_columns,
            "row_count": int(len(data_bundle.dataframe)),
            "split_counts": data_bundle.split_counts,
            "source_csvs": data_bundle.source_csvs,
            "class_names": data_bundle.class_names,
            "label_mode": data_bundle.label_mode,
        },
    )

    model_results: list[ModelResult] = []
    training_histories: dict[str, list[dict[str, float]] | None] = {}

    if "tabnet_classifier" in config.model_names:
        print(f"[tabular_benchmark:{config.label_mode}:{experiment_name}] training tabnet_classifier")
        tabnet_result = train_direct_tabnet_classifier(
            train_features=data_bundle.train_features,
            train_labels=data_bundle.train_labels,
            validation_features=data_bundle.validation_features,
            validation_labels=data_bundle.validation_labels,
            test_features=data_bundle.test_features,
            test_labels=data_bundle.test_labels,
            class_names=data_bundle.class_names,
            input_dim=data_bundle.train_features.shape[1],
            output_dim=len(data_bundle.class_names),
            config=DirectTabNetClassifierConfig(
                batch_size=config.tabnet_batch_size,
                virtual_batch_size=config.tabnet_virtual_batch_size,
                max_epochs=config.tabnet_max_epochs,
                patience=config.tabnet_patience,
                early_stopping_min_delta=config.tabnet_early_stopping_min_delta,
                learning_rate=config.tabnet_learning_rate,
                weight_decay=config.tabnet_weight_decay,
                max_grad_norm=config.tabnet_max_grad_norm,
                seed=config.seed,
                n_d=config.tabnet_n_d,
                n_a=config.tabnet_n_a,
                n_steps=config.tabnet_n_steps,
                gamma=config.tabnet_gamma,
                n_independent=config.tabnet_n_independent,
                n_shared=config.tabnet_n_shared,
                momentum=config.tabnet_momentum,
                mask_type=config.tabnet_mask_type,
            ),
            artifact_path=models_dir / "tabnet_classifier.pt",
            progress_label=f"direct:{config.label_mode}:{experiment_name}:tabnet",
        )
        validation_metrics, test_metrics = _evaluate_torch_model(
            model=tabnet_result.model,
            validation_features=data_bundle.validation_features,
            validation_labels=data_bundle.validation_labels,
            test_features=data_bundle.test_features,
            test_labels=data_bundle.test_labels,
            class_names=data_bundle.class_names,
        )
        model_results.append(
            ModelResult(
                model_name="tabnet_classifier",
                artifact_path=tabnet_result.artifact_path,
                metrics={
                    "validation": validation_metrics,
                    "test": test_metrics,
                    "history": tabnet_result.history,
                },
                notes=f"Best epoch {tabnet_result.best_epoch}",
            )
        )
        training_histories["tabnet_classifier"] = tabnet_result.history

    if "ft_transformer_classifier" in config.model_names:
        print(f"[tabular_benchmark:{config.label_mode}:{experiment_name}] training ft_transformer_classifier")
        ft_result = train_ft_transformer_classifier(
            train_features=data_bundle.train_features,
            train_labels=data_bundle.train_labels,
            validation_features=data_bundle.validation_features,
            validation_labels=data_bundle.validation_labels,
            test_features=data_bundle.test_features,
            test_labels=data_bundle.test_labels,
            class_names=data_bundle.class_names,
            input_dim=data_bundle.train_features.shape[1],
            output_dim=len(data_bundle.class_names),
            config=FTTransformerClassifierConfig(
                batch_size=config.ft_batch_size,
                max_epochs=config.ft_max_epochs,
                patience=config.ft_patience,
                learning_rate=config.ft_learning_rate,
                weight_decay=config.ft_weight_decay,
                max_grad_norm=config.ft_max_grad_norm,
                seed=config.seed,
                token_dim=config.ft_token_dim,
                model_dim=config.ft_model_dim,
                num_heads=config.ft_num_heads,
                num_layers=config.ft_num_layers,
                ffn_multiplier=config.ft_ffn_multiplier,
                dropout=config.ft_dropout,
                attention_dropout=config.ft_attention_dropout,
                residual_dropout=config.ft_residual_dropout,
                classifier_hidden_dim=config.ft_classifier_hidden_dim,
            ),
            artifact_path=models_dir / "ft_transformer_classifier.pt",
            progress_label=f"direct:{config.label_mode}:{experiment_name}:ft",
        )
        validation_metrics, test_metrics = _evaluate_torch_model(
            model=ft_result.model,
            validation_features=data_bundle.validation_features,
            validation_labels=data_bundle.validation_labels,
            test_features=data_bundle.test_features,
            test_labels=data_bundle.test_labels,
            class_names=data_bundle.class_names,
        )
        model_results.append(
            ModelResult(
                model_name="ft_transformer_classifier",
                artifact_path=ft_result.artifact_path,
                metrics={
                    "validation": validation_metrics,
                    "test": test_metrics,
                    "history": ft_result.history,
                },
                notes=f"Best epoch {ft_result.best_epoch}",
            )
        )
        training_histories["ft_transformer_classifier"] = ft_result.history

    sklearn_results = train_model_suite(
        train_features=data_bundle.train_features,
        train_labels=data_bundle.train_labels,
        validation_features=data_bundle.validation_features,
        validation_labels=data_bundle.validation_labels,
        test_features=data_bundle.test_features,
        test_labels=data_bundle.test_labels,
        class_names=data_bundle.class_names,
        feature_names=data_bundle.feature_columns,
        output_dir=output_dir,
        seed=config.seed,
        model_names=[name for name in config.model_names if name == "xgboost"],
        progress_prefix=f"direct:{config.label_mode}:{experiment_name}:sklearn",
    )
    for result in sklearn_results:
        model_results.append(
            ModelResult(
                model_name=result.model_name,
                artifact_path=result.artifact_path,
                metrics=result.metrics,
                available=result.available,
                notes=result.notes,
            )
        )

    metric_rows: list[dict[str, object]] = []
    for result in model_results:
        validation_metrics = result.metrics.get("validation", {})
        test_metrics = result.metrics.get("test", {})
        metric_rows.append(
            {
                "experiment_name": experiment_name,
                "source_kind": data_bundle.source_kind,
                "label_mode": config.label_mode,
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
            }
        )

    metrics_frame = pd.DataFrame(metric_rows).sort_values(
        by=["validation_macro_f1", "validation_accuracy"],
        ascending=False,
    )
    metrics_path = output_dir / "model_metrics.csv"
    metrics_frame.to_csv(metrics_path, index=False)
    available_results = [result for result in model_results if result.available]
    best_result = max(
        available_results,
        key=lambda result: (
            float(result.metrics.get("validation", {}).get("macro_f1", -1.0)),
            float(result.metrics.get("validation", {}).get("accuracy", -1.0)),
        ),
    )

    training_report = {
        "benchmark_family": config.benchmark_family,
        "benchmark_version": config.benchmark_version,
        "experiment_name": experiment_name,
        "label_mode": config.label_mode,
        "source_kind": data_bundle.source_kind,
        "output_dir": str(output_dir),
        "input_build_run_dir": str(build_run_dir),
        "aligned_rows": int(len(data_bundle.dataframe)),
        "split_counts": data_bundle.split_counts,
        "class_names": data_bundle.class_names,
        "selected_model": {
            "model_name": best_result.model_name,
            "artifact_path": str(best_result.artifact_path),
            "validation_macro_f1": float(best_result.metrics.get("validation", {}).get("macro_f1", 0.0)),
        },
        "models": metric_rows,
        "training_histories": training_histories,
        "feature_columns": data_bundle.feature_columns,
        "selected_label_counts_full": {
            name: int((data_bundle.dataframe["selected_label_name"] == name).sum())
            for name in data_bundle.class_names
        },
    }
    report_path = output_dir / "training_report.json"
    write_json(report_path, training_report)
    write_json(
        output_dir / "label_policy.json",
        {
            "selected_mode": config.label_mode,
            "class_names": data_bundle.class_names,
            "class_counts_train": {
                name: int((data_bundle.dataframe.loc[data_bundle.dataframe["split"] == "train", "selected_label_name"] == name).sum())
                for name in data_bundle.class_names
            },
            "diagnostics": {
                "build_run_dir": str(build_run_dir),
                "support_gate_enforced": False,
            },
        },
    )
    write_text(output_dir / "best_model.txt", best_result.model_name)
    write_json(
        output_dir / "run_status.json",
        {
            "completed": True,
            "output_dir": str(output_dir),
            "label_mode": config.label_mode,
            "best_model_name": best_result.model_name,
            "best_validation_macro_f1": float(best_result.metrics.get("validation", {}).get("macro_f1", 0.0)),
            "source_kind": data_bundle.source_kind,
        },
    )

    experiment_report = {
        "experiment_name": experiment_name,
        "source_kind": data_bundle.source_kind,
        "label_mode": config.label_mode,
        "best_model_name": best_result.model_name,
        "best_validation_macro_f1": float(best_result.metrics.get("validation", {}).get("macro_f1", 0.0)),
        "artifact_path": str(best_result.artifact_path),
        "report_path": str(report_path),
        "metrics_path": str(metrics_path),
    }
    return experiment_report, metric_rows


def _evaluate_torch_model(
    *,
    model: torch.nn.Module,
    validation_features: object,
    validation_labels: object,
    test_features: object,
    test_labels: object,
    class_names: list[str],
) -> tuple[dict[str, object], dict[str, object]]:
    device = next(model.parameters()).device
    with torch.no_grad():
        validation_output = model(torch.tensor(validation_features, dtype=torch.float32, device=device))
        test_output = model(torch.tensor(test_features, dtype=torch.float32, device=device))
    validation_logits = validation_output[0] if isinstance(validation_output, tuple) else validation_output
    test_logits = test_output[0] if isinstance(test_output, tuple) else test_output
    validation_predictions = validation_logits.argmax(dim=1).detach().cpu().numpy()
    test_predictions = test_logits.argmax(dim=1).detach().cpu().numpy()
    return (
        summarize_classification(validation_labels, validation_predictions, class_names),
        summarize_classification(test_labels, test_predictions, class_names),
    )
