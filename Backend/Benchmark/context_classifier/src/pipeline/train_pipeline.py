from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd
import torch

from Backend.Benchmark.context_classifier.src.config.train_settings import ContextTrainConfig
from Backend.Benchmark.context_classifier.src.data.training_io import load_build_manifest, load_tabular_bundle
from Backend.Benchmark.context_classifier.src.pipeline.scientific_artifact_pipeline import (
    backfill_training_run_scientific_artifacts,
)
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
from Backend.Benchmark.shared.metrics import summarize_classification


def run_training_pipeline(config: ContextTrainConfig) -> dict[str, object]:
    config.validate()
    run_id, output_dir = create_run_directory(config.output_root, prefix="context_train")
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
        report, rows = _run_tabular_experiment(
            config=config,
            experiment_name=experiment_name,
            output_dir=experiment_output_dir,
        )
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
    write_text(output_dir / "best_result.txt", f"{best_row['experiment_name']}::{best_row['model_name']}")
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

    model_rows: list[dict[str, object]] = []
    model_reports: list[dict[str, object]] = []

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
            validation_metrics = result.metrics.get("validation", {})
            test_metrics = result.metrics.get("test", {})
            model_rows.append(
                _metric_row(
                    experiment_name=experiment_name,
                    model_name=result.model_name,
                    artifact_path=result.artifact_path,
                    validation_metrics=validation_metrics,
                    test_metrics=test_metrics,
                    available=result.available,
                    notes=result.notes,
                )
            )
            model_reports.append(
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
        tabnet_payload = _evaluate_torch_model(
            model=tabnet_result.model,
            validation_features=data_bundle.validation_features,
            validation_labels=data_bundle.validation_labels,
            test_features=data_bundle.test_features,
            test_labels=data_bundle.test_labels,
            class_names=data_bundle.class_names,
        )
        model_rows.append(
            _metric_row(
                experiment_name=experiment_name,
                model_name="tabnet_classifier",
                artifact_path=tabnet_result.artifact_path,
                validation_metrics=tabnet_payload["validation"],
                test_metrics=tabnet_payload["test"],
                available=True,
                notes=f"Best epoch {tabnet_result.best_epoch}",
            )
        )
        model_reports.append(
            {
                "model_name": "tabnet_classifier",
                "available": True,
                "artifact_path": str(tabnet_result.artifact_path),
                "best_epoch": tabnet_result.best_epoch,
                "best_validation_macro_f1": tabnet_result.best_validation_macro_f1,
                "history": tabnet_result.history,
                "metrics": tabnet_payload,
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
        ft_payload = _evaluate_torch_model(
            model=ft_result.model,
            validation_features=data_bundle.validation_features,
            validation_labels=data_bundle.validation_labels,
            test_features=data_bundle.test_features,
            test_labels=data_bundle.test_labels,
            class_names=data_bundle.class_names,
        )
        model_rows.append(
            _metric_row(
                experiment_name=experiment_name,
                model_name="ft_transformer_classifier",
                artifact_path=ft_result.artifact_path,
                validation_metrics=ft_payload["validation"],
                test_metrics=ft_payload["test"],
                available=True,
                notes=f"Best epoch {ft_result.best_epoch}",
            )
        )
        model_reports.append(
            {
                "model_name": "ft_transformer_classifier",
                "available": True,
                "artifact_path": str(ft_result.artifact_path),
                "best_epoch": ft_result.best_epoch,
                "best_validation_macro_f1": ft_result.best_validation_macro_f1,
                "history": ft_result.history,
                "metrics": ft_payload,
            }
        )

    report = {
        "experiment_name": experiment_name,
        "feature_count": len(data_bundle.feature_names),
        "class_names": data_bundle.class_names,
        "models": model_reports,
    }
    write_json(output_dir / "experiment_report.json", report)
    return report, model_rows


def _evaluate_torch_model(
    *,
    model: torch.nn.Module,
    validation_features: object,
    validation_labels: object,
    test_features: object,
    test_labels: object,
    class_names: list[str],
) -> dict[str, dict[str, object]]:
    device = next(model.parameters()).device
    with torch.no_grad():
        validation_output = model(torch.tensor(validation_features, dtype=torch.float32, device=device))
        test_output = model(torch.tensor(test_features, dtype=torch.float32, device=device))
    validation_logits = validation_output[0] if isinstance(validation_output, tuple) else validation_output
    test_logits = test_output[0] if isinstance(test_output, tuple) else test_output
    validation_predictions = validation_logits.argmax(dim=1).detach().cpu().numpy()
    test_predictions = test_logits.argmax(dim=1).detach().cpu().numpy()
    return {
        "validation": summarize_classification(validation_labels, validation_predictions, class_names),
        "test": summarize_classification(test_labels, test_predictions, class_names),
    }


def _metric_row(
    *,
    experiment_name: str,
    model_name: str,
    artifact_path: Path,
    validation_metrics: dict[str, object],
    test_metrics: dict[str, object],
    available: bool,
    notes: str,
) -> dict[str, object]:
    return {
        "experiment_name": experiment_name,
        "model_name": model_name,
        "available": bool(available),
        "artifact_path": str(artifact_path),
        "validation_accuracy": float(validation_metrics.get("accuracy", 0.0)),
        "validation_balanced_accuracy": float(validation_metrics.get("balanced_accuracy", 0.0)),
        "validation_macro_f1": float(validation_metrics.get("macro_f1", 0.0)),
        "test_accuracy": float(test_metrics.get("accuracy", 0.0)),
        "test_balanced_accuracy": float(test_metrics.get("balanced_accuracy", 0.0)),
        "test_macro_f1": float(test_metrics.get("macro_f1", 0.0)),
        "notes": notes,
    }
