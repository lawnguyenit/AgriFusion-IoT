from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PretrainAuditConfig:
    feature_matrix_path: Path
    feature_registry_path: Path
    labels_path: Path
    splits_path: Path
    selected_groups: tuple[str, ...]
    target_columns: tuple[str, ...]
    output_root: Path
    max_missing_fraction: float | None = None
    support_gate_path: Path | None = None
    exclude_unknown_targets: bool = False
    training_label_policy: str = "complete_case"


@dataclass(frozen=True)
class PretrainAuditResult:
    run_id: str
    output_dir: Path
    row_count: int
    feature_count: int
    target_count: int
    status: str
