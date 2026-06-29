from __future__ import annotations

from pathlib import Path

import pandas as pd

from Backend.Benchmark.common.artifact_paths import resolve_dataset_artifact
from Backend.Benchmark.benchmark_dataset.single_window_features.src.config import DEFAULT_INPUT_CSV, DEFAULT_OUTPUT_DIR
from Backend.Config.IO.io_csv import load_csv, write_csv


def resolve_input_csv(input_csv: Path | None) -> Path:
    if input_csv is not None:
        return input_csv.resolve()
    return resolve_dataset_artifact(DEFAULT_OUTPUT_DIR, DEFAULT_INPUT_CSV.name)


def resolve_output_dir(output_dir: Path | None) -> Path:
    return (output_dir or DEFAULT_OUTPUT_DIR).resolve()


def load_layer1_frame(input_csv: Path | None = None) -> pd.DataFrame:
    path = resolve_input_csv(input_csv)
    return load_csv(path)


def write_single_window_csv(dataframe: pd.DataFrame, output_path: Path) -> None:
    write_csv(dataframe, output_path)
