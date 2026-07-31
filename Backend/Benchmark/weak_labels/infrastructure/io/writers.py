from __future__ import annotations

from pathlib import Path

import pandas as pd

from Backend.Benchmark.shared.artifacts import write_json, write_yaml


def write_parquet(dataframe: pd.DataFrame, path: Path, *, engine: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_parquet(path, index=False, engine=engine)


def write_csv(dataframe: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(path, index=False)


def write_json_file(path: Path, payload: object) -> None:
    write_json(path, payload)


def write_yaml_file(path: Path, payload: object) -> None:
    write_yaml(path, payload)
