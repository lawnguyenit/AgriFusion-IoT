from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler


@dataclass
class PreparedDataset:
    dataframe: pd.DataFrame
    feature_columns: list[str]
    split_counts: dict[str, int]
    row_counts: dict[str, int]
    removal_counts: dict[str, int]
    quality_report: dict[str, object]
    split_slices: dict[str, slice]


@dataclass
class ScaledSplitData:
    train_features: np.ndarray
    validation_features: np.ndarray
    test_features: np.ndarray
    scaler: StandardScaler

    @property
    def split_shapes(self) -> dict[str, list[int]]:
        return {
            "train": [int(value) for value in self.train_features.shape],
            "validation": [int(value) for value in self.validation_features.shape],
            "test": [int(value) for value in self.test_features.shape],
        }


@dataclass
class DataPipelineArtifacts:
    cleaned_input_path: Path
    feature_schema_path: Path
    scaler_path: Path
    scaler_stats_path: Path


@dataclass
class DataPipelineResult:
    prepared_dataset: PreparedDataset
    scaled_splits: ScaledSplitData
    feature_schema: dict[str, object]
    artifacts: DataPipelineArtifacts
