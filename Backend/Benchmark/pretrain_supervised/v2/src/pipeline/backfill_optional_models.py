from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from Backend.Benchmark.pretrain_supervised.v1.src.model.sklearn_models import train_model_suite
from Backend.Benchmark.pretrain_supervised.v1.src.utils.artifacts import write_json, write_text


DEFAULT_MODELS = ["xgboost", "lightgbm"]


@dataclass
class BackfillConfig:
    run_dir: Path
    experiments: list[str]
    model_names: list[str]
    seed: int

    def validate(self) -> None:
        if not self.run_dir.exists():
            raise FileNotFoundError(f"Run directory not found: {self.run_dir}")
        if not (self.run_dir / "training_report.json").exists():
            raise FileNotFoundError(f"training_report.json not found in: {self.run_dir}")
        if not self.experiments:
            raise ValueError("At least one experiment must be selected.")
        if not self.model_names:
            raise ValueError("At least one model must be selected.")


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _normalize_metric_rows(frame: pd.DataFrame) -> pd.DataFrame:
    metric_columns = [
        "validation_accuracy",
        "validation_balanced_accuracy",
        "validation_macro_f1",
        "validation_weighted_f1",
        "test_accuracy",
        "test_balanced_accuracy",
        "test_macro_f1",
        "test_weighted_f1",
    ]
    for column in metric_columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "available" in frame.columns:
        frame["available"] = frame["available"].astype(bool)
    return frame


def _metric_row_from_result(
    *,
    experiment_name: str,
    source_kind: str,
    checkpoint_path: str,
    result: Any,
) -> dict[str, object]:
    validation_metrics = result.metrics.get("validation", {})
    test_metrics = result.metrics.get("test", {})
    return {
        "experiment_name": experiment_name,
        "source_kind": source_kind,
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
        "checkpoint_path": checkpoint_path,
    }


def _sort_metric_frame(frame: pd.DataFrame) -> pd.DataFrame:
    sortable = frame.copy()
    for column in ["validation_macro_f1", "validation_accuracy"]:
        sortable[column] = pd.to_numeric(sortable[column], errors="coerce")
    sortable["_sort_macro_f1"] = sortable["validation_macro_f1"].fillna(-1.0)
    sortable["_sort_accuracy"] = sortable["validation_accuracy"].fillna(-1.0)
    sortable = sortable.sort_values(by=["_sort_macro_f1", "_sort_accuracy"], ascending=False)
    return sortable.drop(columns=["_sort_macro_f1", "_sort_accuracy"])


def _select_best_available_row(frame: pd.DataFrame) -> dict[str, object]:
    available = frame[frame["available"] == True].copy()  # noqa: E712
    if available.empty:
        raise ValueError("No available models found after backfill.")
    available = _sort_metric_frame(available)
    return available.iloc[0].to_dict()


def _load_run_seed(run_dir: Path, default_seed: int) -> int:
    run_config_path = run_dir / "run_config.json"
    if not run_config_path.exists():
        return default_seed
    payload = _load_json(run_config_path)
    value = payload.get("seed")
    if isinstance(value, int):
        return value
    return default_seed


def _read_experiment_dataset(experiment_dir: Path) -> tuple[pd.DataFrame, list[str]]:
    dataset_path = experiment_dir / "embedding_dataset.csv"
    if not dataset_path.exists():
        raise FileNotFoundError(f"Embedding dataset not found: {dataset_path}")
    dataframe = pd.read_csv(dataset_path)
    scaled_columns = [column for column in dataframe.columns if column.startswith("scaled_embedding_")]
    if not scaled_columns:
        raise ValueError(f"No scaled embedding columns found in: {dataset_path}")
    return dataframe, scaled_columns


def _extract_split_arrays(
    dataframe: pd.DataFrame,
    feature_columns: list[str],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if "embedding_split" not in dataframe.columns:
        raise ValueError("embedding_split column is missing from embedding_dataset.csv")
    if "selected_label_id" not in dataframe.columns:
        raise ValueError("selected_label_id column is missing from embedding_dataset.csv")

    train_frame = dataframe[dataframe["embedding_split"] == "train"].copy()
    validation_frame = dataframe[dataframe["embedding_split"] == "validation"].copy()
    test_frame = dataframe[dataframe["embedding_split"] == "test"].copy()

    if train_frame.empty or validation_frame.empty or test_frame.empty:
        raise ValueError("At least one split is empty in embedding_dataset.csv")

    train_features = train_frame[feature_columns].to_numpy(dtype=np.float32)
    validation_features = validation_frame[feature_columns].to_numpy(dtype=np.float32)
    test_features = test_frame[feature_columns].to_numpy(dtype=np.float32)
    train_labels = train_frame["selected_label_id"].to_numpy(dtype=np.int64)
    validation_labels = validation_frame["selected_label_id"].to_numpy(dtype=np.int64)
    test_labels = test_frame["selected_label_id"].to_numpy(dtype=np.int64)
    return (
        train_features,
        train_labels,
        validation_features,
        validation_labels,
        test_features,
        test_labels,
    )


def _backfill_experiment(
    *,
    experiment_name: str,
    experiment_dir: Path,
    model_names: list[str],
    seed: int,
) -> dict[str, object]:
    training_report_path = experiment_dir / "training_report.json"
    label_policy_path = experiment_dir / "label_policy.json"
    metrics_path = experiment_dir / "model_metrics.csv"

    if not training_report_path.exists():
        raise FileNotFoundError(f"Experiment training report not found: {training_report_path}")
    if not label_policy_path.exists():
        raise FileNotFoundError(f"Label policy not found: {label_policy_path}")
    if not metrics_path.exists():
        raise FileNotFoundError(f"Model metrics not found: {metrics_path}")

    training_report = _load_json(training_report_path)
    label_policy = _load_json(label_policy_path)
    class_names = list(label_policy["class_names"])
    source_kind = str(training_report["source_kind"])
    checkpoint_path = str(training_report["pretrain_checkpoint"])

    dataframe, feature_columns = _read_experiment_dataset(experiment_dir)
    (
        train_features,
        train_labels,
        validation_features,
        validation_labels,
        test_features,
        test_labels,
    ) = _extract_split_arrays(dataframe, feature_columns)

    results = train_model_suite(
        train_features=train_features,
        train_labels=train_labels,
        validation_features=validation_features,
        validation_labels=validation_labels,
        test_features=test_features,
        test_labels=test_labels,
        class_names=class_names,
        feature_names=feature_columns,
        output_dir=experiment_dir,
        seed=seed,
        model_names=model_names,
    )

    metrics_frame = _normalize_metric_rows(pd.read_csv(metrics_path))
    replacement_rows = pd.DataFrame(
        [
            _metric_row_from_result(
                experiment_name=experiment_name,
                source_kind=source_kind,
                checkpoint_path=checkpoint_path,
                result=result,
            )
            for result in results
        ]
    )
    replacement_rows = _normalize_metric_rows(replacement_rows)

    metrics_frame = metrics_frame[~metrics_frame["model_name"].isin(model_names)]
    metrics_frame = pd.concat([metrics_frame, replacement_rows], ignore_index=True)
    metrics_frame = _sort_metric_frame(metrics_frame)
    metrics_frame.to_csv(metrics_path, index=False)

    metric_rows = metrics_frame.replace({np.nan: None}).to_dict(orient="records")
    best_row = _select_best_available_row(metrics_frame)
    best_validation_macro_f1 = float(best_row["validation_macro_f1"])

    training_report["models"] = metric_rows
    training_report["selected_model"] = {
        "model_name": str(best_row["model_name"]),
        "artifact_path": str(best_row["artifact_path"]),
        "validation_macro_f1": best_validation_macro_f1,
    }
    write_json(training_report_path, training_report)
    write_text(experiment_dir / "best_model.txt", str(best_row["model_name"]))
    write_json(
        experiment_dir / "run_status.json",
        {
            "completed": True,
            "experiment_name": experiment_name,
            "output_dir": str(experiment_dir),
            "best_model_name": str(best_row["model_name"]),
            "best_validation_macro_f1": best_validation_macro_f1,
            "pretrain_checkpoint": checkpoint_path,
            "backfilled_models": model_names,
        },
    )

    return {
        "experiment_name": experiment_name,
        "training_report": training_report,
        "metrics_rows": metric_rows,
        "updated_models": model_names,
    }


def run_backfill(config: BackfillConfig) -> dict[str, object]:
    config.validate()

    experiments_dir = config.run_dir / "experiments"
    if not experiments_dir.exists():
        raise FileNotFoundError(f"Experiments directory not found: {experiments_dir}")

    root_training_report = _load_json(config.run_dir / "training_report.json")
    updated_reports: list[dict[str, object]] = []

    for experiment_name in config.experiments:
        experiment_dir = experiments_dir / experiment_name
        if not experiment_dir.exists():
            raise FileNotFoundError(f"Experiment directory not found: {experiment_dir}")
        updated = _backfill_experiment(
            experiment_name=experiment_name,
            experiment_dir=experiment_dir,
            model_names=config.model_names,
            seed=config.seed,
        )
        updated_reports.append(updated)

    aggregate_rows: list[dict[str, object]] = []
    experiment_reports_by_name = {
        str(report["experiment_name"]): report["training_report"] for report in updated_reports
    }

    for experiment_name in root_training_report["experiments"]:
        experiment_dir = experiments_dir / experiment_name
        metrics_frame = _normalize_metric_rows(pd.read_csv(experiment_dir / "model_metrics.csv"))
        aggregate_rows.extend(metrics_frame.replace({np.nan: None}).to_dict(orient="records"))
        if experiment_name in experiment_reports_by_name:
            report_payload = experiment_reports_by_name[experiment_name]
        else:
            report_payload = _load_json(experiment_dir / "training_report.json")
        experiment_reports_by_name[experiment_name] = report_payload

    aggregate_frame = _normalize_metric_rows(pd.DataFrame(aggregate_rows))
    aggregate_frame = _sort_metric_frame(aggregate_frame)
    aggregate_metrics_path = config.run_dir / "aggregate_model_metrics.csv"
    aggregate_frame.to_csv(aggregate_metrics_path, index=False)

    best_row = _select_best_available_row(aggregate_frame)
    root_training_report["best_result"] = {
        "experiment_name": str(best_row["experiment_name"]),
        "model_name": str(best_row["model_name"]),
        "validation_macro_f1": float(best_row["validation_macro_f1"]),
        "validation_accuracy": float(best_row["validation_accuracy"]),
        "artifact_path": str(best_row["artifact_path"]),
    }
    root_training_report["experiment_reports"] = [
        experiment_reports_by_name[experiment_name] for experiment_name in root_training_report["experiments"]
    ]
    write_json(config.run_dir / "training_report.json", root_training_report)
    write_json(
        config.run_dir / "run_status.json",
        {
            "completed": True,
            "output_dir": str(config.run_dir),
            "best_experiment_name": str(best_row["experiment_name"]),
            "best_model_name": str(best_row["model_name"]),
            "best_validation_macro_f1": float(best_row["validation_macro_f1"]),
            "backfilled_models": config.model_names,
        },
    )
    write_text(config.run_dir / "best_result.txt", f"{best_row['experiment_name']}::{best_row['model_name']}")
    write_json(
        config.run_dir / "backfill_optional_models_report.json",
        {
            "run_dir": str(config.run_dir),
            "experiments": config.experiments,
            "model_names": config.model_names,
            "best_result": root_training_report["best_result"],
        },
    )

    return {
        "run_dir": str(config.run_dir),
        "experiments": config.experiments,
        "model_names": config.model_names,
        "best_result": root_training_report["best_result"],
        "aggregate_metrics_path": str(aggregate_metrics_path),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill optional downstream models for an existing v2 run without rerunning the full suite."
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        required=True,
        help="Existing v2 output run directory, e.g. ...\\v2\\outputs\\v2_20260513_151525",
    )
    parser.add_argument(
        "--experiments",
        nargs="+",
        default=None,
        help="Subset of experiments to update, default is every experiment found in the run report.",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=list(DEFAULT_MODELS),
        help="Model names to backfill, default is xgboost lightgbm.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Fallback random seed if run_config.json does not contain one.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    root_training_report = _load_json(run_dir / "training_report.json")
    experiments = list(args.experiments) if args.experiments else list(root_training_report["experiments"])
    config = BackfillConfig(
        run_dir=run_dir,
        experiments=experiments,
        model_names=list(args.models),
        seed=_load_run_seed(run_dir, args.seed),
    )
    result = run_backfill(config)
    print(f"Run dir: {result['run_dir']}")
    print(f"Experiments: {', '.join(result['experiments'])}")
    print(f"Backfilled models: {', '.join(result['model_names'])}")
    best_result = result["best_result"]
    print(
        "Best result: "
        f"{best_result['experiment_name']}::{best_result['model_name']} "
        f"(validation_macro_f1={best_result['validation_macro_f1']:.4f})"
    )
    print(f"Aggregate metrics: {result['aggregate_metrics_path']}")
