from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_feature_catalog(path: Path) -> pd.DataFrame:
    dataframe = pd.read_csv(path).convert_dtypes()
    if "canonical_name" not in dataframe.columns:
        raise ValueError("Feature catalog is missing required column 'canonical_name'.")
    return dataframe
