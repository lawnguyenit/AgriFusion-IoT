from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ProtocolSourceRef:
    protocol_run_dir: Path
    runner_dir: Path
    task_registry_path: Path
    task_manifest_path: Path
    comparison_manifest_path: Path
    frozen_target_manifest_path: Path


@dataclass(frozen=True)
class ModelSuiteRunSpec:
    run_id: str
    output_dir: Path
    profile_name: str
    protocol_source: ProtocolSourceRef
    model_keys: tuple[str, ...]
    stage_specs: tuple[dict[str, object], ...]
    metadata: dict[str, object] = field(default_factory=dict)
