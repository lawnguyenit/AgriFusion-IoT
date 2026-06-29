from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from Backend.Benchmark.common.paths import FT_TRANSFORMER_BENCHMARK_ROOT, BENCHMARK_DATASETS_ROOT

DEFAULT_DATASET_ROOT = BENCHMARK_DATASETS_ROOT
DEFAULT_ALIGNED_CSV = DEFAULT_DATASET_ROOT / "benchmark_input_aligned.csv"
DEFAULT_EVENT_CSV = DEFAULT_DATASET_ROOT / "benchmark_input_labeled.csv"
DEFAULT_OUTPUT_ROOT = FT_TRANSFORMER_BENCHMARK_ROOT / "outputs"
DEFAULT_EXPERIMENTS = ["v0", "v1", "v2", "v3", "v4", "v5"]


@dataclass
class FTTransformerBenchmarkConfig:
    benchmark_family: str = "ft_transformer_benchmark"
    benchmark_version: str = "ft_transformer"
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
    model_names: list[str] = field(
        default_factory=lambda: [
            "linear_probe",
            "xgboost",
            "ft_transformer_classifier",
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
        invalid = [name for name in self.experiments if name not in set(DEFAULT_EXPERIMENTS)]
        if invalid:
            raise ValueError(f"Unsupported experiments: {invalid}")
        if self.label_mode not in {"auto", "binary", "ternary"}:
            raise ValueError(f"Unsupported label_mode: {self.label_mode}")
        if self.min_class_support <= 0:
            raise ValueError("min_class_support must be positive.")
        if not 0.0 < self.min_class_ratio <= 1.0:
            raise ValueError("min_class_ratio must be in (0, 1].")
        total = self.train_ratio + self.validation_ratio + self.test_ratio
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"Split ratios must sum to 1.0, got {total}")
        if self.ft_batch_size <= 0 or self.ft_max_epochs <= 0 or self.ft_patience <= 0:
            raise ValueError("FT-Transformer batch_size, max_epochs, patience must be positive.")
        if self.ft_learning_rate <= 0 or self.ft_weight_decay < 0:
            raise ValueError("FT-Transformer learning_rate must be positive and weight_decay non-negative.")
        if self.ft_max_grad_norm <= 0:
            raise ValueError("FT-Transformer max_grad_norm must be positive.")
        if self.ft_token_dim <= 0 or self.ft_model_dim <= 0:
            raise ValueError("FT-Transformer dimensions must be positive.")
        if self.ft_num_heads <= 0 or self.ft_num_layers <= 0:
            raise ValueError("FT-Transformer num_heads and num_layers must be positive.")
        if self.ft_model_dim % self.ft_num_heads != 0:
            raise ValueError("ft_model_dim must be divisible by ft_num_heads.")
        if self.ft_ffn_multiplier <= 1.0:
            raise ValueError("ft_ffn_multiplier must be greater than 1.0.")
        if self.ft_dropout < 0 or self.ft_attention_dropout < 0 or self.ft_residual_dropout < 0:
            raise ValueError("FT-Transformer dropouts must be non-negative.")
        if self.ft_classifier_hidden_dim <= 0:
            raise ValueError("ft_classifier_hidden_dim must be positive.")

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["dataset_root"] = str(self.dataset_root)
        payload["aligned_csv"] = str(self.aligned_csv)
        payload["event_csv"] = str(self.event_csv)
        payload["output_root"] = str(self.output_root)
        return payload
