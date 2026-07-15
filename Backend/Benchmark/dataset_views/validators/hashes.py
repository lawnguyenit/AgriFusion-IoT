from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash_object(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def dataframe_schema_hash(dataframe: pd.DataFrame) -> str:
    schema_payload = [
        {"name": column, "dtype": str(dtype)}
        for column, dtype in dataframe.dtypes.items()
    ]
    return stable_hash_object(schema_payload)


def hash_dataframe_rows(dataframe: pd.DataFrame) -> str:
    return hashlib.sha256(pd.util.hash_pandas_object(dataframe, index=False).values.tobytes()).hexdigest()
