from __future__ import annotations

from pathlib import Path

import pandas as pd


def write_csv_file(dataframe: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(path, index=False)
