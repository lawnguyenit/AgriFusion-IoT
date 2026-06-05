from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from Backend.Benchmark.common.paths import (
    CONTEXT_CLASSIFIER_ROOT,
    FUZZY_LOGIC_BASIC_DATASET_ROOT,
    SIMULATOR_ROOT,
)
from Backend.Benchmark.shared.artifacts import create_run_directory
from Backend.Benchmark.shared.labels import default_context_build_root, get_label_scheme

DEFAULT_DATASET_ROOT = FUZZY_LOGIC_BASIC_DATASET_ROOT
DEFAULT_REAL_EVENT_CSV = DEFAULT_DATASET_ROOT / "flb_input_with_events.csv"
DEFAULT_WINDOW_SIZES = [3, 8]


def _latest_simulator_run_dir() -> Path:
    outputs_root = (SIMULATOR_ROOT / "outputs").resolve()
    if not outputs_root.exists():
        raise FileNotFoundError(f"Simulator outputs root not found: {outputs_root}")
    candidates = [path for path in outputs_root.iterdir() if path.is_dir()]
    if not candidates:
        raise FileNotFoundError(f"No simulator run directories found under: {outputs_root}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


@dataclass
class ContextClassifierConfig:
    benchmark_family: str = "context_classifier"
    benchmark_version: str = "dataset_builder_v2"
    label_scheme: str = "four_class"
    dataset_root: Path = field(default_factory=lambda: DEFAULT_DATASET_ROOT.resolve())
    real_event_csv: Path = field(default_factory=lambda: DEFAULT_REAL_EVENT_CSV.resolve())
    synthetic_gap_aware_csv: Path | None = None
    output_root: Path | None = None
    window_sizes: list[int] = field(default_factory=lambda: list(DEFAULT_WINDOW_SIZES))
    sequence_lookback: int = 12
    sequence_stride: int = 1
    train_ratio: float = 0.70
    validation_ratio: float = 0.15
    test_ratio: float = 0.15
    purge_gap_minutes: int = 1440
    split_strategy: str = "coverage_aware_temporal"
    seed: int = 42

    def resolve_defaults(self) -> None:
        scheme = get_label_scheme(self.label_scheme)
        self.label_scheme = scheme.name
        if self.output_root is None:
            self.output_root = default_context_build_root(CONTEXT_CLASSIFIER_ROOT, self.label_scheme)
        else:
            self.output_root = self.output_root.resolve()
        latest_run = _latest_simulator_run_dir()
        if self.synthetic_gap_aware_csv is None:
            self.synthetic_gap_aware_csv = (latest_run / "synthetic_flb_gap_aware.csv").resolve()
        else:
            self.synthetic_gap_aware_csv = self.synthetic_gap_aware_csv.resolve()

    def validate(self) -> None:
        self.resolve_defaults()
        if not self.dataset_root.exists():
            raise FileNotFoundError(f"Dataset root not found: {self.dataset_root}")
        if not self.real_event_csv.exists():
            raise FileNotFoundError(
                f"Real event CSV not found: {self.real_event_csv}. "
                "context_classifier requires a labeled real-data artifact with big_label plus telemetry-gap/provenance fields "
                "from fuzzy_logic_basic real-event-labeling. Rebuild "
                "Backend/Benchmark/fuzzy_logic_basic/dataset/flb_input_with_events.csv first, or pass "
                "--real-event-csv <labeled_real_csv> explicitly."
            )
        if self.synthetic_gap_aware_csv is None or not self.synthetic_gap_aware_csv.exists():
            raise FileNotFoundError(f"Synthetic gap-aware CSV not found: {self.synthetic_gap_aware_csv}")
        if not self.window_sizes:
            raise ValueError("At least one window size is required.")
        if any(size <= 0 for size in self.window_sizes):
            raise ValueError("window_sizes must be positive integers.")
        if self.sequence_lookback <= 1:
            raise ValueError("sequence_lookback must be greater than 1.")
        if self.sequence_stride <= 0:
            raise ValueError("sequence_stride must be positive.")
        if self.train_ratio <= 0 or self.validation_ratio <= 0 or self.test_ratio <= 0:
            raise ValueError("Split ratios must be positive.")
        total = self.train_ratio + self.validation_ratio + self.test_ratio
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"Split ratios must sum to 1.0, got {total}")
        if self.purge_gap_minutes < 0:
            raise ValueError("purge_gap_minutes must be non-negative.")
        if self.split_strategy not in {"chronological_with_gap", "coverage_aware_temporal"}:
            raise ValueError(f"Unsupported split_strategy: {self.split_strategy}")

    def make_run_dir(self) -> Path:
        _, run_dir = create_run_directory(self.output_root, prefix="context_build")
        return run_dir

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["dataset_root"] = str(self.dataset_root)
        payload["real_event_csv"] = str(self.real_event_csv)
        payload["synthetic_gap_aware_csv"] = str(self.synthetic_gap_aware_csv) if self.synthetic_gap_aware_csv else None
        payload["output_root"] = str(self.output_root) if self.output_root else None
        return payload
