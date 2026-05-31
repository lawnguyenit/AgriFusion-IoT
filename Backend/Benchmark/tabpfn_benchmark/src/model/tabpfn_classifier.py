from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import inspect
import sys

import joblib
import numpy as np
import pandas as pd

from Backend.Benchmark.pretrain_supervised.v1.src.model.metrics import summarize_classification

try:
    from tabpfn import TabPFNClassifier as _ImportedTabPFNClassifier  # type: ignore
    TABPFN_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - optional dependency
    _ImportedTabPFNClassifier = None
    TABPFN_IMPORT_ERROR = exc


@dataclass
class TabPFNClassifierConfig:
    model_path: str = "tabpfn-v2-classifier-v2_default.ckpt"
    device: str = "auto"
    fit_mode: str = "fit_preprocessors"
    inference_config: object = "auto"
    ignore_pretraining_limits: bool = False
    prediction_batch_size: int = 128
    seed: int = 42

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class TabPFNTrainResult:
    model_name: str
    artifact_path: Path
    metrics: dict[str, object]
    scientific_split_payloads: dict[str, dict[str, object]]
    training_metadata: dict[str, object]
    available: bool = True
    notes: str = ""


def train_tabpfn_classifier(
    *,
    train_features: np.ndarray,
    train_labels: np.ndarray,
    validation_features: np.ndarray,
    validation_labels: np.ndarray,
    test_features: np.ndarray,
    test_labels: np.ndarray,
    class_names: list[str],
    feature_names: list[str],
    config: TabPFNClassifierConfig,
    artifact_path: Path,
    progress_label: str | None = None,
) -> TabPFNTrainResult:
    if _ImportedTabPFNClassifier is None:
        note = _build_missing_tabpfn_note()
        return TabPFNTrainResult(
            model_name="tabpfn_classifier",
            artifact_path=artifact_path,
            metrics={},
            scientific_split_payloads={},
            training_metadata={
                "tabpfn_available": False,
                "import_error": note,
                "training_config": config.to_dict(),
            },
            available=False,
            notes=note,
        )

    if progress_label:
        print(f"[{progress_label}] preparing tabpfn_classifier")

    train_frame = pd.DataFrame(train_features, columns=feature_names)
    validation_frame = pd.DataFrame(validation_features, columns=feature_names)
    test_frame = pd.DataFrame(test_features, columns=feature_names)

    constructor_kwargs, constructor_notes = _build_constructor_kwargs(config)
    if progress_label:
        print(f"[{progress_label}] fitting tabpfn_classifier")
    model = _ImportedTabPFNClassifier(**constructor_kwargs)
    try:
        model.fit(train_frame, train_labels)
    except ValueError as exc:
        if "Unknown user config provided" in str(exc) and "inference_config" in constructor_kwargs:
            constructor_notes.append(
                "Installed TabPFN rejected inference_config at fit-time; retried with the default inference_config."
            )
            constructor_kwargs = dict(constructor_kwargs)
            constructor_kwargs.pop("inference_config", None)
            model = _ImportedTabPFNClassifier(**constructor_kwargs)
            model.fit(train_frame, train_labels)
        else:
            raise
    except OSError as exc:
        if "WinError 10038" in str(exc):
            raise RuntimeError(
                "TabPFN entered the gated browser-auth flow before model download. "
                "This benchmark should use the ungated v2 checkpoint. "
                "Keep --tabpfn-model-path=tabpfn-v2-classifier-v2_default.ckpt, or set "
                "TABPFN_TOKEN if you intentionally want a gated model version."
            ) from exc
        raise

    train_predictions = _predict_in_batches(
        model,
        train_frame,
        batch_size=config.prediction_batch_size,
        predict_kind="labels",
    )
    validation_predictions = _predict_in_batches(
        model,
        validation_frame,
        batch_size=config.prediction_batch_size,
        predict_kind="labels",
    )
    test_predictions = _predict_in_batches(
        model,
        test_frame,
        batch_size=config.prediction_batch_size,
        predict_kind="labels",
    )

    train_probabilities = _ensure_probability_matrix(
        _predict_in_batches(
            model,
            train_frame,
            batch_size=config.prediction_batch_size,
            predict_kind="probabilities",
        ),
        len(class_names),
    )
    validation_probabilities = _ensure_probability_matrix(
        _predict_in_batches(
            model,
            validation_frame,
            batch_size=config.prediction_batch_size,
            predict_kind="probabilities",
        ),
        len(class_names),
    )
    test_probabilities = _ensure_probability_matrix(
        _predict_in_batches(
            model,
            test_frame,
            batch_size=config.prediction_batch_size,
            predict_kind="probabilities",
        ),
        len(class_names),
    )

    train_metrics = summarize_classification(train_labels, train_predictions, class_names)
    validation_metrics = summarize_classification(validation_labels, validation_predictions, class_names)
    test_metrics = summarize_classification(test_labels, test_predictions, class_names)

    if progress_label:
        print(
            f"[{progress_label}] completed tabpfn_classifier: "
            f"val_macro_f1={validation_metrics['macro_f1']:.4f}, "
            f"test_macro_f1={test_metrics['macro_f1']:.4f}"
        )

    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, artifact_path)

    scientific_split_payloads = {
        "train": {
            "labels": train_labels,
            "predictions": np.asarray(train_predictions, dtype=np.int64),
            "probabilities": train_probabilities,
            "metrics": train_metrics,
        },
        "validation": {
            "labels": validation_labels,
            "predictions": np.asarray(validation_predictions, dtype=np.int64),
            "probabilities": validation_probabilities,
            "metrics": validation_metrics,
        },
        "test": {
            "labels": test_labels,
            "predictions": np.asarray(test_predictions, dtype=np.int64),
            "probabilities": test_probabilities,
            "metrics": test_metrics,
        },
    }

    training_metadata = {
        "tabpfn_available": True,
        "tabpfn_module": getattr(_ImportedTabPFNClassifier, "__module__", "tabpfn"),
        "tabpfn_class_name": getattr(_ImportedTabPFNClassifier, "__name__", "TabPFNClassifier"),
        "constructor_kwargs": constructor_kwargs,
        "constructor_notes": constructor_notes,
        "training_config": config.to_dict(),
    }
    return TabPFNTrainResult(
        model_name="tabpfn_classifier",
        artifact_path=artifact_path,
        metrics={
            "train": train_metrics,
            "validation": validation_metrics,
            "test": test_metrics,
            "history": [],
        },
        scientific_split_payloads=scientific_split_payloads,
        training_metadata=training_metadata,
        notes=_build_result_note(constructor_notes),
    )


def _build_constructor_kwargs(config: TabPFNClassifierConfig) -> tuple[dict[str, Any], list[str]]:
    signature = inspect.signature(_ImportedTabPFNClassifier.__init__)  # type: ignore[union-attr]
    accepted = set(signature.parameters.keys())
    accepted.discard("self")
    kwargs: dict[str, Any] = {}
    notes: list[str] = []
    if "model_path" in accepted and config.model_path.strip():
        kwargs["model_path"] = config.model_path.strip()
    if "device" in accepted and config.device != "auto":
        kwargs["device"] = config.device
    if "ignore_pretraining_limits" in accepted and config.ignore_pretraining_limits:
        kwargs["ignore_pretraining_limits"] = True
    if "fit_mode" in accepted:
        kwargs["fit_mode"] = config.fit_mode
    if "inference_config" in accepted:
        if isinstance(config.inference_config, dict):
            kwargs["inference_config"] = config.inference_config
        elif config.inference_config not in (None, "auto"):
            notes.append(
                f"Ignored preset-like inference_config={config.inference_config!r}; "
                "installed TabPFN expects dict/InferenceConfig/None."
            )
    if "random_state" in accepted:
        kwargs["random_state"] = config.seed
    elif "seed" in accepted:
        kwargs["seed"] = config.seed
    return kwargs, notes


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
    array = array / row_sums
    return array


def _predict_in_batches(
    model: Any,
    frame: pd.DataFrame,
    *,
    batch_size: int,
    predict_kind: str,
) -> np.ndarray:
    if batch_size <= 0:
        raise ValueError(f"prediction_batch_size must be positive, got {batch_size}")
    if len(frame) == 0:
        return np.empty((0,), dtype=np.int64) if predict_kind == "labels" else np.empty((0, 0), dtype=np.float64)

    outputs: list[np.ndarray] = []
    for start in range(0, len(frame), batch_size):
        stop = min(start + batch_size, len(frame))
        batch = frame.iloc[start:stop]
        if predict_kind == "labels":
            prediction = model.predict(batch)
            outputs.append(np.asarray(prediction, dtype=np.int64))
        elif predict_kind == "probabilities":
            probabilities = model.predict_proba(batch)
            outputs.append(np.asarray(probabilities, dtype=np.float64))
        else:
            raise ValueError(f"Unsupported predict_kind: {predict_kind}")
    return np.concatenate(outputs, axis=0)


def _build_missing_tabpfn_note() -> str:
    if TABPFN_IMPORT_ERROR is None:
        import_reason = "tabpfn import failed."
    else:
        import_reason = f"tabpfn import failed: {type(TABPFN_IMPORT_ERROR).__name__}: {TABPFN_IMPORT_ERROR}"
    install_hint = (
        f"Install it into the active env with: "
        f"\"{sys.executable}\" -m pip install tabpfn"
    )
    return f"{import_reason} active_python={sys.executable} python_version={sys.version.split()[0]}. {install_hint}"


def _build_result_note(constructor_notes: list[str]) -> str:
    base_note = "Optional TabPFN baseline on raw benchmark features."
    if not constructor_notes:
        return base_note
    return f"{base_note} {' '.join(constructor_notes)}"
