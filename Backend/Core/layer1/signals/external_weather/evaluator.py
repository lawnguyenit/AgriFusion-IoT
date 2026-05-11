from __future__ import annotations

from math import exp
from typing import Any, Mapping, Sequence

HOUR_SECONDS = 3600
WINDOW_HOURS = (1, 3, 6, 24, 72)


def evaluate_external_weather(
    meteo_snapshot: Mapping[str, Any],
    history_records: Sequence[Mapping[str, Any]] | None = None,
    microclimate_records: Sequence[Mapping[str, Any]] | None = None,
    relation_tolerance_sec: int = 2 * HOUR_SECONDS,
) -> dict[str, Any]:
    records = _timestamped_records([*(history_records or []), meteo_snapshot])
    current_ts = _resolve_ts(meteo_snapshot)
    current = _perception(meteo_snapshot)
    nearest_micro = _nearest_record(
        records=microclimate_records or [],
        observed_ts=current_ts,
        tolerance_sec=relation_tolerance_sec,
    )

    return {
        "schema_version": 1,
        "layer": "external_weather_signals",
        "source_object": "meteo",
        "window_hours": list(WINDOW_HOURS),
        "ts": current_ts,
        "signals": {
            "wetness_background": _wetness_background(records=records, current=current),
            "rain_event_context": _rain_event_context(records=records, current_ts=current_ts),
            "drying_demand": _drying_demand(records=records, current=current),
            "heat_cold_background": _heat_cold_background(records=records, current=current),
            "macro_micro_relation": _macro_micro_relation(
                meteo_snapshot=meteo_snapshot,
                micro_snapshot=nearest_micro,
                tolerance_sec=relation_tolerance_sec,
            ),
        },
    }


def _timestamped_records(records: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return sorted(
        [record for record in records if _resolve_ts(record) is not None],
        key=lambda record: _resolve_ts(record) or 0,
    )


def _window_records(
    records: Sequence[Mapping[str, Any]],
    current_ts: float | None,
    hours: int,
) -> list[Mapping[str, Any]]:
    if current_ts is None:
        return []
    start_ts = current_ts - (hours * HOUR_SECONDS)
    return [
        record
        for record in records
        if (ts := _resolve_ts(record)) is not None and start_ts <= ts <= current_ts
    ]


def _wetness_background(
    records: Sequence[Mapping[str, Any]],
    current: Mapping[str, Any],
) -> dict[str, Any]:
    current_ts = _resolve_ts(records[-1]) if records else None
    wetness_by_window: dict[str, Any] = {}
    for hours in (3, 6, 24, 72):
        subset = _window_records(records=records, current_ts=current_ts, hours=hours)
        humidity_avg = _avg(_values(subset, "humidity_air_pct"))
        dew_point_avg = _avg(_values(subset, "dew_point_c"))
        cloud_avg = _avg(_values(subset, "cloud_cover_pct"))
        score = _mean_present(
            _scale(humidity_avg, low=75, high=95),
            _scale(dew_point_avg, low=23, high=27),
            _scale(cloud_avg, low=70, high=95),
        )
        wetness_by_window[f"{hours}h"] = {
            "score": _round(score),
            "level": _level(score),
            "humidity_avg_pct": _round(humidity_avg),
            "dew_point_avg_c": _round(dew_point_avg),
            "cloud_cover_avg_pct": _round(cloud_avg),
            "sample_count": len(subset),
        }

    current_score = _mean_present(
        _scale(_safe_float(current.get("humidity_air_pct")), low=75, high=95),
        _scale(_safe_float(current.get("dew_point_c")), low=23, high=27),
        _scale(_safe_float(current.get("cloud_cover_pct")), low=70, high=95),
    )
    return {
        "score": _round(current_score),
        "level": _level(current_score),
        "windows": wetness_by_window,
    }


def _rain_event_context(
    records: Sequence[Mapping[str, Any]],
    current_ts: float | None,
) -> dict[str, Any]:
    windows: dict[str, Any] = {}
    for hours in WINDOW_HOURS:
        subset = _window_records(records=records, current_ts=current_ts, hours=hours)
        rain_values = _values(subset, "rain_mm")
        precipitation_values = _values(subset, "precipitation_mm")
        rain_sum = sum(rain_values)
        precipitation_sum = sum(precipitation_values)
        total_mm = max(rain_sum, precipitation_sum)
        score = _scale(total_mm, low=0.2, high=10.0)
        windows[f"{hours}h"] = {
            "total_mm": _round(total_mm),
            "rain_mm_sum": _round(rain_sum),
            "precipitation_mm_sum": _round(precipitation_sum),
            "score": _round(score),
            "level": _level(score),
            "sample_count": len(subset),
        }
    rain_now = _safe_float(_perception(records[-1]).get("rain_mm")) if records else None
    precipitation_now = _safe_float(_perception(records[-1]).get("precipitation_mm")) if records else None
    return {
        "is_raining_now": max(rain_now or 0.0, precipitation_now or 0.0) > 0.0,
        "windows": windows,
    }


def _drying_demand(
    records: Sequence[Mapping[str, Any]],
    current: Mapping[str, Any],
) -> dict[str, Any]:
    current_vpd = _vpd_kpa(
        temp_c=_safe_float(current.get("temp_air_c")),
        humidity_pct=_safe_float(current.get("humidity_air_pct")),
    )
    et0_current = _safe_float(current.get("et0_mm"))
    score = _mean_present(
        _scale(current_vpd, low=0.8, high=2.0),
        _scale(et0_current, low=0.15, high=0.45),
        _scale(100.0 - (_safe_float(current.get("cloud_cover_pct")) or 100.0), low=20, high=80),
    )

    current_ts = _resolve_ts(records[-1]) if records else None
    windows: dict[str, Any] = {}
    for hours in (3, 6, 24, 72):
        subset = _window_records(records=records, current_ts=current_ts, hours=hours)
        vpd_values = [
            value
            for record in subset
            if (
                value := _vpd_kpa(
                    temp_c=_safe_float(_perception(record).get("temp_air_c")),
                    humidity_pct=_safe_float(_perception(record).get("humidity_air_pct")),
                )
            )
            is not None
        ]
        et0_values = _values(subset, "et0_mm")
        windows[f"{hours}h"] = {
            "vpd_avg_kpa": _round(_avg(vpd_values)),
            "et0_sum_mm": _round(sum(et0_values)),
            "sample_count": len(subset),
        }

    return {
        "score": _round(score),
        "level": _level(score),
        "vpd_current_kpa": _round(current_vpd),
        "et0_current_mm": _round(et0_current),
        "windows": windows,
    }


def _heat_cold_background(
    records: Sequence[Mapping[str, Any]],
    current: Mapping[str, Any],
) -> dict[str, Any]:
    current_temp = _safe_float(current.get("temp_air_c"))
    heat_score = _scale(current_temp, low=32, high=38)
    cold_score = _scale(None if current_temp is None else 18 - current_temp, low=0, high=8)

    current_ts = _resolve_ts(records[-1]) if records else None
    windows: dict[str, Any] = {}
    for hours in (3, 6, 24, 72):
        subset = _window_records(records=records, current_ts=current_ts, hours=hours)
        temps = _values(subset, "temp_air_c")
        temp_avg = _avg(temps)
        windows[f"{hours}h"] = {
            "temp_avg_c": _round(temp_avg),
            "heat_score": _round(_scale(temp_avg, low=32, high=38)),
            "cold_score": _round(_scale(None if temp_avg is None else 18 - temp_avg, low=0, high=8)),
            "sample_count": len(subset),
        }

    return {
        "state": "heat" if (heat_score or 0.0) > (cold_score or 0.0) else "cold" if (cold_score or 0.0) > 0 else "normal",
        "heat_score": _round(heat_score),
        "cold_score": _round(cold_score),
        "level": _level(max(heat_score or 0.0, cold_score or 0.0)),
        "windows": windows,
    }


def _macro_micro_relation(
    meteo_snapshot: Mapping[str, Any],
    micro_snapshot: Mapping[str, Any] | None,
    tolerance_sec: int,
) -> dict[str, Any]:
    meteo_ts = _resolve_ts(meteo_snapshot)
    if micro_snapshot is None or meteo_ts is None:
        return {
            "status": "missing_microclimate_reference",
            "relation_tolerance_sec": tolerance_sec,
        }

    micro_ts = _resolve_ts(micro_snapshot)
    meteo = _perception(meteo_snapshot)
    micro = _perception(micro_snapshot)
    temp_delta = _subtract(
        _safe_float(micro.get("temp_air_c")),
        _safe_float(meteo.get("temp_air_c")),
    )
    humidity_delta = _subtract(
        _safe_float(micro.get("humidity_air_pct")),
        _safe_float(meteo.get("humidity_air_pct")),
    )
    abs_temp_delta = None if temp_delta is None else abs(temp_delta)
    abs_humidity_delta = None if humidity_delta is None else abs(humidity_delta)
    divergence_score = _mean_present(
        _scale(abs_temp_delta, low=1.5, high=5.0),
        _scale(abs_humidity_delta, low=8.0, high=25.0),
    )
    time_delta_sec = None if micro_ts is None else int(abs(meteo_ts - micro_ts))

    return {
        "status": "ready",
        "relation_tolerance_sec": tolerance_sec,
        "time_delta_sec": time_delta_sec,
        "micro_ts": micro_ts,
        "meteo_ts": meteo_ts,
        "temp_delta_micro_minus_meteo_c": _round(temp_delta),
        "humidity_delta_micro_minus_meteo_pct": _round(humidity_delta),
        "divergence_score": _round(divergence_score),
        "level": _level(divergence_score),
    }


def _nearest_record(
    records: Sequence[Mapping[str, Any]],
    observed_ts: float | None,
    tolerance_sec: int,
) -> Mapping[str, Any] | None:
    if observed_ts is None:
        return None
    candidates = [
        (abs(observed_ts - ts), record)
        for record in records
        if (ts := _resolve_ts(record)) is not None and abs(observed_ts - ts) <= tolerance_sec
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[0])[1]


def _perception(record: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = record.get("perception")
    return payload if isinstance(payload, Mapping) else {}


def _values(records: Sequence[Mapping[str, Any]], metric_key: str) -> list[float]:
    return [
        value
        for record in records
        if (value := _safe_float(_perception(record).get(metric_key))) is not None
    ]


def _resolve_ts(record: Mapping[str, Any]) -> float | None:
    timestamps = record.get("timestamps")
    if isinstance(timestamps, Mapping):
        value = _safe_float(timestamps.get("ts_server"))
        if value is not None:
            return value
    return _safe_float(record.get("ts_server"))


def _vpd_kpa(temp_c: float | None, humidity_pct: float | None) -> float | None:
    if temp_c is None or humidity_pct is None:
        return None
    saturation = 0.6108 * exp((17.27 * temp_c) / (temp_c + 237.3))
    return saturation * (1.0 - max(0.0, min(humidity_pct, 100.0)) / 100.0)


def _scale(value: float | None, low: float, high: float) -> float | None:
    if value is None:
        return None
    if high <= low:
        return 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def _mean_present(*values: float | None) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present) / len(present)


def _avg(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _subtract(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left - right


def _level(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score >= 0.75:
        return "high"
    if score >= 0.4:
        return "moderate"
    if score > 0:
        return "low"
    return "none"


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(value, digits)
