from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_DIGEST_CONFIG: dict[str, object] = {
    "hash_algorithm": "sha256",
    "canonical_sort_columns": ["sample_id"],
    "column_order": "explicit",
    "null_normalization": "<NA>",
    "datetime_normalization": "iso8601_tz",
    "float_normalization": "12g",
}


def stable_digest(payload: object) -> str:
    normalized_payload = _normalize_scalar(payload)
    encoded = json.dumps(
        normalized_payload,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dataframe_digest(
    dataframe: pd.DataFrame,
    *,
    columns: list[str],
    sort_columns: list[str] | None = None,
    config: dict[str, object] | None = None,
) -> str:
    digest_config = dict(DEFAULT_DIGEST_CONFIG)
    if config:
        digest_config.update(config)
    missing = [column for column in columns if column not in dataframe.columns]
    if missing:
        raise KeyError(f"Missing digest columns: {missing}")
    working = dataframe.loc[:, columns].copy()
    normalized = _normalize_frame(working, digest_config=digest_config)
    if sort_columns:
        normalized = normalized.sort_values(sort_columns, kind="stable").reset_index(drop=True)
    rows = normalized.to_dict(orient="records")
    return stable_digest(
        {
            "config": digest_config,
            "columns": columns,
            "rows": rows,
        }
    )


def population_digest(sample_ids: pd.Series | list[str]) -> str:
    frame = pd.DataFrame({"sample_id": pd.Series(sample_ids, dtype="string")}).convert_dtypes()
    return dataframe_digest(frame, columns=["sample_id"], sort_columns=["sample_id"])


def feature_contract_digest(
    *,
    sample_ids: pd.Series | list[str],
    ordered_feature_names: list[str],
    feature_view_version: str,
) -> str:
    frame = pd.DataFrame({"sample_id": pd.Series(sample_ids, dtype="string")}).convert_dtypes()
    sample_id_digest = dataframe_digest(frame, columns=["sample_id"], sort_columns=["sample_id"])
    return stable_digest(
        {
            "sample_id_digest": sample_id_digest,
            "ordered_feature_names": ordered_feature_names,
            "feature_view_version": feature_view_version,
        }
    )


def _normalize_frame(dataframe: pd.DataFrame, *, digest_config: dict[str, object]) -> pd.DataFrame:
    normalized = dataframe.copy()
    null_token = str(digest_config["null_normalization"])
    float_format = str(digest_config["float_normalization"])
    for column in normalized.columns:
        series = normalized[column]
        normalized[column] = series.map(
            lambda value: _normalize_series_value(
                value,
                null_token=null_token,
                float_format=float_format,
            )
        )
    return normalized.convert_dtypes()


def _normalize_series_value(value: object, *, null_token: str, float_format: str) -> object:
    if value is None or value is pd.NA:
        return null_token
    if isinstance(value, float):
        if pd.isna(value):
            return null_token
        return format(value, float_format)
    if isinstance(value, (pd.Timestamp, datetime)):
        timestamp = pd.Timestamp(value)
        if pd.isna(timestamp):
            return null_token
        if timestamp.tzinfo is None:
            return timestamp.isoformat()
        return timestamp.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return _normalize_scalar(value)


def _normalize_scalar(value: Any) -> Any:
    if value is None or value is pd.NA:
        return "<NA>"
    if isinstance(value, Path):
        return str(value.resolve())
    if is_dataclass(value):
        return _normalize_scalar(asdict(value))
    if isinstance(value, dict):
        return {str(key): _normalize_scalar(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_scalar(item) for item in value]
    if isinstance(value, set):
        return sorted(_normalize_scalar(item) for item in value)
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if pd.isna(value):
            return "<NA>"
        return format(value, "12g")
    if isinstance(value, (pd.Timestamp, datetime)):
        timestamp = pd.Timestamp(value)
        return timestamp.isoformat() if not pd.isna(timestamp) else "<NA>"
    if isinstance(value, date):
        return value.isoformat()
    return value
