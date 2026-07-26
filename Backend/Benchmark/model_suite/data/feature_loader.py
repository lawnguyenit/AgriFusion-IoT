from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def load_feature_frame(registry_row: pd.Series, feature_cache: dict[str, pd.DataFrame]) -> pd.DataFrame:
    feature_source_view_id = str(registry_row["feature_source_view_id"])
    cached = feature_cache.get(feature_source_view_id)
    if cached is not None:
        return cached
    x_path = Path(str(registry_row["feature_artifact_path"]))
    row_index_path = Path(str(registry_row["row_index_path"]))
    x_frame = pd.read_parquet(x_path)
    row_index = pd.read_parquet(row_index_path, columns=["record.id"]).convert_dtypes()
    if len(x_frame) != len(row_index):
        raise ValueError(
            f"Feature artifact row count does not match row_index for {feature_source_view_id}: "
            f"{len(x_frame)} != {len(row_index)}."
        )
    feature_frame = x_frame.copy()
    feature_frame.insert(0, "sample_id", row_index["record.id"].astype("string"))
    feature_cache[feature_source_view_id] = feature_frame
    return feature_frame


def extract_partition_matrix(
    feature_frame: pd.DataFrame,
    partition_rows: pd.DataFrame,
    allowed_feature_columns: list[str],
) -> dict[str, object]:
    ordered_sample_ids = partition_rows["sample_id"].astype("string").tolist()
    indexed = feature_frame.set_index("sample_id", drop=False)
    subset = indexed.loc[ordered_sample_ids].copy().reset_index(drop=True)
    return {
        "features": subset.loc[:, allowed_feature_columns].to_numpy(dtype=np.float32),
        "labels": partition_rows["label_name"].astype("string").reset_index(drop=True),
    }


def parse_allowed_feature_columns(registry_row: pd.Series) -> list[str]:
    return json.loads(str(registry_row["allowed_feature_columns_json"]))
