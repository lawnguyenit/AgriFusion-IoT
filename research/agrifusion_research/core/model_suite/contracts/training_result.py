from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TabularTrainingResult:
    class_names: list[str]
    evaluation_predictions: dict[str, list[int]]
    evaluation_probabilities: dict[str, list[list[float]] | None]
    selected_feature_names: list[str]
    preprocessing_metadata: dict[str, object]
    model_metadata: dict[str, object]
    artifact_paths: dict[str, str]
    output_dir: Path
