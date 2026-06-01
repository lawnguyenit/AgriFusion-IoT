from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd

from Backend.Benchmark.context_classifier.src.config.train_settings import ContextTrainConfig
from Backend.Benchmark.context_classifier.src.data.training_io import (
    load_build_manifest,
    load_sequence_bundle,
    load_tabular_bundle,
)
from Backend.Benchmark.context_classifier.src.model.lstm_classifier import LstmClassifierConfig, train_lstm_classifier
from Backend.Benchmark.context_classifier.src.pipeline.scientific_artifact_pipeline import (
    backfill_training_run_scientific_artifacts,
)
from Backend.Benchmark.direct_benchmark.src.model.tabnet_classifier import (
    DirectTabNetClassifierConfig,
    train_direct_tabnet_classifier,
)
from Backend.Benchmark.ft_transformer_benchmark.src.model.ft_transformer_classifier import (
    FTTransformerClassifierConfig,
    train_ft_transformer_classifier,
)
from Backend.Benchmark.pretrain_supervised.pretrain.src.utils.artifacts import create_run_directory, write_json
from Backend.Benchmark.pretrain_supervised.v1.src.model.sklearn_models import train_model_suite
from Backend.Benchmark.tabpfn_benchmark.src.model.tabpfn_classifier import (
    TabPFNClassifierConfig,
    train_tabpfn_classifier,
)


def _flatten_model_metrics(
    *,
    experiment_name: str,
    model_name: str,
    artifact_path: Path,
    validation_metrics: dict[str, object],
    test_metrics: dict[str, object],
    available: bool = True,
    notes: str = "",
) -> dict[str, object]:
    if not available:
        return {
            "experiment_name": experiment_name,
            "model_name": model_name,
            "available": False,
            "artifact_path": str(artifact_path),
            "validation_accuracy": 0.0,
            "validation_balanced_accuracy": 0.0,
            "validation_macro_f1": 0.0,
            "test_accuracy": 0.0,
            "test_balanced_accuracy": 0.0,
            "test_macro_f1": 0.0,
            "notes": notes,
        }
    return {
        "experiment_name": experiment_name,
        "model_name": model_name,
        "available": True,
        "artifact_path": str(artifact_path),
        "validation_accuracy": float(validation_metrics["accuracy"]),
        "validation_balanced_accuracy": float(validation_metrics["balanced_accuracy"]),
        "validation_macro_f1": float(validation_metrics["macro_f1"]),
        "test_accuracy": float(test_metrics["accuracy"]),
        "test_balanced_accuracy": float(test_metrics["balanced_accuracy"]),
        "test_macro_f1": float(test_metrics["macro_f1"]),
        "notes": notes,
    }


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def run_training_pipeline(config: ContextTrainConfig) -> dict[str, object]:
    config.validate()
    output_root = config.output_root / "training"
    run_id, output_dir = create_run_directory(output_root, prefix="context_train")
    experiments_dir = output_dir / "experiments"
    output_dir.mkdir(parents=True, exist_ok=True)
    experiments_dir.mkdir(parents=True, exist_ok=True)

    build_manifest = load_build_manifest(config.build_run_dir)
    build_label_scheme = str(build_manifest.get("label_scheme", ""))
    if build_label_scheme and build_label_scheme != config.label_scheme:
        raise ValueError(
            f"Build run label scheme mismatch: build uses {build_label_scheme}, train config uses {config.label_scheme}."
        )
    aggregate_rows: list[dict[str, object]] = []
    experiment_reports: list[dict[str, object]] = []
    print(f"[context_classifier] label_scheme={config.label_scheme} output_dir={output_dir}")

    for experiment_index, experiment_name in enumerate(config.experiment_names, start=1):
        print(f"[context_classifier] experiment {experiment_index}/{len(config.experiment_names)} -> {experiment_name}")
        experiment_output_dir = experiments_dir / experiment_name
        experiment_output_dir.mkdir(parents=True, exist_ok=True)
        if experiment_name == "sequence":
            report, rows = _run_sequence_experiment(config=config, output_dir=experiment_output_dir)
        else:
            report, rows = _run_tabular_experiment(config=config, experiment_name=experiment_name, output_dir=experiment_output_dir)
        experiment_reports.append(report)
        aggregate_rows.extend(rows)

    aggregate_frame = pd.DataFrame(aggregate_rows).sort_values(
        by=["validation_macro_f1", "validation_balanced_accuracy", "test_macro_f1"],
        ascending=False,
    )
    aggregate_metrics_path = output_dir / "aggregate_model_metrics.csv"
    aggregate_frame.to_csv(aggregate_metrics_path, index=False)
    best_row = aggregate_frame.iloc[0].to_dict()

    summary_report = {
        "benchmark_family": config.benchmark_family,
        "benchmark_version": config.benchmark_version,
        "label_scheme": config.label_scheme,
        "run_id": run_id,
        "build_run_dir": str(config.build_run_dir),
        "output_dir": str(output_dir),
        "experiments": config.experiment_names,
        "models": config.model_names,
        "best_result": {
            "experiment_name": str(best_row["experiment_name"]),
            "model_name": str(best_row["model_name"]),
            "validation_macro_f1": float(best_row["validation_macro_f1"]),
            "validation_balanced_accuracy": float(best_row["validation_balanced_accuracy"]),
            "test_macro_f1": float(best_row["test_macro_f1"]),
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
            "best_experiment_name": str(best_row["experiment_name"]),
            "best_model_name": str(best_row["model_name"]),
            "best_validation_macro_f1": float(best_row["validation_macro_f1"]),
        },
    )
    _write_text(output_dir / "best_result.txt", f"{best_row['experiment_name']}::{best_row['model_name']}")
    backfill_training_run_scientific_artifacts(output_dir)
    print(
        f"[context_classifier] best={best_row['experiment_name']}/{best_row['model_name']} "
        f"val_macro_f1={float(best_row['validation_macro_f1']):.4f}"
    )

    return {
        "benchmark_family": config.benchmark_family,
        "benchmark_version": config.benchmark_version,
        "label_scheme": config.label_scheme,
        "experiments": config.experiment_names,
        "best_result": {
            "experiment_name": str(best_row["experiment_name"]),
            "model_name": str(best_row["model_name"]),
            "validation_macro_f1": float(best_row["validation_macro_f1"]),
        },
        "output_dir": str(output_dir),
        "report_path": str(output_dir / "training_report.json"),
        "aggregate_metrics_path": str(aggregate_metrics_path),
    }


def _run_tabular_experiment(
    *,
    config: ContextTrainConfig,
    experiment_name: str,
    output_dir: Path,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    models_dir = output_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    data_bundle = load_tabular_bundle(config.build_run_dir, experiment_name)
    joblib.dump(data_bundle.scaler, output_dir / "scaler.pkl")
    joblib.dump(data_bundle.imputer, output_dir / "imputer.pkl")
    write_json(
        output_dir / "feature_schema.json",
        {
            "experiment_name": experiment_name,
            "feature_names": data_bundle.feature_names,
            "feature_count": len(data_bundle.feature_names),
            "class_names": data_bundle.class_names,
        },
    )

    rows: list[dict[str, object]] = []
    reports: list[dict[str, object]] = []

    if "xgboost" in config.model_names:
        print(f"[context:{config.label_scheme}:{experiment_name}] training xgboost")
        sklearn_results = train_model_suite(
            train_features=data_bundle.train_features,
            train_labels=data_bundle.train_labels,
            validation_features=data_bundle.validation_features,
            validation_labels=data_bundle.validation_labels,
            test_features=data_bundle.test_features,
            test_labels=data_bundle.test_labels,
            class_names=data_bundle.class_names,
            feature_names=data_bundle.feature_names,
            output_dir=output_dir,
            seed=config.seed,
            model_names=["xgboost"],
            progress_prefix=f"context:{config.label_scheme}:{experiment_name}:sklearn",
        )
        for result in sklearn_results:
            rows.append(
                _flatten_model_metrics(
                    experiment_name=experiment_name,
                    model_name=result.model_name,
                    artifact_path=result.artifact_path,
                    validation_metrics=result.metrics.get("validation", {}),
                    test_metrics=result.metrics.get("test", {}),
                    available=result.available,
                    notes=result.notes,
                )
            )
            reports.append(
                {
                    "model_name": result.model_name,
                    "available": result.available,
                    "artifact_path": str(result.artifact_path),
                    "notes": result.notes,
                    "metrics": result.metrics,
                }
            )

    if "tabnet_classifier" in config.model_names:
        print(f"[context:{config.label_scheme}:{experiment_name}] training tabnet_classifier")
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
            progress_label=f"context:{config.label_scheme}:{experiment_name}:tabnet",
        )
        history = tabnet_result.history
        best_record = max(history, key=lambda row: (row["validation_macro_f1"], row["validation_accuracy"]))
        rows.append(
            {
                "experiment_name": experiment_name,
                "model_name": "tabnet_classifier",
                "available": True,
                "artifact_path": str(tabnet_result.artifact_path),
                "validation_accuracy": float(best_record["validation_accuracy"]),
                "validation_balanced_accuracy": float(best_record["validation_balanced_accuracy"]),
                "validation_macro_f1": float(best_record["validation_macro_f1"]),
                "test_accuracy": float(best_record["test_accuracy"]),
                "test_balanced_accuracy": float(best_record["test_balanced_accuracy"]),
                "test_macro_f1": float(best_record["test_macro_f1"]),
                "notes": f"Best epoch {tabnet_result.best_epoch}",
            }
        )
        reports.append(
            {
                "model_name": "tabnet_classifier",
                "available": True,
                "artifact_path": str(tabnet_result.artifact_path),
                "best_epoch": tabnet_result.best_epoch,
                "best_validation_macro_f1": tabnet_result.best_validation_macro_f1,
                "history": history,
            }
        )

    if "ft_transformer_classifier" in config.model_names:
        print(f"[context:{config.label_scheme}:{experiment_name}] training ft_transformer_classifier")
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
            progress_label=f"context:{config.label_scheme}:{experiment_name}:ft",
        )
        history = ft_result.history
        best_record = max(history, key=lambda row: (row["validation_macro_f1"], row["validation_accuracy"]))
        rows.append(
            {
                "experiment_name": experiment_name,
                "model_name": "ft_transformer_classifier",
                "available": True,
                "artifact_path": str(ft_result.artifact_path),
                "validation_accuracy": float(best_record["validation_accuracy"]),
                "validation_balanced_accuracy": float(best_record["validation_balanced_accuracy"]),
                "validation_macro_f1": float(best_record["validation_macro_f1"]),
                "test_accuracy": float(best_record["test_accuracy"]),
                "test_balanced_accuracy": float(best_record["test_balanced_accuracy"]),
                "test_macro_f1": float(best_record["test_macro_f1"]),
                "notes": f"Best epoch {ft_result.best_epoch}",
            }
        )
        reports.append(
            {
                "model_name": "ft_transformer_classifier",
                "available": True,
                "artifact_path": str(ft_result.artifact_path),
                "best_epoch": ft_result.best_epoch,
                "best_validation_macro_f1": ft_result.best_validation_macro_f1,
                "history": history,
            }
        )

    if "tabpfn_classifier" in config.model_names:
        print(f"[context:{config.label_scheme}:{experiment_name}] training tabpfn_classifier")
        tabpfn_result = train_tabpfn_classifier(
            train_features=data_bundle.train_features,
            train_labels=data_bundle.train_labels,
            validation_features=data_bundle.validation_features,
            validation_labels=data_bundle.validation_labels,
            test_features=data_bundle.test_features,
            test_labels=data_bundle.test_labels,
            class_names=data_bundle.class_names,
            feature_names=data_bundle.feature_names,
            config=TabPFNClassifierConfig(
                model_path=config.tabpfn_model_path,
                device=config.tabpfn_device,
                fit_mode=config.tabpfn_fit_mode,
                inference_config=config.tabpfn_inference_config,
                ignore_pretraining_limits=config.tabpfn_ignore_pretraining_limits,
                prediction_batch_size=config.tabpfn_prediction_batch_size,
                seed=config.seed,
            ),
            artifact_path=models_dir / "tabpfn_classifier.joblib",
            progress_label=f"context:{config.label_scheme}:{experiment_name}:tabpfn",
        )
        rows.append(
            _flatten_model_metrics(
                experiment_name=experiment_name,
                model_name="tabpfn_classifier",
                artifact_path=tabpfn_result.artifact_path,
                validation_metrics=tabpfn_result.metrics.get("validation", {}),
                test_metrics=tabpfn_result.metrics.get("test", {}),
                available=tabpfn_result.available,
                notes=tabpfn_result.notes,
            )
        )
        reports.append(
            {
                "model_name": "tabpfn_classifier",
                "available": tabpfn_result.available,
                "artifact_path": str(tabpfn_result.artifact_path),
                "notes": tabpfn_result.notes,
                "training_metadata": tabpfn_result.training_metadata,
                "metrics": tabpfn_result.metrics,
            }
        )

    report = {
        "experiment_name": experiment_name,
        "feature_count": len(data_bundle.feature_names),
        "class_names": data_bundle.class_names,
        "models": reports,
    }
    write_json(output_dir / "experiment_report.json", report)
    return report, rows


def _run_sequence_experiment(
    *,
    config: ContextTrainConfig,
    output_dir: Path,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    models_dir = output_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    data_bundle = load_sequence_bundle(config.build_run_dir)

    write_json(
        output_dir / "feature_schema.json",
        {
            "experiment_name": "sequence",
            "feature_names": data_bundle.feature_names,
            "feature_count": len(data_bundle.feature_names),
            "class_names": data_bundle.class_names,
            "sequence_length": int(data_bundle.train_features.shape[1]),
        },
    )
    joblib.dump(
        {"mean": data_bundle.scaler_mean, "std": data_bundle.scaler_std},
        output_dir / "sequence_scaler.pkl",
    )

    rows: list[dict[str, object]] = []
    reports: list[dict[str, object]] = []

    if "lstm_classifier" in config.model_names:
        print(f"[context:{config.label_scheme}:sequence] training lstm_classifier")
        lstm_result = train_lstm_classifier(
            train_features=data_bundle.train_features,
            train_labels=data_bundle.train_labels,
            validation_features=data_bundle.validation_features,
            validation_labels=data_bundle.validation_labels,
            test_features=data_bundle.test_features,
            test_labels=data_bundle.test_labels,
            class_names=data_bundle.class_names,
            input_dim=data_bundle.train_features.shape[-1],
            output_dim=len(data_bundle.class_names),
            config=LstmClassifierConfig(
                hidden_dim=config.lstm_hidden_dim,
                num_layers=config.lstm_layers,
                dropout=config.lstm_dropout,
                batch_size=config.lstm_batch_size,
                max_epochs=config.lstm_max_epochs,
                patience=config.lstm_patience,
                learning_rate=config.lstm_learning_rate,
                weight_decay=config.lstm_weight_decay,
                max_grad_norm=config.lstm_max_grad_norm,
                seed=config.seed,
            ),
            artifact_path=models_dir / "lstm_classifier.pt",
            progress_label=f"context:{config.label_scheme}:sequence:lstm",
        )
        history = lstm_result.history
        best_record = max(history, key=lambda row: (row["validation_macro_f1"], row["validation_accuracy"]))
        rows.append(
            {
                "experiment_name": "sequence",
                "model_name": "lstm_classifier",
                "available": True,
                "artifact_path": str(lstm_result.artifact_path),
                "validation_accuracy": float(best_record["validation_accuracy"]),
                "validation_balanced_accuracy": float(best_record["validation_balanced_accuracy"]),
                "validation_macro_f1": float(best_record["validation_macro_f1"]),
                "test_accuracy": float(best_record["test_accuracy"]),
                "test_balanced_accuracy": float(best_record["test_balanced_accuracy"]),
                "test_macro_f1": float(best_record["test_macro_f1"]),
                "notes": f"Best epoch {lstm_result.best_epoch}",
            }
        )
        reports.append(
            {
                "model_name": "lstm_classifier",
                "available": True,
                "artifact_path": str(lstm_result.artifact_path),
                "best_epoch": lstm_result.best_epoch,
                "best_validation_macro_f1": lstm_result.best_validation_macro_f1,
                "history": history,
            }
        )

    report = {
        "experiment_name": "sequence",
        "feature_count": len(data_bundle.feature_names),
        "class_names": data_bundle.class_names,
        "models": reports,
    }
    write_json(output_dir / "experiment_report.json", report)
    return report, rows
