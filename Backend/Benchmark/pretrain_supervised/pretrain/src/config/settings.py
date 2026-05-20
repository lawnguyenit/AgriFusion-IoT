from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path


PRETRAIN_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_ROOT = PRETRAIN_ROOT.parent

DEFAULT_INPUT_CSV = BENCHMARK_ROOT / "fuzzy_logic_basic" / "dataset" / "flb_input_aligned.csv"
DEFAULT_OUTPUT_ROOT = PRETRAIN_ROOT / "outputs"
DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"

DEFAULT_REQUIRED_COLUMNS = [
    "timestamp",
    "soil_temp",
    "soil_humidity",
    "air_temp",
    "air_humidity",
    "EC",
]

DEFAULT_FEATURE_COLUMNS = [
    "soil_temp",
    "soil_humidity",
    "air_temp",
    "air_humidity",
    "EC",
    "hour_sin",
    "hour_cos",
    "dayofweek_sin",
    "dayofweek_cos",
    "gap_minutes_since_prev",
]

OPTIONAL_PROXY_FEATURE = "ec_npk_proxy_index"
DEFAULT_SPLIT_STRATEGY = "chronological_with_lookback_gap"


@dataclass
class PretrainConfig:
    benchmark_family: str = "pretrain_supervised"
    benchmark_version: str = "v1"
    source_kind: str = "layer1"
    input_csv: Path = field(default_factory=lambda: DEFAULT_INPUT_CSV.resolve())
    output_root: Path = field(default_factory=lambda: DEFAULT_OUTPUT_ROOT.resolve())
    timezone: str = DEFAULT_TIMEZONE
    include_npk_proxy: bool = False
    required_columns: list[str] = field(default_factory=lambda: list(DEFAULT_REQUIRED_COLUMNS))
    feature_columns: list[str] = field(default_factory=lambda: list(DEFAULT_FEATURE_COLUMNS))
    optional_proxy_feature: str = OPTIONAL_PROXY_FEATURE
    mask_ratio: float = 0.2
    split_strategy: str = DEFAULT_SPLIT_STRATEGY
    split_gap_minutes_override: int | None = None
    train_ratio: float = 0.70
    validation_ratio: float = 0.15
    test_ratio: float = 0.15
    seed: int = 42
    batch_size: int = 256
    virtual_batch_size: int = 128
    max_epochs: int = 120
    patience: int = 8
    early_stopping_min_delta: float = 1e-3
    learning_rate: float = 2e-3
    weight_decay: float = 1e-5
    max_grad_norm: float = 1.0
    n_d: int = 16
    n_a: int = 16
    n_steps: int = 4
    gamma: float = 1.3
    n_independent: int = 2
    n_shared: int = 2
    n_shared_decoder: int = 1
    n_indep_decoder: int = 1
    momentum: float = 0.02
    mask_type: str = "sparsemax"
    run_label: str = "pretrain"

    def validate(self) -> None:
        if not self.input_csv.exists():
            raise FileNotFoundError(f"Input CSV not found: {self.input_csv}")
        if not 0.0 < self.mask_ratio < 1.0:
            raise ValueError(f"mask_ratio must be in (0, 1), got {self.mask_ratio}")
        if self.train_ratio <= 0 or self.validation_ratio <= 0 or self.test_ratio <= 0:
            raise ValueError("Split ratios must all be positive.")
        total = self.train_ratio + self.validation_ratio + self.test_ratio
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"Split ratios must sum to 1.0, got {total}")
        if self.split_strategy not in {"chronological_v1", "chronological_with_lookback_gap"}:
            raise ValueError(f"Unsupported split_strategy: {self.split_strategy}")
        if self.split_gap_minutes_override is not None and self.split_gap_minutes_override < 0:
            raise ValueError("split_gap_minutes_override must be non-negative when provided.")
        if self.batch_size <= 0 or self.virtual_batch_size <= 0:
            raise ValueError("Batch sizes must be positive.")
        if self.max_epochs <= 0:
            raise ValueError("max_epochs must be positive.")
        if self.early_stopping_min_delta < 0.0:
            raise ValueError("early_stopping_min_delta must be non-negative.")
        if self.include_npk_proxy:
            required_for_proxy = {"EC", "N", "P", "K"}
            if not required_for_proxy.issubset(self.required_columns):
                missing = sorted(required_for_proxy.difference(self.required_columns))
                raise ValueError(
                    "include_npk_proxy requires a schema containing EC, N, P, and K. "
                    f"Missing in current source contract: {missing}"
                )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["input_csv"] = str(self.input_csv)
        payload["output_root"] = str(self.output_root)
        return payload
