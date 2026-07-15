from __future__ import annotations

from pathlib import Path

import pandas as pd

from Backend.Benchmark.dataset_views.contracts import LabelConfig


def load_label_artifact(config: LabelConfig) -> pd.DataFrame:
    path = config.artifact_path
    if not path.exists():
        raise FileNotFoundError(f"Label artifact not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".parquet":
        dataframe = pd.read_parquet(path)
    elif suffix == ".csv":
        dataframe = pd.read_csv(path)
    else:
        raise ValueError(f"Unsupported label artifact format '{path.suffix}'. Use .parquet or .csv.")

    dataframe = dataframe.convert_dtypes()
    if config.key_column not in dataframe.columns:
        raise ValueError(f"Label artifact must contain key column '{config.key_column}'.")

    required_columns = [column for column in config.required_columns if column not in dataframe.columns]
    if required_columns:
        raise ValueError(
            "Label artifact is missing required label columns: "
            + ", ".join(sorted(required_columns))
        )

    return dataframe
