from __future__ import annotations

import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import torch

from Backend.Benchmark.context_classifier.src.data.training_io import (
    load_sequence_bundle,
    load_sequence_split_frames,
    load_tabular_bundle,
    load_tabular_split_frames,
)
from Backend.Benchmark.context_classifier.src.model.lstm_classifier import (
    LstmClassifierConfig,
    LstmSequenceClassifier,
)
from Backend.Benchmark.context_classifier.src.scientific_artifacts import (
    probabilities_from_logits,
    write_context_scientific_artifacts,
)
from Backend.Benchmark.direct_benchmark.src.model.tabnet_classifier import (
    DirectTabNetClassifier,
    DirectTabNetClassifierConfig,
)
from Backend.Benchmark.ft_transformer_benchmark.src.model.ft_transformer_classifier import (
    FTTransformerClassifier,
    FTTransformerClassifierConfig,
)
from Backend.Benchmark.pretrain_supervised.pretrain.src.utils.artifacts import write_json
from Backend.Benchmark.pretrain_supervised.v1.src.model.metrics import summarize_classification


def backfill_training_run_scientific_artifacts(train_run_dir: Path) -> dict[str, object]:
    train_run_dir = train_run_dir.resolve()
    training_report_path = train_run_dir / "training_report.json"
    run_config_path = train_run_dir / "run_config.json"
    if not training_report_path.exists():
        raise FileNotFoundError(f"training_report.json not found: {training_report_path}")
    if not run_config_path.exists():
        raise FileNotFoundError(f"run_config.json not found: {run_config_path}")

    training_report = json.loads(training_report_path.read_text(encoding="utf-8"))
    run_config = json.loads(run_config_path.read_text(encoding="utf-8"))
    build_run_dir = Path(str(training_report["build_run_dir"])).resolve()

    environment_manifest = _build_environment_manifest(train_run_dir)
    environment_manifest_path = train_run_dir / "environment_manifest.json"
    write_json(environment_manifest_path, environment_manifest)

    scientific_run_manifest: dict[str, object] = {
        "train_run_dir": str(train_run_dir),
        "build_run_dir": str(build_run_dir),
        "environment_manifest_path": str(environment_manifest_path),
        "experiments": {},
    }

    updated_experiment_reports: list[dict[str, object]] = []
    for experiment_report in training_report.get("experiment_reports", []):
        experiment_name = str(experiment_report.get("experiment_name"))
        experiment_output_dir = train_run_dir / "experiments" / experiment_name
        updated_report, manifest_entries = _backfill_experiment(
            experiment_name=experiment_name,
            experiment_report=experiment_report,
            experiment_output_dir=experiment_output_dir,
            build_run_dir=build_run_dir,
            run_config=run_config,
        )
        scientific_run_manifest["experiments"][experiment_name] = manifest_entries
        write_json(experiment_output_dir / "experiment_report.json", updated_report)
        updated_experiment_reports.append(updated_report)

    scientific_run_manifest_path = train_run_dir / "scientific_run_manifest.json"
    write_json(scientific_run_manifest_path, scientific_run_manifest)

    training_report["experiment_reports"] = updated_experiment_reports
    training_report["environment_manifest_path"] = str(environment_manifest_path)
    training_report["scientific_run_manifest_path"] = str(scientific_run_manifest_path)
    write_json(training_report_path, training_report)

    return {
        "train_run_dir": str(train_run_dir),
        "environment_manifest_path": str(environment_manifest_path),
        "scientific_run_manifest_path": str(scientific_run_manifest_path),
    }


def _backfill_experiment(
    *,
    experiment_name: str,
    experiment_report: dict[str, object],
    experiment_output_dir: Path,
    build_run_dir: Path,
    run_config: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    if experiment_name == "sequence":
        return _backfill_sequence_experiment(
            experiment_report=experiment_report,
            experiment_output_dir=experiment_output_dir,
            build_run_dir=build_run_dir,
            run_config=run_config,
        )
    return _backfill_tabular_experiment(
        experiment_name=experiment_name,
        experiment_report=experiment_report,
        experiment_output_dir=experiment_output_dir,
        build_run_dir=build_run_dir,
        run_config=run_config,
    )


def _backfill_tabular_experiment(
    *,
    experiment_name: str,
    experiment_report: dict[str, object],
    experiment_output_dir: Path,
    build_run_dir: Path,
    run_config: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    data_bundle = load_tabular_bundle(build_run_dir, experiment_name)
    split_frames = load_tabular_split_frames(build_run_dir, experiment_name)
    feature_names = data_bundle.feature_names
    class_names = data_bundle.class_names

    split_inputs = {
        "train": {
            "features": data_bundle.train_features,
            "labels": data_bundle.train_labels,
            "metadata_frame": split_frames["train"],
        },
        "validation": {
            "features": data_bundle.validation_features,
            "labels": data_bundle.validation_labels,
            "metadata_frame": split_frames["validation"],
        },
        "test": {
            "features": data_bundle.test_features,
            "labels": data_bundle.test_labels,
            "metadata_frame": split_frames["test"],
        },
    }

    manifest_entries: dict[str, object] = {}
    updated_models: list[dict[str, object]] = []
    for model_report in experiment_report.get("models", []):
        model_name = str(model_report.get("model_name"))
        if not bool(model_report.get("available", True)):
            updated_models.append(model_report)
            continue
        scientific_result = _generate_tabular_model_artifacts(
            experiment_output_dir=experiment_output_dir,
            experiment_name=experiment_name,
            model_name=model_name,
            model_report=model_report,
            split_inputs=split_inputs,
            feature_names=feature_names,
            class_names=class_names,
            run_config=run_config,
        )
        updated_model_report = dict(model_report)
        updated_model_report["metrics"] = scientific_result["metrics"]
        updated_model_report["scientific_artifacts"] = scientific_result["manifest"]
        updated_model_report["training_metadata"] = scientific_result["training_metadata"]
        updated_models.append(updated_model_report)
        manifest_entries[model_name] = scientific_result["manifest"]

    updated_report = dict(experiment_report)
    updated_report["models"] = updated_models
    return updated_report, manifest_entries


def _backfill_sequence_experiment(
    *,
    experiment_report: dict[str, object],
    experiment_output_dir: Path,
    build_run_dir: Path,
    run_config: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    data_bundle = load_sequence_bundle(build_run_dir)
    split_frames = load_sequence_split_frames(build_run_dir)
    sequence_metadata = {
        split_name: _sequence_prediction_metadata(frame)
        for split_name, frame in split_frames.items()
    }
    split_inputs = {
        "train": {
            "features": data_bundle.train_features,
            "labels": data_bundle.train_labels,
            "metadata_frame": sequence_metadata["train"],
        },
        "validation": {
            "features": data_bundle.validation_features,
            "labels": data_bundle.validation_labels,
            "metadata_frame": sequence_metadata["validation"],
        },
        "test": {
            "features": data_bundle.test_features,
            "labels": data_bundle.test_labels,
            "metadata_frame": sequence_metadata["test"],
        },
    }

    manifest_entries: dict[str, object] = {}
    updated_models: list[dict[str, object]] = []
    for model_report in experiment_report.get("models", []):
        model_name = str(model_report.get("model_name"))
        if model_name != "lstm_classifier" or not bool(model_report.get("available", True)):
            updated_models.append(model_report)
            continue
        scientific_result = _generate_sequence_model_artifacts(
            experiment_output_dir=experiment_output_dir,
            model_name=model_name,
            model_report=model_report,
            split_inputs=split_inputs,
            class_names=data_bundle.class_names,
            run_config=run_config,
        )
        updated_model_report = dict(model_report)
        updated_model_report["metrics"] = scientific_result["metrics"]
        updated_model_report["scientific_artifacts"] = scientific_result["manifest"]
        updated_model_report["training_metadata"] = scientific_result["training_metadata"]
        updated_models.append(updated_model_report)
        manifest_entries[model_name] = scientific_result["manifest"]

    updated_report = dict(experiment_report)
    updated_report["models"] = updated_models
    return updated_report, manifest_entries


def _generate_tabular_model_artifacts(
    *,
    experiment_output_dir: Path,
    experiment_name: str,
    model_name: str,
    model_report: dict[str, object],
    split_inputs: dict[str, dict[str, object]],
    feature_names: list[str],
    class_names: list[str],
    run_config: dict[str, object],
) -> dict[str, object]:
    artifact_path = Path(str(model_report["artifact_path"]))
    if model_name == "xgboost":
        model = joblib.load(artifact_path)
        split_payloads: dict[str, dict[str, object]] = {}
        for split_name, payload in split_inputs.items():
            frame = pd.DataFrame(payload["features"], columns=feature_names)
            predictions = np.asarray(model.predict(frame), dtype=np.int64)
            probabilities = _ensure_probability_matrix(model.predict_proba(frame), len(class_names))
            labels = np.asarray(payload["labels"], dtype=np.int64)
            split_payloads[split_name] = {
                "metadata_frame": payload["metadata_frame"],
                "labels": labels,
                "predictions": predictions,
                "probabilities": probabilities,
                "metrics": summarize_classification(labels, predictions, class_names),
            }
        training_config = _json_safe(model.get_params())
        training_metadata = {
            "model_class": model.__class__.__name__,
            "notes": str(model_report.get("notes", "")),
        }
        manifest = write_context_scientific_artifacts(
            output_dir=experiment_output_dir,
            experiment_name=experiment_name,
            model_name=model_name,
            class_names=class_names,
            history=[],
            best_epoch=0,
            training_config=training_config,
            training_metadata=training_metadata,
            split_payloads=split_payloads,
        )
        metrics = {split_name: payload["metrics"] for split_name, payload in split_payloads.items()}
        return {"manifest": manifest, "metrics": metrics, "training_metadata": training_metadata}

    if model_name == "tabnet_classifier":
        checkpoint = torch.load(artifact_path, map_location=_torch_device(), weights_only=False)
        model, training_config = _load_tabnet_model(checkpoint)
        history = list(checkpoint.get("history", []))
        best_epoch = int(checkpoint.get("best_epoch", model_report.get("best_epoch", 0)))
        training_metadata = {
            "model_class": str(checkpoint.get("model_class", model.__class__.__name__)),
            "best_validation_macro_f1": float(checkpoint.get("best_validation_macro_f1", model_report.get("best_validation_macro_f1", 0.0))),
        }
        split_payloads = _predict_torch_classifier(
            model=model,
            split_inputs=split_inputs,
            class_names=class_names,
        )
        manifest = write_context_scientific_artifacts(
            output_dir=experiment_output_dir,
            experiment_name=experiment_name,
            model_name=model_name,
            class_names=class_names,
            history=history,
            best_epoch=best_epoch,
            training_config=training_config,
            training_metadata=training_metadata,
            split_payloads=split_payloads,
        )
        metrics = {split_name: payload["metrics"] for split_name, payload in split_payloads.items()}
        return {"manifest": manifest, "metrics": metrics, "training_metadata": training_metadata}

    if model_name == "ft_transformer_classifier":
        checkpoint = torch.load(artifact_path, map_location=_torch_device(), weights_only=False)
        model, training_config = _load_ft_model(checkpoint)
        history = list(checkpoint.get("history", []))
        best_epoch = int(checkpoint.get("best_epoch", model_report.get("best_epoch", 0)))
        training_metadata = {
            "model_class": str(checkpoint.get("model_class", model.__class__.__name__)),
            "best_validation_macro_f1": float(checkpoint.get("best_validation_macro_f1", model_report.get("best_validation_macro_f1", 0.0))),
            "best_validation_loss": _safe_float(checkpoint.get("best_validation_loss")),
            "class_weights": checkpoint.get("class_weights"),
        }
        split_payloads = _predict_torch_classifier(
            model=model,
            split_inputs=split_inputs,
            class_names=class_names,
        )
        manifest = write_context_scientific_artifacts(
            output_dir=experiment_output_dir,
            experiment_name=experiment_name,
            model_name=model_name,
            class_names=class_names,
            history=history,
            best_epoch=best_epoch,
            training_config=training_config,
            training_metadata=training_metadata,
            split_payloads=split_payloads,
        )
        metrics = {split_name: payload["metrics"] for split_name, payload in split_payloads.items()}
        return {"manifest": manifest, "metrics": metrics, "training_metadata": training_metadata}

    if model_name == "tabpfn_classifier":
        model = joblib.load(artifact_path)
        split_payloads = {}
        for split_name, payload in split_inputs.items():
            frame = pd.DataFrame(payload["features"], columns=feature_names)
            predictions = np.asarray(model.predict(frame), dtype=np.int64)
            probabilities = _ensure_probability_matrix(model.predict_proba(frame), len(class_names))
            labels = np.asarray(payload["labels"], dtype=np.int64)
            split_payloads[split_name] = {
                "metadata_frame": payload["metadata_frame"],
                "labels": labels,
                "predictions": predictions,
                "probabilities": probabilities,
                "metrics": summarize_classification(labels, predictions, class_names),
            }
        training_metadata = _json_safe(model_report.get("training_metadata", {}))
        manifest = write_context_scientific_artifacts(
            output_dir=experiment_output_dir,
            experiment_name=experiment_name,
            model_name=model_name,
            class_names=class_names,
            history=[],
            best_epoch=0,
            training_config=_json_safe(run_config),
            training_metadata=training_metadata,
            split_payloads=split_payloads,
        )
        metrics = {split_name: payload["metrics"] for split_name, payload in split_payloads.items()}
        return {"manifest": manifest, "metrics": metrics, "training_metadata": training_metadata}

    raise ValueError(f"Unsupported tabular model for scientific backfill: {model_name}")


def _generate_sequence_model_artifacts(
    *,
    experiment_output_dir: Path,
    model_name: str,
    model_report: dict[str, object],
    split_inputs: dict[str, dict[str, object]],
    class_names: list[str],
    run_config: dict[str, object],
) -> dict[str, object]:
    artifact_path = Path(str(model_report["artifact_path"]))
    checkpoint = torch.load(artifact_path, map_location=_torch_device(), weights_only=False)
    model, training_config = _load_lstm_model(checkpoint)
    history = list(checkpoint.get("history", []))
    best_epoch = int(checkpoint.get("best_epoch", model_report.get("best_epoch", 0)))
    training_metadata = {
        "model_class": str(checkpoint.get("model_class", model.__class__.__name__)),
        "best_validation_macro_f1": float(checkpoint.get("best_validation_macro_f1", model_report.get("best_validation_macro_f1", 0.0))),
        "run_config": _json_safe(run_config),
    }
    split_payloads = _predict_torch_classifier(
        model=model,
        split_inputs=split_inputs,
        class_names=class_names,
    )
    manifest = write_context_scientific_artifacts(
        output_dir=experiment_output_dir,
        experiment_name="sequence",
        model_name=model_name,
        class_names=class_names,
        history=history,
        best_epoch=best_epoch,
        training_config=training_config,
        training_metadata=training_metadata,
        split_payloads=split_payloads,
    )
    metrics = {split_name: payload["metrics"] for split_name, payload in split_payloads.items()}
    return {"manifest": manifest, "metrics": metrics, "training_metadata": training_metadata}


def _predict_torch_classifier(
    *,
    model: torch.nn.Module,
    split_inputs: dict[str, dict[str, object]],
    class_names: list[str],
) -> dict[str, dict[str, object]]:
    device = _torch_device()
    model = model.to(device)
    model.eval()
    results: dict[str, dict[str, object]] = {}
    with torch.no_grad():
        for split_name, payload in split_inputs.items():
            features = torch.tensor(np.asarray(payload["features"], dtype=np.float32), dtype=torch.float32, device=device)
            output = model(features)
            logits = output[0] if isinstance(output, tuple) else output
            logits_np = logits.detach().cpu().numpy()
            probabilities = probabilities_from_logits(logits_np)
            predictions = probabilities.argmax(axis=1).astype(np.int64)
            labels = np.asarray(payload["labels"], dtype=np.int64)
            results[split_name] = {
                "metadata_frame": payload["metadata_frame"],
                "labels": labels,
                "predictions": predictions,
                "probabilities": probabilities,
                "metrics": summarize_classification(labels, predictions, class_names),
            }
    return results


def _load_tabnet_model(checkpoint: dict[str, object]) -> tuple[DirectTabNetClassifier, dict[str, object]]:
    config = DirectTabNetClassifierConfig(**dict(checkpoint["config"]))
    model = DirectTabNetClassifier(
        input_dim=int(checkpoint["input_dim"]),
        output_dim=int(checkpoint["output_dim"]),
        config=config,
    )
    model.load_state_dict(checkpoint["state_dict"])
    return model, config.to_dict()


def _load_ft_model(checkpoint: dict[str, object]) -> tuple[FTTransformerClassifier, dict[str, object]]:
    config = FTTransformerClassifierConfig(**dict(checkpoint["config"]))
    model = FTTransformerClassifier(
        input_dim=int(checkpoint["input_dim"]),
        output_dim=int(checkpoint["output_dim"]),
        config=config,
    )
    model.load_state_dict(checkpoint["state_dict"])
    return model, config.to_dict()


def _load_lstm_model(checkpoint: dict[str, object]) -> tuple[LstmSequenceClassifier, dict[str, object]]:
    config = LstmClassifierConfig(**dict(checkpoint["config"]))
    model = LstmSequenceClassifier(
        input_dim=int(checkpoint["input_dim"]),
        output_dim=int(checkpoint["output_dim"]),
        config=config,
    )
    model.load_state_dict(checkpoint["state_dict"])
    return model, config.to_dict()


def _sequence_prediction_metadata(frame: pd.DataFrame) -> pd.DataFrame:
    ordered = frame.sort_values(["sequence_id", "step_index"]).copy()
    tail = ordered.groupby("sequence_id", as_index=False).tail(1).reset_index(drop=True)
    columns = [
        column
        for column in [
            "sequence_id",
            "target_timestamp",
            "target_label",
            "sequence_origin",
            "split_name",
            "data_origin",
            "is_synthetic",
        ]
        if column in tail.columns
    ]
    return tail[columns].copy()


def _ensure_probability_matrix(probabilities: Any, class_count: int) -> np.ndarray:
    array = np.asarray(probabilities, dtype=np.float64)
    if array.ndim == 1:
        positive = array.reshape(-1, 1)
        negative = 1.0 - positive
        array = np.concatenate([negative, positive], axis=1)
    if array.shape[1] != class_count:
        raise ValueError(
            f"Probability matrix width mismatch: expected {class_count}, got {array.shape[1]}"
        )
    array = np.clip(array, 1e-12, None)
    row_sums = array.sum(axis=1, keepdims=True)
    if np.any(row_sums <= 0.0):
        raise ValueError("Probability matrix contains non-positive row sums after clipping.")
    return array / row_sums


def _build_environment_manifest(train_run_dir: Path) -> dict[str, object]:
    device = _torch_device()
    git_commit = None
    git_branch = None
    try:
        git_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=train_run_dir,
            text=True,
        ).strip()
        git_branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=train_run_dir,
            text=True,
        ).strip()
    except Exception:
        pass

    return {
        "python_executable": sys.executable,
        "python_version": sys.version,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "machine": platform.machine(),
        "packages": {
            "numpy": _package_version("numpy"),
            "pandas": _package_version("pandas"),
            "scikit-learn": _package_version("scikit-learn"),
            "torch": _package_version("torch"),
            "xgboost": _package_version("xgboost"),
            "tabpfn": _package_version("tabpfn"),
        },
        "torch": {
            "cuda_available": bool(torch.cuda.is_available()),
            "torch_cuda_version": torch.version.cuda,
            "device_count": int(torch.cuda.device_count()) if torch.cuda.is_available() else 0,
            "active_device": str(device),
            "device_name": torch.cuda.get_device_name(device) if device.type == "cuda" else "cpu",
        },
        "git": {
            "commit": git_commit,
            "branch": git_branch,
        },
    }


def _package_version(package_name: str) -> str | None:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _torch_device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def _json_safe(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return value


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
