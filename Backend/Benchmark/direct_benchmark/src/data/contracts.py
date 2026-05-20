from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class DirectDataBundle:
    dataframe: pd.DataFrame
    feature_columns: list[str]
    source_kind: str
    source_csv: Path
    source_csvs: list[Path]
    split_counts: dict[str, int]
    split_slices: dict[str, slice]
    split_manifest: dict[str, object]
    row_count: int


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
