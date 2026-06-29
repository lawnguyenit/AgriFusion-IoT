from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

@dataclass
class DirectExperimentResult:
    experiment_name: str
    source_kind: str
    best_model_name: str
    best_validation_macro_f1: float
    output_dir: Path
    report_path: Path
    metrics_path: Path


@dataclass
class DirectModelResult:
    model_name: str
    artifact_path: Path
    metrics: dict[str, object]
    available: bool = True
    notes: str = ""
