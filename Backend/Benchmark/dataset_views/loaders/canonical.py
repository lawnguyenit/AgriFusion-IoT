from __future__ import annotations

from pathlib import Path

import pandas as pd

from Backend.Config.storage import read_table


def load_canonical_history(path: Path) -> pd.DataFrame:
    dataframe = read_table(path).convert_dtypes()
    if "record.id" not in dataframe.columns:
        raise ValueError("Canonical history is missing required column 'record.id'.")
    return dataframe
