from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_input_dataframe(csv_path: Path) -> pd.DataFrame:
    return pd.read_csv(csv_path)
