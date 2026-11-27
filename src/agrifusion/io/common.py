from __future__ import annotations

from datetime import datetime, timezone, tzinfo
from typing import Any


def safe_float(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int | None = None) -> int | None:
    if value is None or value == "" or isinstance(value, bool):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def iso_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_local_iso(ts_value: int | None, tzinfo: tzinfo) -> str | None:
    if ts_value is None:
        return None
    return datetime.fromtimestamp(ts_value, tz=timezone.utc).astimezone(tzinfo).isoformat()
