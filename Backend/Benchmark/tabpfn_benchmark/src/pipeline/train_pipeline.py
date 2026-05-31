from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

from Backend.Benchmark.pretrain_supervised.pretrain.src.utils.artifacts import create_run_directory
from Backend.Benchmark.pretrain_supervised.v1.src.data.contracts import ModelResult
from Backend.Benchmark.pretrain_supervised.v1.src.data.labels import select_label_policy
from Backend.Benchmark.pretrain_supervised.v1.src.model.sklearn_models import train_model_suite
from Backend.Benchmark.pretrain_supervised.v1.src.utils.artifacts import write_json, write_text
from Backend.Benchmark.tabpfn_benchmark.src.config.settings import TabPFNBenchmarkConfig
from Backend.Benchmark.tabpfn_benchmark.src.data.raw_data import build_tabpfn_data_bundle
from Backend.Benchmark.tabpfn_benchmark.src.model.tabpfn_classifier import (
    TabPFNClassifierConfig,
    train_tabpfn_classifier,
)
from Backend.Benchmark.tabpfn_benchmark.src.scientific_artifacts import write_ft_scientific_artifacts


def run_tabpfn_pipeline(config: TabPFNBenchmarkConfig) -> dict[str, object]:
    config.validate()
    run_id, output_dir = create_run_directory(config.output_root, prefix=config.benchmark_version)
    experiments_dir = output_dir / "experiments"
    output_dir.mkdir(parents=True, exist_ok=True)
    experiments_dir.mkdir(parents=True, exist_ok=True)

    experiment_reports: list[dict[str, object]] = []
    aggregate_rows: list[dict[str, object]] = []
    print(f"[tabpfn_benchmark] run_id={run_id} output_dir={output_dir}")

    for experiment_index, experiment_name in enumerate(config.experiments, start=1):
        print(f"[tabpfn_benchmark] experiment {experiment_index}/{len(config.experiments)} -> {experiment_name}")
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
    print(
        f"[tabpfn_benchmark] best={best_row['experiment_name']}/{best_row['model_name']} "
        f"val_macro_f1={float(best_row['validation_macro_f1']):.4f}"
    )

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
    config: TabPFNBenchmarkConfig,
    experiment_name: str,
    output_dir: Path,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    models_dir = output_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    data_bundle = build_tabpfn_data_bundle(config, experiment_name=experiment_name)
    dataframe = data_bundle.dataframe.copy()
    label_policy = select_label_policy(
        dataframe,
        requested_mode=config.label_mode,
        min_class_support=config.min_class_support,
        min_class_ratio=config.min_class_ratio,
    )

    dataframe["selected_label_name"] = dataframe[label_policy.label_column]
    dataframe["selected_label_id"] = dataframe[label_policy.label_id_column]
    dataframe["direct_split"] = dataframe["split"]

    feature_columns = list(data_bundle.feature_columns)
    features = dataframe[feature_columns].to_numpy(dtype=np.float32)
    labels = dataframe["selected_label_id"].to_numpy(dtype=np.int64)

    train_features = features[data_bundle.split_slices["train"]]
    validation_features = features[data_bundle.split_slices["validation"]]
    test_features = features[data_bundle.split_slices["test"]]
    train_frame = dataframe.iloc[data_bundle.split_slices["train"]].reset_index(drop=True).copy()
    validation_frame = dataframe.iloc[data_bundle.split_slices["validation"]].reset_index(drop=True).copy()
    test_frame = dataframe.iloc[data_bundle.split_slices["test"]].reset_index(drop=True).copy()
    train_labels = labels[data_bundle.split_slices["train"]]
    validation_labels = labels[data_bundle.split_slices["validation"]]
    test_labels = labels[data_bundle.split_slices["test"]]

    imputer = SimpleImputer(strategy="median")
    train_imputed = imputer.fit_transform(train_features)
    validation_imputed = imputer.transform(validation_features)
    test_imputed = imputer.transform(test_features)
    all_imputed = imputer.transform(features)

    scaler = StandardScaler()
    train_scaled = scaler.fit_transform(train_imputed)
    validation_scaled = scaler.transform(validation_imputed)
    test_scaled = scaler.transform(test_imputed)
    scaled_all = scaler.transform(all_imputed)

    dataframe_with_scaled = dataframe.copy()
    for index, column in enumerate(feature_columns):
        dataframe_with_scaled[f"scaled_{column}"] = scaled_all[:, index]

    direct_dataset_path = output_dir / "direct_dataset.csv"
    dataframe_with_scaled.to_csv(direct_dataset_path, index=False)
    joblib.dump(scaler, output_dir / "scaler.pkl")
    joblib.dump(imputer, output_dir / "imputer.pkl")

    write_json(
        output_dir / "feature_schema.json",
        {
            "experiment_name": experiment_name,
            "feature_columns": feature_columns,
            "row_count": data_bundle.row_count,
            "split_counts": data_bundle.split_counts,
            "source_csvs": [str(path) for path in data_bundle.source_csvs],
        },
    )

    model_results: list[ModelResult] = []
    scientific_artifacts_by_model: dict[str, dict[str, object]] = {}
    scientific_summaries_by_model: dict[str, dict[str, dict[str, object]]] = {}

    if "tabpfn_classifier" in config.model_names:
        print(f"[tabpfn:{experiment_name}] training tabpfn_classifier")
        tabpfn_result = train_tabpfn_classifier(
            train_features=train_scaled,
            train_labels=train_labels,
            validation_features=validation_scaled,
            validation_labels=validation_labels,
            test_features=test_scaled,
            test_labels=test_labels,
            class_names=label_policy.class_names,
            feature_names=feature_columns,
            config=TabPFNClassifierConfig(
                model_path=config.tabpfn_model_path,
                device=config.tabpfn_device,
                fit_mode=config.tabpfn_fit_mode,
                inference_config=config.tabpfn_inference_config,
                seed=config.seed,
            ),
            artifact_path=models_dir / "tabpfn_classifier.joblib",
            progress_label=f"tabpfn:{experiment_name}:model",
        )
        if tabpfn_result.available:
            tabpfn_scientific_artifacts = write_ft_scientific_artifacts(
                output_dir=output_dir,
                experiment_name=experiment_name,
                model_name="tabpfn_classifier",
                class_names=label_policy.class_names,
                history=[],
                best_epoch=0,
                training_config=tabpfn_result.training_metadata.get("training_config", {}),
                training_metadata=tabpfn_result.training_metadata,
                split_payloads={
                    "train": {
                        "metadata_frame": train_frame,
                        **tabpfn_result.scientific_split_payloads["train"],
                    },
                    "validation": {
                        "metadata_frame": validation_frame,
                        **tabpfn_result.scientific_split_payloads["validation"],
                    },
                    "test": {
                        "metadata_frame": test_frame,
                        **tabpfn_result.scientific_split_payloads["test"],
                    },
                },
            )
            scientific_artifacts_by_model["tabpfn_classifier"] = tabpfn_scientific_artifacts
            scientific_summaries_by_model["tabpfn_classifier"] = tabpfn_scientific_artifacts["split_summaries"]
            notes = (
                f"{tabpfn_result.notes} "
                f"scientific_artifacts={tabpfn_scientific_artifacts['manifest_path']}"
            ).strip()
        else:
            notes = tabpfn_result.notes
        model_results.append(
            ModelResult(
                model_name="tabpfn_classifier",
                artifact_path=tabpfn_result.artifact_path,
                metrics=tabpfn_result.metrics,
                available=tabpfn_result.available,
                notes=notes,
            )
        )

    sklearn_model_names = [name for name in config.model_names if name != "tabpfn_classifier"]
    sklearn_results = train_model_suite(
        train_features=train_scaled,
        train_labels=train_labels,
        validation_features=validation_scaled,
        validation_labels=validation_labels,
        test_features=test_scaled,
        test_labels=test_labels,
        class_names=label_policy.class_names,
        feature_names=feature_columns,
        output_dir=output_dir,
        seed=config.seed,
        model_names=sklearn_model_names,
        progress_prefix=f"tabpfn:{experiment_name}:sklearn",
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
        scientific_summary = scientific_summaries_by_model.get(result.model_name, {})
        validation_scientific = scientific_summary.get("validation", {})
        test_scientific = scientific_summary.get("test", {})
        metric_rows.append(
            {
                "experiment_name": experiment_name,
                "source_kind": data_bundle.source_kind,
                "model_name": result.model_name,
                "available": bool(result.available),
                "notes": result.notes,
                "validation_accuracy": float(validation_metrics.get("accuracy", float("nan"))),
                "validation_balanced_accuracy": float(validation_metrics.get("balanced_accuracy", float("nan"))),
                "validation_macro_f1": float(validation_metrics.get("macro_f1", float("nan"))),
                "validation_weighted_f1": float(validation_metrics.get("weighted_f1", float("nan"))),
                "validation_log_loss": _to_float_or_nan(validation_scientific.get("log_loss")),
                "validation_ovr_macro_roc_auc": _to_float_or_nan(validation_scientific.get("ovr_macro_roc_auc")),
                "validation_ovr_macro_average_precision": _to_float_or_nan(
                    validation_scientific.get("ovr_macro_average_precision")
                ),
                "validation_ovr_macro_brier": _to_float_or_nan(validation_scientific.get("ovr_macro_brier")),
                "validation_top1_ece_15bins": _to_float_or_nan(validation_scientific.get("top1_ece_15bins")),
                "test_accuracy": float(test_metrics.get("accuracy", float("nan"))),
                "test_balanced_accuracy": float(test_metrics.get("balanced_accuracy", float("nan"))),
                "test_macro_f1": float(test_metrics.get("macro_f1", float("nan"))),
                "test_weighted_f1": float(test_metrics.get("weighted_f1", float("nan"))),
                "test_log_loss": _to_float_or_nan(test_scientific.get("log_loss")),
                "test_ovr_macro_roc_auc": _to_float_or_nan(test_scientific.get("ovr_macro_roc_auc")),
                "test_ovr_macro_average_precision": _to_float_or_nan(
                    test_scientific.get("ovr_macro_average_precision")
                ),
                "test_ovr_macro_brier": _to_float_or_nan(test_scientific.get("ovr_macro_brier")),
                "test_top1_ece_15bins": _to_float_or_nan(test_scientific.get("top1_ece_15bins")),
                "artifact_path": str(result.artifact_path),
                "scientific_manifest_path": str(
                    scientific_artifacts_by_model.get(result.model_name, {}).get("manifest_path", "")
                ),
            }
        )

    metrics_frame = pd.DataFrame(metric_rows).sort_values(by=["validation_macro_f1", "validation_accuracy"], ascending=False)
    metrics_frame.to_csv(output_dir / "experiment_model_metrics.csv", index=False)

    experiment_report = {
        "experiment_name": experiment_name,
        "source_kind": data_bundle.source_kind,
        "row_count": data_bundle.row_count,
        "feature_count": len(feature_columns),
        "feature_columns": feature_columns,
        "split_counts": data_bundle.split_counts,
        "split_manifest": data_bundle.split_manifest,
        "label_policy": {
            "label_column": label_policy.label_column,
            "label_id_column": label_policy.label_id_column,
            "class_names": label_policy.class_names,
        },
        "model_results": [
            {
                "model_name": result.model_name,
                "artifact_path": str(result.artifact_path),
                "available": bool(result.available),
                "notes": result.notes,
                "metrics": result.metrics,
                "scientific_artifacts": scientific_artifacts_by_model.get(result.model_name),
            }
            for result in model_results
        ],
    }
    write_json(output_dir / "experiment_report.json", experiment_report)
    return experiment_report, metric_rows


def _to_float_or_nan(value: object) -> float:
    if value is None:
        return float("nan")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")
