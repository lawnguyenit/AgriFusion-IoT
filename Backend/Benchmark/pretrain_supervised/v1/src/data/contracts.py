from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


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
class EmbeddingBundle:
    dataframe: pd.DataFrame
    feature_columns: list[str]
    embedding_columns: list[str]
    embeddings: np.ndarray
    checkpoint_path: Path
    checkpoint_config: dict[str, object]
    split_counts: dict[str, int]
    split_slices: dict[str, slice]
    split_manifest: dict[str, object]
    embedding_dim: int


@dataclass
class ModelResult:
    model_name: str
    artifact_path: Path
    metrics: dict[str, object]
    available: bool = True
    notes: str = ""
