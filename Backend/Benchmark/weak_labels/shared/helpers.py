from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from Backend.Benchmark.dataset_views.validators.hashes import hash_dataframe_rows as stable_hash_dataframe_rows


LOCAL_TIMEZONE = "Asia/Ho_Chi_Minh"


def coerce_boolean_series(series: pd.Series) -> pd.Series:
    if str(series.dtype) == "boolean":
        return series.fillna(False)
    normalized = series.replace({"true": True, "false": False, "True": True, "False": False})
    return normalized.fillna(False).astype(bool)


def resolve_local_timestamp_series(canonical_df: pd.DataFrame) -> pd.Series:
    timestamps: list[pd.Timestamp] = []
    sample_time_series = canonical_df.get("record.sample_time_local", pd.Series([pd.NA] * len(canonical_df)))
    ts_sample_series = pd.to_numeric(canonical_df.get("record.ts_sample", pd.Series([pd.NA] * len(canonical_df))), errors="coerce")
    for value, ts_sample in zip(sample_time_series.tolist(), ts_sample_series.tolist(), strict=False):
        timestamp = _parse_local_timestamp(value)
        if timestamp is None and pd.notna(ts_sample):
            timestamp = pd.to_datetime(int(ts_sample), unit="s", utc=True).tz_convert(LOCAL_TIMEZONE)
        timestamps.append(timestamp if timestamp is not None else pd.NaT)
    return pd.Series(pd.DatetimeIndex(timestamps), index=canonical_df.index)


def compute_vpd_kpa(temp_series: pd.Series, humidity_series: pd.Series) -> pd.Series:
    temp = pd.to_numeric(temp_series, errors="coerce")
    humidity = pd.to_numeric(humidity_series, errors="coerce")
    es = 0.6108 * np.exp(17.27 * temp / (temp + 237.3))
    vpd = es * (1.0 - (humidity / 100.0))
    return pd.Series(vpd, index=temp_series.index, dtype="Float64")


def local_time_bucket(timestamp_local: pd.Timestamp) -> str:
    if pd.isna(timestamp_local):
        return "unknown"
    hour = int(timestamp_local.hour)
    if 0 <= hour < 8:
        return "00-08"
    if 8 <= hour < 16:
        return "08-16"
    return "16-24"


def json_dumps_compact(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def output_hashes(output_dir: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(output_dir.rglob("*")):
        if path.is_file():
            hashes[str(path.relative_to(output_dir))] = file_sha256(path)
    return hashes


def file_sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_dataframe_rows(dataframe: pd.DataFrame) -> str:
    if dataframe.empty:
        return "empty"
    return stable_hash_dataframe_rows(dataframe.fillna("<NA>"))


def _parse_local_timestamp(value: object) -> pd.Timestamp | None:
    if value is None or value is pd.NA:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    try:
        timestamp = pd.Timestamp(text)
    except Exception:
        return None
    if timestamp.tzinfo is None:
        return timestamp.tz_localize(LOCAL_TIMEZONE)
    return timestamp.tz_convert(LOCAL_TIMEZONE)
