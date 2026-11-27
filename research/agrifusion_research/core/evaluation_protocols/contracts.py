from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EvaluationProtocolConfig:
    protocol_registry_run_dir: Path
    protocol_stage_id: str
    canonical_history_path: Path
    feature_catalog_path: Path
    manifest_path: Path
    segment_manifest_path: Path | None
    dataset_views_run_dir: Path
    native_label_release_dir: Path
    output_root: Path
    execution_profile_path: Path | None = None
    rolling_block_days: int = 7
    initial_train_blocks: int = 3
    validation_blocks: int = 1
    test_blocks: int = 1
    compare_block_days: tuple[int, ...] = (5, 7)
    p2_warm_start_enabled: bool = False
    warmup_duration_hours: int = 48


@dataclass(frozen=True)
class EvaluationProtocolResult:
    run_id: str
    output_dir: Path
    source_row_count: int
    target_row_count: int
