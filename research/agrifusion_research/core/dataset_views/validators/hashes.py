from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path

import pandas as pd


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_hash_payload(payload: object) -> object:
    if isinstance(payload, Path):
        return str(payload.resolve())
    if is_dataclass(payload):
        return _normalize_hash_payload(asdict(payload))
    if isinstance(payload, dict):
        return {str(key): _normalize_hash_payload(value) for key, value in payload.items()}
    if isinstance(payload, (list, tuple)):
        return [_normalize_hash_payload(value) for value in payload]
    if isinstance(payload, set):
        return sorted(_normalize_hash_payload(value) for value in payload)
    return payload


def stable_hash_object(payload: object) -> str:
    normalized_payload = _normalize_hash_payload(payload)
    encoded = json.dumps(normalized_payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def dataframe_schema_hash(dataframe: pd.DataFrame) -> str:
    schema_payload = [
        {"name": column, "dtype": str(dtype)}
        for column, dtype in dataframe.dtypes.items()
    ]
    return stable_hash_object(schema_payload)


def hash_dataframe_rows(dataframe: pd.DataFrame) -> str:
    return hashlib.sha256(pd.util.hash_pandas_object(dataframe, index=False).values.tobytes()).hexdigest()
