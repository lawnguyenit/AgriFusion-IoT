from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from Backend.Benchmark.common.paths import BENCHMARK_DATASETS_ROOT, PRETRAIN_ROOT, PRETRAIN_SUPERVISED_ROOT

V3_ROOT = PRETRAIN_SUPERVISED_ROOT / "v3"

DEFAULT_EVENT_CSV = BENCHMARK_DATASETS_ROOT / "benchmark_input_labeled.csv"
DEFAULT_OUTPUT_ROOT = V3_ROOT / "outputs"
DEFAULT_PRETRAIN_OUTPUT_ROOTS = [
    PRETRAIN_ROOT / "outputs",
    PRETRAIN_ROOT / "outputs" / "pretrain",
]
DEFAULT_EXPERIMENTS = ["combo1", "combo2", "combo3", "combo4"]
DEFAULT_SKLEARN_MODEL_NAMES = ["linear_probe", "xgboost"]
ALLOWED_SKLEARN_MODEL_NAMES = {
    "linear_probe",
    "random_forest",
    "hist_gradient_boosting",
    "xgboost",
    "lightgbm",
}


@dataclass
class V3Config:
    benchmark_family: str = "pretrain_supervised"
    benchmark_version: str = "v3"
    event_csv: Path = field(default_factory=lambda: DEFAULT_EVENT_CSV.resolve())
    output_root: Path = field(default_factory=lambda: DEFAULT_OUTPUT_ROOT.resolve())
    pretrain_output_roots: list[Path] = field(default_factory=lambda: [path.resolve() for path in DEFAULT_PRETRAIN_OUTPUT_ROOTS])
    experiments: list[str] = field(default_factory=lambda: list(DEFAULT_EXPERIMENTS))
    label_mode: str = "auto"
    min_class_support: int = 20
    min_class_ratio: float = 0.10
    seed: int = 42
    train_ratio: float = 0.70
    validation_ratio: float = 0.15
    test_ratio: float = 0.15
    max_epochs: int = 100
    patience: int = 8
    batch_size: int = 64
    learning_rate: float = 1e-3
    weight_decay: float = 1e-4
    max_grad_norm: float = 1.0
    torch_hidden_dim: int = 64
    torch_dropout: float = 0.20
    model_names: list[str] = field(
        default_factory=lambda: list(DEFAULT_SKLEARN_MODEL_NAMES)
    )

    def validate(self) -> None:
        if not self.event_csv.exists():
            raise FileNotFoundError(f"Event CSV not found: {self.event_csv}")
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
        invalid_model_names = [name for name in self.model_names if name not in ALLOWED_SKLEARN_MODEL_NAMES]
        if invalid_model_names:
            raise ValueError(f"Unsupported sklearn model_names: {invalid_model_names}")

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["event_csv"] = str(self.event_csv)
        payload["output_root"] = str(self.output_root)
        payload["pretrain_output_roots"] = [str(path) for path in self.pretrain_output_roots]
        return payload
