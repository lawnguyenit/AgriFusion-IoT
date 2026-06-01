from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path

from Backend.Benchmark.context_classifier.src.config.settings import CONTEXT_CLASSIFIER_ROOT
from Backend.Benchmark.context_classifier.src.data.label_schemes import (
    default_output_root,
    get_label_scheme,
    infer_label_scheme_from_context_labels,
)


DEFAULT_EXPERIMENTS = ["v0", "v1", "v2", "v3", "sequence"]
DEFAULT_MODELS = ["xgboost", "tabnet_classifier", "ft_transformer_classifier", "tabpfn_classifier", "lstm_classifier"]


def _infer_build_run_label_scheme(run_dir: Path) -> str | None:
    manifest_path = run_dir / "dataset_manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}
        manifest_scheme = manifest.get("label_scheme")
        if isinstance(manifest_scheme, str) and manifest_scheme:
            return manifest_scheme
        class_names = manifest.get("class_names")
        if isinstance(class_names, list) and class_names:
            inferred = infer_label_scheme_from_context_labels(class_names)
            if inferred is not None:
                return inferred.name

    label_summary_path = run_dir / "context_label_summary.json"
    if label_summary_path.exists():
        try:
            summary = json.loads(label_summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            summary = {}
        summary_scheme = summary.get("label_scheme")
        if isinstance(summary_scheme, str) and summary_scheme:
            return summary_scheme
        class_names = summary.get("class_names")
        if isinstance(class_names, list) and class_names:
            inferred = infer_label_scheme_from_context_labels(class_names)
            if inferred is not None:
                return inferred.name
        context_counts = summary.get("context_label_counts")
        if isinstance(context_counts, dict) and context_counts:
            inferred = infer_label_scheme_from_context_labels(list(context_counts.keys()))
            if inferred is not None:
                return inferred.name

    return None


def _candidate_output_roots(preferred_output_root: Path) -> list[Path]:
    candidates = [
        preferred_output_root.resolve(),
        (CONTEXT_CLASSIFIER_ROOT / "outputs").resolve(),
        (CONTEXT_CLASSIFIER_ROOT / "outputs_option2_4class").resolve(),
    ]
    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        unique.append(candidate)
    return unique


def _latest_build_run_dir(output_root: Path, label_scheme_name: str) -> Path:
    matched_run_dirs: list[Path] = []
    visited_roots: list[Path] = []
    for root in _candidate_output_roots(output_root):
        if not root.exists():
            continue
        visited_roots.append(root)
        for date_dir in root.iterdir():
            if not date_dir.is_dir():
                continue
            for run_dir in date_dir.iterdir():
                if not run_dir.is_dir() or not run_dir.name.startswith("context_build_"):
                    continue
                inferred_scheme = _infer_build_run_label_scheme(run_dir)
                if inferred_scheme is None:
                    continue
                if inferred_scheme == label_scheme_name:
                    matched_run_dirs.append(run_dir)
    if not matched_run_dirs:
        searched = ", ".join(str(path) for path in visited_roots) if visited_roots else str(output_root)
        raise FileNotFoundError(
            f"No context build runs found for label_scheme={label_scheme_name} under: {searched}"
        )
    return max(matched_run_dirs, key=lambda path: path.stat().st_mtime)


@dataclass
class ContextTrainConfig:
    benchmark_family: str = "context_classifier"
    benchmark_version: str = "train_v0"
    label_scheme: str = "option2_4class"
    build_run_dir: Path | None = None
    output_root: Path | None = None
    experiment_names: list[str] = field(default_factory=lambda: list(DEFAULT_EXPERIMENTS))
    model_names: list[str] = field(default_factory=lambda: list(DEFAULT_MODELS))
    seed: int = 42
    max_epochs: int = 100
    patience: int = 12
    batch_size: int = 64
    learning_rate: float = 1e-3
    weight_decay: float = 1e-4
    max_grad_norm: float = 1.0
    torch_hidden_dim: int = 64
    torch_dropout: float = 0.20
    tabnet_batch_size: int = 64
    tabnet_virtual_batch_size: int = 32
    tabnet_max_epochs: int = 100
    tabnet_patience: int = 12
    tabnet_early_stopping_min_delta: float = 1e-3
    tabnet_learning_rate: float = 1e-3
    tabnet_weight_decay: float = 1e-4
    tabnet_max_grad_norm: float = 1.0
    tabnet_n_d: int = 16
    tabnet_n_a: int = 16
    tabnet_n_steps: int = 4
    tabnet_gamma: float = 1.3
    tabnet_n_independent: int = 2
    tabnet_n_shared: int = 2
    tabnet_momentum: float = 0.02
    tabnet_mask_type: str = "sparsemax"
    ft_batch_size: int = 64
    ft_max_epochs: int = 100
    ft_patience: int = 12
    ft_learning_rate: float = 8e-4
    ft_weight_decay: float = 1e-4
    ft_max_grad_norm: float = 1.0
    ft_token_dim: int = 48
    ft_model_dim: int = 48
    ft_num_heads: int = 6
    ft_num_layers: int = 3
    ft_ffn_multiplier: float = 4.0
    ft_dropout: float = 0.15
    ft_attention_dropout: float = 0.10
    ft_residual_dropout: float = 0.0
    ft_classifier_hidden_dim: int = 64
    lstm_hidden_dim: int = 64
    lstm_layers: int = 2
    lstm_dropout: float = 0.15
    lstm_max_epochs: int = 100
    lstm_patience: int = 12
    tabpfn_model_path: str = "tabpfn-v2-classifier-v2_default.ckpt"
    tabpfn_device: str = "auto"
    tabpfn_fit_mode: str = "fit_preprocessors"
    tabpfn_inference_config: str = "auto"
    tabpfn_ignore_pretraining_limits: bool = False
    tabpfn_prediction_batch_size: int = 128
    lstm_batch_size: int = 64
    lstm_learning_rate: float = 1e-3
    lstm_weight_decay: float = 1e-4
    lstm_max_grad_norm: float = 1.0

    def resolve_defaults(self) -> None:
        get_label_scheme(self.label_scheme)
        if self.output_root is None:
            self.output_root = default_output_root(CONTEXT_CLASSIFIER_ROOT, self.label_scheme)
        else:
            self.output_root = self.output_root.resolve()
        if self.build_run_dir is None:
            self.build_run_dir = _latest_build_run_dir(self.output_root, self.label_scheme)
        else:
            self.build_run_dir = self.build_run_dir.resolve()

    def validate(self) -> None:
        self.resolve_defaults()
        if self.build_run_dir is None or not self.build_run_dir.exists():
            raise FileNotFoundError(f"build_run_dir not found: {self.build_run_dir}")
        if not self.experiment_names:
            raise ValueError("At least one experiment must be selected.")
        if not self.model_names:
            raise ValueError("At least one model must be selected.")
        allowed_experiments = set(DEFAULT_EXPERIMENTS)
        invalid_experiments = [name for name in self.experiment_names if name not in allowed_experiments]
        if invalid_experiments:
            raise ValueError(f"Unsupported experiments: {invalid_experiments}")
        allowed_models = set(DEFAULT_MODELS)
        invalid_models = [name for name in self.model_names if name not in allowed_models]
        if invalid_models:
            raise ValueError(f"Unsupported models: {invalid_models}")
        if self.tabpfn_device not in {"auto", "cpu", "cuda"}:
            raise ValueError(f"Unsupported tabpfn_device: {self.tabpfn_device}")
        if self.tabpfn_fit_mode not in {"fit_preprocessors", "low_memory", "batched"}:
            raise ValueError(f"Unsupported tabpfn_fit_mode: {self.tabpfn_fit_mode}")
        if self.tabpfn_inference_config not in {"auto", "low_memory", "fast"}:
            raise ValueError(f"Unsupported tabpfn_inference_config: {self.tabpfn_inference_config}")
        if self.tabpfn_prediction_batch_size <= 0:
            raise ValueError("tabpfn_prediction_batch_size must be positive.")

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["build_run_dir"] = str(self.build_run_dir) if self.build_run_dir else None
        payload["output_root"] = str(self.output_root) if self.output_root else None
        return payload
