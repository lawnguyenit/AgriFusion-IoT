from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path


TABNET_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_ROOT = TABNET_ROOT.parent

DEFAULT_INPUT_CSV = BENCHMARK_ROOT / "fuzzy_logic_basic" / "dataset" / "flb_input_aligned.csv"
DEFAULT_OUTPUT_ROOT = TABNET_ROOT / "outputs" / "pretrain"
DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"

DEFAULT_FEATURE_COLUMNS = [
    "soil_temp",
    "soil_humidity",
    "air_temp",
    "air_humidity",
    "EC",
    "pH",
    "hour_sin",
    "hour_cos",
    "dayofweek_sin",
    "dayofweek_cos",
    "gap_minutes_since_prev",
]

OPTIONAL_PROXY_FEATURE = "ec_npk_proxy_index"
RAW_REQUIRED_COLUMNS = [
    "timestamp",
    "soil_temp",
    "soil_humidity",
    "air_temp",
    "air_humidity",
    "EC",
    "pH",
    "N",
    "P",
    "K",
    "ec_npk_consistency_score",
    "ec_npk_consistency_flag",
]


@dataclass
class PretrainConfig:
    source_kind: str = "layer1"
    input_csv: Path = field(default_factory=lambda: DEFAULT_INPUT_CSV.resolve())
    output_root: Path = field(default_factory=lambda: DEFAULT_OUTPUT_ROOT.resolve())
    timezone: str = DEFAULT_TIMEZONE
    include_npk_proxy: bool = False
    feature_columns: list[str] = field(default_factory=lambda: list(DEFAULT_FEATURE_COLUMNS))
    optional_proxy_feature: str = OPTIONAL_PROXY_FEATURE
    mask_ratio: float = 0.2
    train_ratio: float = 0.70
    validation_ratio: float = 0.15
    test_ratio: float = 0.15
    seed: int = 42
    batch_size: int = 256
    virtual_batch_size: int = 128
    max_epochs: int = 40
    patience: int = 8
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
        if self.batch_size <= 0 or self.virtual_batch_size <= 0:
            raise ValueError("Batch sizes must be positive.")
        if self.max_epochs <= 0:
            raise ValueError("max_epochs must be positive.")

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["input_csv"] = str(self.input_csv)
        payload["output_root"] = str(self.output_root)
        return payload
