from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ExperimentCheckpoint:
    experiment_name: str
    source_kind: str
    checkpoint_path: Path
    run_dir: Path
    report_path: Path
    config_path: Path


@dataclass
class ExperimentEmbeddingBundle:
    experiment_name: str
    source_kind: str
    dataframe: pd.DataFrame
    feature_columns: list[str]
    embedding_columns: list[str]
    embeddings: np.ndarray
    checkpoint_path: Path
    checkpoint_config: dict[str, object]
    split_counts: dict[str, int]
    split_slices: dict[str, slice]
    embedding_dim: int
    label_merge_report: dict[str, object]
