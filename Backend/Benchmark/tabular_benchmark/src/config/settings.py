from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from Backend.Benchmark.common.artifact_paths import resolve_dataset_artifact_path
from Backend.Benchmark.common.paths import TABULAR_BENCHMARK_ROOT, BENCHMARK_DATASETS_ROOT

DEFAULT_DATASET_ROOT = BENCHMARK_DATASETS_ROOT
DEFAULT_ALIGNED_CSV = DEFAULT_DATASET_ROOT / "benchmark_input_aligned.csv"
DEFAULT_EVENT_CSV = DEFAULT_DATASET_ROOT / "benchmark_input_labeled.csv"
DEFAULT_EXPERIMENTS = ["v0", "v1", "v2", "v3", "v4", "v5"]
DEFAULT_MODELS = ["xgboost", "tabnet_classifier", "ft_transformer_classifier"]
DEFAULT_ARTIFACT_ROOT = TABULAR_BENCHMARK_ROOT / "artifacts"
DEFAULT_SPLIT_STRATEGIES = {
    "chronological_v1",
    "chronological_with_lookback_gap",
    "coverage_aware_temporal",
}


def normalize_label_lane(label_mode: str) -> str:
    normalized = str(label_mode).strip()
    if normalized not in {"auto", "binary", "tri_class", "four_class"}:
        raise ValueError(f"Unsupported label_mode: {label_mode}")
    return normalized


def default_dataset_output_root(label_mode: str) -> Path:
    lane = normalize_label_lane(label_mode)
    return (DEFAULT_ARTIFACT_ROOT / lane / "datasets").resolve()


def default_training_output_root(label_mode: str) -> Path:
    lane = normalize_label_lane(label_mode)
    return (DEFAULT_ARTIFACT_ROOT / lane / "training").resolve()


def default_report_output_root(label_mode: str) -> Path:
    lane = normalize_label_lane(label_mode)
    return (DEFAULT_ARTIFACT_ROOT / lane / "reports").resolve()


def _validate_common_dataset_inputs(*, dataset_root: Path, aligned_csv: Path, event_csv: Path) -> None:
    if not aligned_csv.exists():
        raise FileNotFoundError(f"Aligned CSV not found: {aligned_csv}")
    if not event_csv.exists():
        raise FileNotFoundError(f"Event CSV not found: {event_csv}")
    if not dataset_root.exists():
        raise FileNotFoundError(f"Dataset root not found: {dataset_root}")


def _validate_experiments(experiments: list[str]) -> None:
    if not experiments:
        raise ValueError("At least one experiment must be selected.")
    invalid = [name for name in experiments if name not in set(DEFAULT_EXPERIMENTS)]
    if invalid:
        raise ValueError(f"Unsupported experiments: {invalid}")


def _validate_label_mode(label_mode: str, *, allow_auto: bool) -> str:
    normalized = normalize_label_lane(label_mode)
    if not allow_auto and normalized == "auto":
        raise ValueError("Explicit build/train lanes require binary, tri_class, or four_class; auto is legacy-only.")
    return normalized


def _validate_split_strategy(split_strategy: str) -> str:
    normalized = str(split_strategy).strip()
    if normalized not in DEFAULT_SPLIT_STRATEGIES:
        raise ValueError(f"Unsupported split_strategy: {split_strategy}")
    return normalized


@dataclass
class DirectBenchmarkBuildConfig:
    benchmark_family: str = "tabular_benchmark"
    benchmark_version: str = "direct_build"
    dataset_root: Path = field(default_factory=lambda: DEFAULT_DATASET_ROOT.resolve())
    aligned_csv: Path = field(default_factory=lambda: DEFAULT_ALIGNED_CSV.resolve())
    event_csv: Path = field(default_factory=lambda: DEFAULT_EVENT_CSV.resolve())
    output_root: Path | None = None
    experiments: list[str] = field(default_factory=lambda: list(DEFAULT_EXPERIMENTS))
    label_mode: str = "binary"
    min_class_support: int = 20
    min_class_ratio: float = 0.10
    train_ratio: float = 0.70
    validation_ratio: float = 0.15
    test_ratio: float = 0.15
    split_strategy: str = "coverage_aware_temporal"
    split_gap_minutes_override: int | None = None

    def resolve_defaults(self) -> None:
        self.label_mode = _validate_label_mode(self.label_mode, allow_auto=False)
        self.split_strategy = _validate_split_strategy(self.split_strategy)
        self.dataset_root = self.dataset_root.resolve()
        self.aligned_csv = resolve_dataset_artifact_path(self.aligned_csv, self.dataset_root)
        self.event_csv = resolve_dataset_artifact_path(self.event_csv, self.dataset_root)
        if self.output_root is None:
            self.output_root = default_dataset_output_root(self.label_mode)
        else:
            self.output_root = self.output_root.resolve()

    def validate(self) -> None:
        self.resolve_defaults()
        _validate_common_dataset_inputs(
            dataset_root=self.dataset_root,
            aligned_csv=self.aligned_csv,
            event_csv=self.event_csv,
        )
        _validate_experiments(self.experiments)
        total = self.train_ratio + self.validation_ratio + self.test_ratio
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"Split ratios must sum to 1.0, got {total}")
        if self.min_class_support <= 0:
            raise ValueError("min_class_support must be positive.")
        if not 0.0 < self.min_class_ratio <= 1.0:
            raise ValueError("min_class_ratio must be in (0, 1].")

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["dataset_root"] = str(self.dataset_root)
        payload["aligned_csv"] = str(self.aligned_csv)
        payload["event_csv"] = str(self.event_csv)
        payload["output_root"] = str(self.output_root) if self.output_root else None
        return payload


@dataclass
class DirectBenchmarkTrainConfig:
    benchmark_family: str = "tabular_benchmark"
    benchmark_version: str = "direct_train"
    build_run_dir: Path | None = None
    output_root: Path | None = None
    experiments: list[str] = field(default_factory=lambda: list(DEFAULT_EXPERIMENTS))
    label_mode: str = "binary"
    model_names: list[str] = field(default_factory=lambda: list(DEFAULT_MODELS))
    seed: int = 42
    tabnet_batch_size: int = 64
    tabnet_virtual_batch_size: int = 32
    tabnet_max_epochs: int = 120
    tabnet_patience: int = 16
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
    ft_max_epochs: int = 140
    ft_patience: int = 18
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

    def resolve_defaults(self) -> None:
        self.label_mode = _validate_label_mode(self.label_mode, allow_auto=False)
        if self.output_root is None:
            self.output_root = default_training_output_root(self.label_mode)
        else:
            self.output_root = self.output_root.resolve()
        if self.build_run_dir is not None:
            self.build_run_dir = self.build_run_dir.resolve()

    def validate(self) -> None:
        self.resolve_defaults()
        _validate_experiments(self.experiments)
        if self.build_run_dir is None or not self.build_run_dir.exists():
            raise FileNotFoundError(f"build_run_dir not found: {self.build_run_dir}")
        if not self.model_names:
            raise ValueError("At least one model must be selected.")
        invalid_models = [name for name in self.model_names if name not in set(DEFAULT_MODELS)]
        if invalid_models:
            raise ValueError(f"Unsupported models: {invalid_models}")
        if self.tabnet_batch_size <= 0 or self.tabnet_virtual_batch_size <= 0:
            raise ValueError("TabNet batch sizes must be positive.")
        if self.tabnet_max_epochs <= 0 or self.tabnet_patience <= 0:
            raise ValueError("TabNet epochs and patience must be positive.")
        if self.tabnet_learning_rate <= 0 or self.tabnet_weight_decay < 0:
            raise ValueError("TabNet learning_rate must be positive and weight_decay non-negative.")
        if self.ft_batch_size <= 0 or self.ft_max_epochs <= 0 or self.ft_patience <= 0:
            raise ValueError("FT-Transformer batch_size, max_epochs, patience must be positive.")
        if self.ft_learning_rate <= 0 or self.ft_weight_decay < 0:
            raise ValueError("FT-Transformer learning_rate must be positive and weight_decay non-negative.")
        if self.ft_model_dim % self.ft_num_heads != 0:
            raise ValueError("ft_model_dim must be divisible by ft_num_heads.")

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["build_run_dir"] = str(self.build_run_dir) if self.build_run_dir else None
        payload["output_root"] = str(self.output_root) if self.output_root else None
        return payload


@dataclass
class DirectBenchmarkConfig:
    benchmark_family: str = "tabular_benchmark"
    benchmark_version: str = "direct"
    dataset_root: Path = field(default_factory=lambda: DEFAULT_DATASET_ROOT.resolve())
    aligned_csv: Path = field(default_factory=lambda: DEFAULT_ALIGNED_CSV.resolve())
    event_csv: Path = field(default_factory=lambda: DEFAULT_EVENT_CSV.resolve())
    output_root: Path | None = None
    experiments: list[str] = field(default_factory=lambda: list(DEFAULT_EXPERIMENTS))
    label_mode: str = "auto"
    min_class_support: int = 20
    min_class_ratio: float = 0.10
    seed: int = 42
    train_ratio: float = 0.70
    validation_ratio: float = 0.15
    test_ratio: float = 0.15
    split_strategy: str = "coverage_aware_temporal"
    split_gap_minutes_override: int | None = None
    tabnet_batch_size: int = 64
    tabnet_virtual_batch_size: int = 32
    tabnet_max_epochs: int = 120
    tabnet_patience: int = 16
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
    ft_max_epochs: int = 140
    ft_patience: int = 18
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
    model_names: list[str] = field(default_factory=lambda: list(DEFAULT_MODELS))

    def resolve_defaults(self) -> None:
        self.label_mode = _validate_label_mode(self.label_mode, allow_auto=True)
        self.split_strategy = _validate_split_strategy(self.split_strategy)
        self.dataset_root = self.dataset_root.resolve()
        self.aligned_csv = resolve_dataset_artifact_path(self.aligned_csv, self.dataset_root)
        self.event_csv = resolve_dataset_artifact_path(self.event_csv, self.dataset_root)
        if self.output_root is None:
            self.output_root = default_training_output_root(self.label_mode)
        else:
            self.output_root = self.output_root.resolve()

    def validate(self) -> None:
        self.resolve_defaults()
        _validate_common_dataset_inputs(
            dataset_root=self.dataset_root,
            aligned_csv=self.aligned_csv,
            event_csv=self.event_csv,
        )
        _validate_experiments(self.experiments)
        if self.min_class_support <= 0:
            raise ValueError("min_class_support must be positive.")
        if not 0.0 < self.min_class_ratio <= 1.0:
            raise ValueError("min_class_ratio must be in (0, 1].")
        total = self.train_ratio + self.validation_ratio + self.test_ratio
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"Split ratios must sum to 1.0, got {total}")
        if self.tabnet_batch_size <= 0 or self.tabnet_virtual_batch_size <= 0:
            raise ValueError("TabNet batch sizes must be positive.")
        if self.tabnet_max_epochs <= 0 or self.tabnet_patience <= 0:
            raise ValueError("TabNet epochs and patience must be positive.")
        if self.tabnet_learning_rate <= 0 or self.tabnet_weight_decay < 0:
            raise ValueError("TabNet learning_rate must be positive and weight_decay non-negative.")
        if self.ft_batch_size <= 0 or self.ft_max_epochs <= 0 or self.ft_patience <= 0:
            raise ValueError("FT-Transformer batch_size, max_epochs, patience must be positive.")
        if self.ft_learning_rate <= 0 or self.ft_weight_decay < 0:
            raise ValueError("FT-Transformer learning_rate must be positive and weight_decay non-negative.")
        if self.ft_model_dim % self.ft_num_heads != 0:
            raise ValueError("ft_model_dim must be divisible by ft_num_heads.")

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["dataset_root"] = str(self.dataset_root)
        payload["aligned_csv"] = str(self.aligned_csv)
        payload["event_csv"] = str(self.event_csv)
        payload["output_root"] = str(self.output_root) if self.output_root else None
        return payload

    def to_build_config(self) -> DirectBenchmarkBuildConfig:
        effective_label_mode = "binary" if self.label_mode == "auto" else self.label_mode
        return DirectBenchmarkBuildConfig(
            dataset_root=self.dataset_root,
            aligned_csv=self.aligned_csv,
            event_csv=self.event_csv,
            output_root=default_dataset_output_root(effective_label_mode),
            experiments=list(self.experiments),
            label_mode=effective_label_mode,
            min_class_support=self.min_class_support,
            min_class_ratio=self.min_class_ratio,
            train_ratio=self.train_ratio,
            validation_ratio=self.validation_ratio,
            test_ratio=self.test_ratio,
            split_strategy=self.split_strategy,
            split_gap_minutes_override=self.split_gap_minutes_override,
        )

    def to_train_config(self, build_run_dir: Path, *, effective_label_mode: str) -> DirectBenchmarkTrainConfig:
        return DirectBenchmarkTrainConfig(
            build_run_dir=build_run_dir.resolve(),
            output_root=default_training_output_root(effective_label_mode),
            experiments=list(self.experiments),
            label_mode=effective_label_mode,
            model_names=list(self.model_names),
            seed=self.seed,
            tabnet_batch_size=self.tabnet_batch_size,
            tabnet_virtual_batch_size=self.tabnet_virtual_batch_size,
            tabnet_max_epochs=self.tabnet_max_epochs,
            tabnet_patience=self.tabnet_patience,
            tabnet_early_stopping_min_delta=self.tabnet_early_stopping_min_delta,
            tabnet_learning_rate=self.tabnet_learning_rate,
            tabnet_weight_decay=self.tabnet_weight_decay,
            tabnet_max_grad_norm=self.tabnet_max_grad_norm,
            tabnet_n_d=self.tabnet_n_d,
            tabnet_n_a=self.tabnet_n_a,
            tabnet_n_steps=self.tabnet_n_steps,
            tabnet_gamma=self.tabnet_gamma,
            tabnet_n_independent=self.tabnet_n_independent,
            tabnet_n_shared=self.tabnet_n_shared,
            tabnet_momentum=self.tabnet_momentum,
            tabnet_mask_type=self.tabnet_mask_type,
            ft_batch_size=self.ft_batch_size,
            ft_max_epochs=self.ft_max_epochs,
            ft_patience=self.ft_patience,
            ft_learning_rate=self.ft_learning_rate,
            ft_weight_decay=self.ft_weight_decay,
            ft_max_grad_norm=self.ft_max_grad_norm,
            ft_token_dim=self.ft_token_dim,
            ft_model_dim=self.ft_model_dim,
            ft_num_heads=self.ft_num_heads,
            ft_num_layers=self.ft_num_layers,
            ft_ffn_multiplier=self.ft_ffn_multiplier,
            ft_dropout=self.ft_dropout,
            ft_attention_dropout=self.ft_attention_dropout,
            ft_residual_dropout=self.ft_residual_dropout,
            ft_classifier_hidden_dim=self.ft_classifier_hidden_dim,
        )
