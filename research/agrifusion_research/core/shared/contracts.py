from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class LabelPolicyResult:
    label_mode: str
    label_column: str
    label_id_column: str
    class_names: list[str]
    class_to_id: dict[str, int]
    class_counts: dict[str, int]
    diagnostics: dict[str, object]


@dataclass
class ModelResult:
    model_name: str
    artifact_path: Path
    metrics: dict[str, object]
    available: bool = True
    notes: str = ""
