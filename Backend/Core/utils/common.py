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


def iso_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_local_iso(ts_value: int | None, tzinfo: tzinfo) -> str | None:
    if ts_value is None:
        return None
    return datetime.fromtimestamp(ts_value, tz=timezone.utc).astimezone(tzinfo).isoformat()


def resolve_window_ts(record: dict[str, Any]) -> int | None:
    """Prefer raw server timestamp so 30-minute window stats keep their resolution."""
    timestamps = record.get("timestamps", {})
    return safe_int(timestamps.get("ts_server"))


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
            "status": "missing",
            "current": None,
            "min": None,
            "max": None,
            "avg": None,
            "delta_from_start": None,
            "trend": "unknown",
            "trend_per_hour": None,
        }

    current = values[-1]
    base_payload = {
        "count": len(values),
        "status": "ready" if len(values) >= 2 else "insufficient_samples",
        "current": round(current, 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "avg": round(sum(values) / len(values), 4),
    }

    if len(values) < 2 or len(timestamps) < 2 or timestamps[-1] <= timestamps[0]:
        return {
            **base_payload,
            "delta_from_start": None,
            "trend": "unknown",
            "trend_per_hour": None,
        }

    start = values[0]
    delta = current - start
    trend_per_hour = None
    if len(timestamps) >= 2 and timestamps[-1] > timestamps[0]:
        hours = (timestamps[-1] - timestamps[0]) / HOUR_SECONDS
        if hours > 0:
            trend_per_hour = round(delta / hours, 4)

    stable_threshold = max(0.15, abs(current) * 0.01)
    return {
        **base_payload,
        "delta_from_start": round(delta, 4),
        "trend": classify_trend(delta, stable_threshold=stable_threshold),
        "trend_per_hour": trend_per_hour,
    }


def build_window_stats(
    records: Sequence[dict[str, Any]],
    observed_ts: int | None,
    metric_keys: Iterable[str],
    window_hours: Iterable[int],
    expected_interval_sec: int = 1800,
    max_regular_gap_sec: int = 2100,
    boundary_tolerance_sec: int = 300,
) -> dict[str, Any]:
    if observed_ts is None:
        return {}

    windows: dict[str, Any] = {}
    for hours in window_hours:
        window_duration_sec = hours * HOUR_SECONDS
        window_start = observed_ts - window_duration_sec
        selection_start = window_start - boundary_tolerance_sec
        expected_sample_count = int(window_duration_sec / expected_interval_sec) + 1
        min_regular_gap_sec = max(1, expected_interval_sec - boundary_tolerance_sec)
        near_duplicate_gap_sec = max(1, expected_interval_sec // 2)

        timestamped_records = sorted(
            (
                (ts, record)
                for record in records
                if (ts := resolve_window_ts(record)) is not None
                and selection_start <= ts <= observed_ts
            ),
            key=lambda item: item[0],
        )
        timestamps = [ts for ts, _ in timestamped_records]
        gaps = [
            later - earlier
            for earlier, later in zip(timestamps, timestamps[1:])
            if later >= earlier
        ]

        regular_gap_count = sum(
            1
            for gap in gaps
            if min_regular_gap_sec <= gap <= max_regular_gap_sec
        )
        short_gap_count = sum(1 for gap in gaps if gap < min_regular_gap_sec)
        large_gap_count = sum(1 for gap in gaps if gap > max_regular_gap_sec)
        near_duplicate_gap_count = sum(1 for gap in gaps if gap < near_duplicate_gap_sec)

        actual_sample_count = len(timestamped_records)
        sample_coverage_ratio = min(actual_sample_count / expected_sample_count, 1.0)
        usable_for_trend = actual_sample_count >= 2
        gap_continuity_ratio = (
            regular_gap_count / len(gaps)
            if gaps
            else (1.0 if usable_for_trend else 0.0)
        )

        window_payload: dict[str, Any] = {
            "count": actual_sample_count,
            "status": "ready" if usable_for_trend else "insufficient_samples",
            "usable_for_trend": usable_for_trend,
            "actual_sample_count": actual_sample_count,
            "expected_sample_count": expected_sample_count,
            "sample_coverage_ratio": round(sample_coverage_ratio, 4),
            "window_start_ts": window_start,
            "window_end_ts": observed_ts,
            "selection_start_ts": selection_start,
            "expected_interval_sec": expected_interval_sec,
            "min_regular_gap_sec": min_regular_gap_sec,
            "max_regular_gap_sec": max_regular_gap_sec,
            "boundary_tolerance_sec": boundary_tolerance_sec,
            "sampling_interval_sec_median": None,
            "min_gap_sec": None,
            "max_gap_sec": None,
            "regular_gap_count": regular_gap_count,
            "short_gap_count": short_gap_count,
            "large_gap_count": large_gap_count,
            "near_duplicate_gap_count": near_duplicate_gap_count,
            "gap_continuity_ratio": round(gap_continuity_ratio, 4),
            "coverage_hours": 0.0,
        }

        if gaps:
            window_payload["sampling_interval_sec_median"] = int(median(gaps))
            window_payload["min_gap_sec"] = int(min(gaps))
            window_payload["max_gap_sec"] = int(max(gaps))
            window_payload["coverage_hours"] = round(
                (timestamps[-1] - timestamps[0]) / HOUR_SECONDS,
                3,
            )

        for metric_key in metric_keys:
            metric_points = [
                (ts, value)
                for ts, record in timestamped_records
                if (value := safe_float(record.get("perception", {}).get(metric_key))) is not None
            ]
            values = [value for _, value in metric_points]
            metric_timestamps = [ts for ts, _ in metric_points]
            window_payload[metric_key] = series_stats(values=values, timestamps=metric_timestamps)

        windows[f"{hours}h"] = window_payload

    return windows


def trim_recent_ids(record_ids: Sequence[str], limit: int = 128) -> list[str]:
    if len(record_ids) <= limit:
        return list(record_ids)
    return list(record_ids[-limit:])
