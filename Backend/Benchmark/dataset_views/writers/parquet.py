from __future__ import annotations

from pathlib import Path

import pandas as pd


def write_parquet_file(dataframe: pd.DataFrame, path: Path, engine: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_parquet(path, index=False, engine=engine)
