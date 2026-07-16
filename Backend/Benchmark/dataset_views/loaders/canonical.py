from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_canonical_history(path: Path) -> pd.DataFrame:
    dataframe = pd.read_csv(path).convert_dtypes()
    if "record.id" not in dataframe.columns:
        raise ValueError("Canonical history is missing required column 'record.id'.")
    return dataframe
