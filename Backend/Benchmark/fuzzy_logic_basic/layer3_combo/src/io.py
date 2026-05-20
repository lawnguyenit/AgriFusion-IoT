from __future__ import annotations

from pathlib import Path

import pandas as pd

from Backend.Benchmark.fuzzy_logic_basic.layer3_combo.src.config import DEFAULT_INPUT_CSV, DEFAULT_OUTPUT_DIR
from Backend.Config.IO.io_csv import load_csv, write_csv


def resolve_input_csv(input_csv: Path | None) -> Path:
    return (input_csv or DEFAULT_INPUT_CSV).resolve()


def resolve_output_dir(output_dir: Path | None) -> Path:
    return (output_dir or DEFAULT_OUTPUT_DIR).resolve()


def load_layer1_frame(input_csv: Path | None = None) -> pd.DataFrame:
    path = resolve_input_csv(input_csv)
    return load_csv(path)


def write_layer3_combo_csv(dataframe: pd.DataFrame, output_path: Path) -> None:
    write_csv(dataframe, output_path)

