from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from Backend.Benchmark.common.paths import TABPFN_BENCHMARK_ROOT, FUZZY_LOGIC_BASIC_DATASET_ROOT

DEFAULT_DATASET_ROOT = FUZZY_LOGIC_BASIC_DATASET_ROOT
DEFAULT_ALIGNED_CSV = DEFAULT_DATASET_ROOT / "flb_input_aligned.csv"
DEFAULT_EVENT_CSV = DEFAULT_DATASET_ROOT / "flb_input_with_events.csv"
DEFAULT_OUTPUT_ROOT = TABPFN_BENCHMARK_ROOT / "outputs"
DEFAULT_EXPERIMENTS = ["v0", "v1", "v2", "v3", "v4", "v5"]


@dataclass
class TabPFNBenchmarkConfig:
    benchmark_family: str = "tabpfn_benchmark"
    benchmark_version: str = "tabpfn"
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
    tabpfn_model_path: str = "tabpfn-v2-classifier-v2_default.ckpt"
    tabpfn_device: str = "auto"
    tabpfn_fit_mode: str = "fit_preprocessors"
    tabpfn_inference_config: str = "auto"
    model_names: list[str] = field(
        default_factory=lambda: [
            "linear_probe",
            "xgboost",
            "tabpfn_classifier",
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
        if not isinstance(self.tabpfn_model_path, str) or not self.tabpfn_model_path.strip():
            raise ValueError("tabpfn_model_path must be a non-empty string.")
        if self.tabpfn_device not in {"auto", "cpu", "cuda"}:
            raise ValueError(f"Unsupported tabpfn_device: {self.tabpfn_device}")
        if self.tabpfn_fit_mode not in {"fit_preprocessors", "low_memory", "batched"}:
            raise ValueError(f"Unsupported tabpfn_fit_mode: {self.tabpfn_fit_mode}")
        if self.tabpfn_inference_config not in {"auto", "low_memory", "fast"}:
            raise ValueError(f"Unsupported tabpfn_inference_config: {self.tabpfn_inference_config}")

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["dataset_root"] = str(self.dataset_root)
        payload["aligned_csv"] = str(self.aligned_csv)
        payload["event_csv"] = str(self.event_csv)
        payload["output_root"] = str(self.output_root)
        return payload
