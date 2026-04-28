from __future__ import annotations

from datetime import datetime, timezone, tzinfo
from statistics import median
from typing import Any, Iterable, Sequence

HOUR_SECONDS = 3600


def safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def iso_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_local_iso(ts_value: int | None, tzinfo: tzinfo) -> str | None:
    if ts_value is None:
        return None
    return datetime.fromtimestamp(ts_value, tz=timezone.utc).astimezone(tzinfo).isoformat()


def floor_ts_to_hour(ts_value: int | None) -> int | None:
    if ts_value is None:
        return None
    return int(ts_value // HOUR_SECONDS) * HOUR_SECONDS


def resolve_window_ts(record: dict[str, Any]) -> int | None:
    timestamps = record.get("timestamps", {})
    return safe_int(timestamps.get("ts_hour_bucket")) or safe_int(timestamps.get("ts_server"))


def classify_trend(delta: float | None, stable_threshold: float) -> str:
    if delta is None:
        return "unknown"
    if abs(delta) <= stable_threshold:
        return "stable"
    return "rising" if delta > 0 else "falling"


def series_stats(values: Sequence[float], timestamps: Sequence[int]) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "current": None,
            "min": None,
            "max": None,
            "avg": None,
            "delta_from_start": None,
            "trend": "unknown",
            "trend_per_hour": None,
        }

    current = values[-1]
    start = values[0]
    delta = current - start
    trend_per_hour = None
    if len(timestamps) >= 2 and timestamps[-1] > timestamps[0]:
        hours = (timestamps[-1] - timestamps[0]) / 3600.0
        if hours > 0:
            trend_per_hour = round(delta / hours, 4)

    stable_threshold = max(0.15, abs(current) * 0.01)
    return {
        "count": len(values),
        "current": round(current, 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "avg": round(sum(values) / len(values), 4),
        "delta_from_start": round(delta, 4),
        "trend": classify_trend(delta, stable_threshold=stable_threshold),
        "trend_per_hour": trend_per_hour,
    }


def build_window_stats(
    records: Sequence[dict[str, Any]],
    observed_ts: int | None,
    metric_keys: Iterable[str],
    window_hours: Iterable[int],
) -> dict[str, Any]:
    if observed_ts is None:
        return {}

    windows: dict[str, Any] = {}
    for hours in window_hours:
        window_start = observed_ts - (hours * 3600)
        subset = [
            record
            for record in records   
            if (ts := resolve_window_ts(record)) is not None
            and ts >= window_start
        ]
        timestamps = [
            resolve_window_ts(record)
            for record in subset
            if resolve_window_ts(record) is not None
        ]
        window_payload: dict[str, Any] = {
            "count": len(subset),
            "sampling_interval_sec_median": None,
            "coverage_hours": 0.0,
        }

        if len(timestamps) >= 2 and timestamps[-1] is not None and timestamps[0] is not None:
            gaps = [
                later - earlier
                for earlier, later in zip(timestamps, timestamps[1:])
                if later is not None and earlier is not None and later >= earlier
            ]
            if gaps:
                window_payload["sampling_interval_sec_median"] = int(median(gaps))
                window_payload["coverage_hours"] = round(
                    (timestamps[-1] - timestamps[0]) / 3600.0,
                    3,
                )

        for metric_key in metric_keys:
            values = [
                v
                for record in subset
                if (v := safe_float(record.get("perception", {}).get(metric_key))) is not None
            ]
            metric_timestamps = [
                ts
                for record in subset
                if safe_float(record.get("perception", {}).get(metric_key)) is not None
                and (ts := resolve_window_ts(record)) is not None
            ]
            window_payload[metric_key] = series_stats(values=values, timestamps=metric_timestamps)

        windows[f"{hours}h"] = window_payload

    return windows


def severity_from_confidence(confidence: float) -> str:
    if confidence >= 0.85:
        return "info"
    if confidence >= 0.65:
        return "low"
    if confidence >= 0.4:
        return "medium"
    return "high"


def trim_recent_ids(record_ids: Sequence[str], limit: int = 128) -> list[str]:
    if len(record_ids) <= limit:
        return list(record_ids)
    return list(record_ids[-limit:])


def summarize_issues(issues: Sequence[str], fallback: str) -> str:
    if not issues:
        return fallback
    if len(issues) == 1:
        return issues[0]
    return "; ".join(issues[:3])
