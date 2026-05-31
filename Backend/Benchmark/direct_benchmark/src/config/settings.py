from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from Backend.Benchmark.common.paths import DIRECT_BENCHMARK_ROOT, FUZZY_LOGIC_BASIC_DATASET_ROOT

DEFAULT_DATASET_ROOT = FUZZY_LOGIC_BASIC_DATASET_ROOT
DEFAULT_ALIGNED_CSV = DEFAULT_DATASET_ROOT / "flb_input_aligned.csv"
DEFAULT_EVENT_CSV = DEFAULT_DATASET_ROOT / "flb_input_with_events.csv"
DEFAULT_OUTPUT_ROOT = DIRECT_BENCHMARK_ROOT / "outputs"
DEFAULT_EXPERIMENTS = ["v0", "v1", "v2", "v3", "v4", "v5"]


@dataclass
class DirectBenchmarkConfig:
    benchmark_family: str = "direct_benchmark"
    benchmark_version: str = "direct"
    dataset_root: Path = field(default_factory=lambda: DEFAULT_DATASET_ROOT.resolve())
    aligned_csv: Path = field(default_factory=lambda: DEFAULT_ALIGNED_CSV.resolve())
    event_csv: Path = field(default_factory=lambda: DEFAULT_EVENT_CSV.resolve())
    output_root: Path = field(default_factory=lambda: DEFAULT_OUTPUT_ROOT.resolve())
    experiments: list[str] = field(default_factory=lambda: list(DEFAULT_EXPERIMENTS))
    label_mode: str = "auto"
    min_class_support: int = 20
    min_class_ratio: float = 0.10
    seed: int = 42
    train_ratio: float = 0.70
    validation_ratio: float = 0.15
    test_ratio: float = 0.15
    split_strategy: str = "chronological_with_lookback_gap"
    split_gap_minutes_override: int | None = None
    max_epochs: int = 120
    patience: int = 16
    batch_size: int = 64
    learning_rate: float = 1e-3
    weight_decay: float = 1e-4
    max_grad_norm: float = 1.0
    torch_hidden_dim: int = 64
    torch_dropout: float = 0.20
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
    model_names: list[str] = field(
        default_factory=lambda: [
            "linear_probe",
            "xgboost",
            "tabnet_classifier",
        ]
    )

    def validate(self) -> None:
        if not self.aligned_csv.exists():
            raise FileNotFoundError(f"Aligned CSV not found: {self.aligned_csv}")
        if not self.event_csv.exists():
            raise FileNotFoundError(f"Event CSV not found: {self.event_csv}")
        if not self.dataset_root.exists():
            raise FileNotFoundError(f"Dataset root not found: {self.dataset_root}")
        if not self.experiments:
            raise ValueError("At least one experiment must be selected.")
        allowed = set(DEFAULT_EXPERIMENTS)
        invalid = [name for name in self.experiments if name not in allowed]
        if invalid:
            raise ValueError(f"Unsupported experiments: {invalid}")
        if self.label_mode not in {"auto", "binary", "ternary"}:
            raise ValueError(f"Unsupported label_mode: {self.label_mode}")
        if self.min_class_support <= 0:
            raise ValueError("min_class_support must be positive.")
        if not 0.0 < self.min_class_ratio <= 1.0:
            raise ValueError("min_class_ratio must be in (0, 1].")
        if self.train_ratio <= 0 or self.validation_ratio <= 0 or self.test_ratio <= 0:
            raise ValueError("Split ratios must be positive.")
        total = self.train_ratio + self.validation_ratio + self.test_ratio
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"Split ratios must sum to 1.0, got {total}")
        if self.max_epochs <= 0 or self.patience <= 0:
            raise ValueError("Training epochs and patience must be positive.")
        if self.batch_size <= 0:
            raise ValueError("batch_size must be positive.")
        if self.learning_rate <= 0:
            raise ValueError("learning_rate must be positive.")
        if self.torch_hidden_dim <= 0:
            raise ValueError("torch_hidden_dim must be positive.")
        if self.tabnet_batch_size <= 0 or self.tabnet_virtual_batch_size <= 0:
            raise ValueError("TabNet batch sizes must be positive.")
        if self.tabnet_max_epochs <= 0 or self.tabnet_patience <= 0:
            raise ValueError("TabNet epochs and patience must be positive.")
        if self.tabnet_early_stopping_min_delta < 0.0:
            raise ValueError("TabNet early_stopping_min_delta must be non-negative.")
        if self.tabnet_learning_rate <= 0 or self.tabnet_weight_decay < 0:
            raise ValueError("TabNet learning_rate must be positive and weight_decay non-negative.")
        if self.tabnet_max_grad_norm <= 0:
            raise ValueError("TabNet max_grad_norm must be positive.")
        if self.tabnet_n_d <= 0 or self.tabnet_n_a <= 0 or self.tabnet_n_steps <= 0:
            raise ValueError("TabNet structural widths and steps must be positive.")
        if self.tabnet_gamma <= 1.0:
            raise ValueError("tabnet_gamma must be greater than 1.0.")
        if self.tabnet_n_independent <= 0 or self.tabnet_n_shared <= 0:
            raise ValueError("TabNet shared/independent layer counts must be positive.")
        if self.tabnet_mask_type not in {"sparsemax", "softmax"}:
            raise ValueError("tabnet_mask_type must be sparsemax or softmax.")

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["dataset_root"] = str(self.dataset_root)
        payload["aligned_csv"] = str(self.aligned_csv)
        payload["event_csv"] = str(self.event_csv)
        payload["output_root"] = str(self.output_root)
        return payload
