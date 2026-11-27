from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MultiLabelRunConfig:
    audit_dir: Path
    target_columns: tuple[str, ...]
    model_key: str
    output_root: Path
    random_seed: int = 20260929
    thread_count: int = 1
    probability_threshold: float = 0.5
    hyperparameter_overrides: dict[str, object] | None = None
    use_balanced_sample_weight: bool | None = None
    evaluation_partitions: tuple[str, ...] = ("validation", "test")
    require_observable_features: bool = False


@dataclass(frozen=True)
class MultiLabelRunResult:
    run_id: str
    output_dir: Path
    status: str
    fold_count: int
    head_count: int
