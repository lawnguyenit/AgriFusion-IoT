from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class SignalRule:
    name: str
    field: str
    normal_low: float
    normal_high: float
    threshold_low: float | None = None
    threshold_high: float | None = None
    direction: str = "both"
    alpha: float = 0.25
    confidence: float = 0.95
    unit: str | None = None
    description: str | None = None


def evaluate_signal_rules(
    source_object: str,
    sample: Mapping[str, Any],
    history: Sequence[Mapping[str, Any]] | None,
    previous_signals: Mapping[str, Any] | None,
    rules: Sequence[SignalRule],
    aliases: Mapping[str, Sequence[str]],
    window_hours: Sequence[int],
    ruleset_version: str,
) -> dict[str, Any]:
    current = _normalize_record(sample=sample, aliases=aliases)
    history_records = [
        _normalize_record(sample=record, aliases=aliases)
        for record in (history or [])
    ]
    records = sorted(
        [record for record in history_records + [current] if record["ts"] is not None],
        key=lambda record: record["ts"],
    )
    if current["ts"] is None:
        records = history_records + [current]

    signals: dict[str, Any] = {}
    for rule in rules:
        value = current["values"].get(rule.field)
        previous_value = _previous_value(records=records, current=current, field=rule.field)
        fuzzy = _fuzzy_state(rule=rule, value=value)
        fuzzy["smoothed_score"] = _smooth_score(
            signal_name=rule.name,
            current_score=fuzzy["risk_score"],
            previous_signals=previous_signals,
            alpha=rule.alpha,
        )
        windows = {
            f"{hours}h": _window_profile(
                records=records,
                current=current,
                rule=rule,
                hours=hours,
            )
            for hours in window_hours
        }
        signals[rule.name] = {
            "rule": asdict(rule),
            "value": value,
            "unit": rule.unit,
            "fuzzy": fuzzy,
            "trend": {
                "previous": _trend_profile(
                    current_value=value,
                    previous_value=previous_value,
                    elapsed_hours=_elapsed_hours(records, current),
                ),
                "windows": {
                    key: {
                        "delta": profile["delta"],
                        "rate_per_hour": profile["rate_per_hour"],
                        "trend": profile["trend"],
                        "speed": profile["speed"],
                    }
                    for key, profile in windows.items()
                },
            },
            "accumulation": {
                key: {
                    "pressure_hours": profile["pressure_hours"],
                    "pressure_ratio": profile["pressure_ratio"],
                    "value_sum": profile["value_sum"],
                    "sample_count": profile["sample_count"],
                    "coverage_hours": profile["coverage_hours"],
                }
                for key, profile in windows.items()
            },
        }

    return {
        "schema_version": 1,
        "ruleset_version": ruleset_version,
        "layer": "fuzzy_signals",
        "source_object": source_object,
        "window_hours": list(window_hours),
        "ts": current["ts"],
        "perception": current["values"],
        "signals": signals,
        "debug": {
            "rule_names": [rule.name for rule in rules],
            "field_aliases": {
                field: list(alias_keys)
                for field, alias_keys in aliases.items()
            },
            "history_sample_count": len(history_records),
            "normalized_record_count": len(records),
        },
    }


def _normalize_record(
    sample: Mapping[str, Any],
    aliases: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    payload = _payload(sample, aliases=aliases)
    values = {
        field: _safe_float(_first_present(payload, alias_keys))
        for field, alias_keys in aliases.items()
    }
    return {
        "ts": _resolve_ts(sample),
        "values": values,
        "raw": sample,
    }


def _payload(
    sample: Mapping[str, Any],
    aliases: Mapping[str, Sequence[str]],
) -> Mapping[str, Any]:
    candidates: list[Mapping[str, Any]] = [sample]
    perception = sample.get("perception")
    if isinstance(perception, Mapping):
        candidates.append(perception)
    packet = sample.get("packet")
    if isinstance(packet, Mapping):
        candidates.append(packet)
        for key in ("npk_data", "sht30_data", "meteo_data"):
            nested = packet.get(key)
            if isinstance(nested, Mapping):
                candidates.append(nested)
    return max(candidates, key=lambda candidate: _alias_hit_count(candidate, aliases))


def _alias_hit_count(
    payload: Mapping[str, Any],
    aliases: Mapping[str, Sequence[str]],
) -> int:
    count = 0
    for alias_keys in aliases.values():
        if _first_present(payload, alias_keys) is not None:
            count += 1
    return count


def _resolve_ts(sample: Mapping[str, Any]) -> float | None:
    timestamps = sample.get("timestamps")
    if isinstance(timestamps, Mapping):
        for key in ("ts_server", "observed_ts", "timestamp"):
            value = _safe_float(timestamps.get(key))
            if value is not None:
                return value
    for key in ("ts_server", "observed_ts", "timestamp", "ts"):
        value = _safe_float(sample.get(key))
        if value is not None:
            return value
    return None


def _first_present(payload: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in payload and payload.get(key) is not None:
            return payload.get(key)
    return None


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _fuzzy_state(rule: SignalRule, value: float | None) -> dict[str, Any]:
    if value is None:
        return {
            "state": "missing",
            "level": "unknown",
            "side": "unknown",
            "low_membership": None,
            "normal_membership": None,
            "high_membership": None,
            "risk_score": None,
            "distance_to_normal": None,
        }

    low_pressure = _side_pressure_low(rule, value)
    high_pressure = _side_pressure_high(rule, value)
    if rule.direction == "low":
        risk = low_pressure
    elif rule.direction == "high":
        risk = high_pressure
    else:
        risk = max(low_pressure, high_pressure)

    if value < rule.normal_low:
        side = "low"
        if rule.direction == "high":
            state = "opposite_low"
        else:
            state = "low_critical" if low_pressure >= 1.0 else "low_leaning"
        distance = round(rule.normal_low - value, 4)
    elif value > rule.normal_high:
        side = "high"
        if rule.direction == "low":
            state = "opposite_high"
        else:
            state = "high_critical" if high_pressure >= 1.0 else "high_leaning"
        distance = round(value - rule.normal_high, 4)
    else:
        side = "normal"
        state = "normal"
        distance = 0.0

    normal_membership = 1.0 if side == "normal" else 1.0 - max(low_pressure, high_pressure)
    return {
        "state": state,
        "level": _risk_level(risk),
        "side": side,
        "low_membership": round(low_pressure, 4),
        "normal_membership": round(_clamp(normal_membership), 4),
        "high_membership": round(high_pressure, 4),
        "risk_score": round(_clamp(risk) * rule.confidence, 4),
        "distance_to_normal": distance,
    }


def _side_pressure_low(rule: SignalRule, value: float) -> float:
    if value >= rule.normal_low:
        return 0.0
    if rule.threshold_low is None or rule.normal_low <= rule.threshold_low:
        return 1.0
    return _clamp((rule.normal_low - value) / (rule.normal_low - rule.threshold_low))


def _side_pressure_high(rule: SignalRule, value: float) -> float:
    if value <= rule.normal_high:
        return 0.0
    if rule.threshold_high is None or rule.normal_high >= rule.threshold_high:
        return 1.0
    return _clamp((value - rule.normal_high) / (rule.threshold_high - rule.normal_high))


def _risk_level(risk: float) -> str:
    if risk >= 0.85:
        return "critical"
    if risk >= 0.55:
        return "warning"
    if risk > 0.0:
        return "watch"
    return "normal"


def _smooth_score(
    signal_name: str,
    current_score: float | None,
    previous_signals: Mapping[str, Any] | None,
    alpha: float,
) -> float | None:
    if current_score is None:
        return None
    previous_score = None
    if previous_signals and signal_name in previous_signals:
        previous_payload = previous_signals[signal_name]
        if isinstance(previous_payload, Mapping):
            fuzzy = previous_payload.get("fuzzy")
            if isinstance(fuzzy, Mapping):
                previous_score = _safe_float(
                    fuzzy.get("smoothed_score") or fuzzy.get("risk_score")
                )
            else:
                previous_score = _safe_float(previous_payload.get("smoothed_score"))
    if previous_score is None:
        return current_score
    alpha = _clamp(alpha)
    return round((alpha * current_score) + ((1.0 - alpha) * previous_score), 4)


def _previous_value(
    records: Sequence[dict[str, Any]],
    current: Mapping[str, Any],
    field: str,
) -> float | None:
    if not records:
        return None
    for record in reversed(records):
        if record is current:
            continue
        value = record["values"].get(field)
        if value is not None:
            return value
    return None


def _elapsed_hours(records: Sequence[dict[str, Any]], current: Mapping[str, Any]) -> float | None:
    current_ts = current.get("ts")
    if current_ts is None:
        return None
    for record in reversed(records):
        if record is current:
            continue
        ts = record.get("ts")
        if ts is not None and current_ts >= ts:
            return round((current_ts - ts) / 3600.0, 4)
    return None


def _window_profile(
    records: Sequence[dict[str, Any]],
    current: Mapping[str, Any],
    rule: SignalRule,
    hours: int,
) -> dict[str, Any]:
    current_ts = current.get("ts")
    if current_ts is None:
        values = [
            record["values"][rule.field]
            for record in records
            if record["values"].get(rule.field) is not None
        ]
        return _profile_from_values(values=values, timestamps=[], rule=rule, hours=hours)

    start_ts = current_ts - (hours * 3600)
    subset = [
        record
        for record in records
        if record.get("ts") is not None and start_ts <= record["ts"] <= current_ts
    ]
    values: list[float] = []
    timestamps: list[float] = []
    for record in subset:
        value = record["values"].get(rule.field)
        if value is not None:
            values.append(value)
            timestamps.append(record["ts"])
    return _profile_from_values(values=values, timestamps=timestamps, rule=rule, hours=hours)


def _profile_from_values(
    values: Sequence[float],
    timestamps: Sequence[float],
    rule: SignalRule,
    hours: int,
) -> dict[str, Any]:
    if not values:
        return {
            "sample_count": 0,
            "coverage_hours": 0.0,
            "delta": None,
            "rate_per_hour": None,
            "trend": "unknown",
            "speed": "unknown",
            "pressure_hours": 0.0,
            "pressure_ratio": 0.0,
            "value_sum": None,
        }
    delta = round(values[-1] - values[0], 4)
    coverage_hours = 0.0
    rate = None
    if len(timestamps) >= 2 and timestamps[-1] > timestamps[0]:
        coverage_hours = round((timestamps[-1] - timestamps[0]) / 3600.0, 4)
        if coverage_hours > 0:
            rate = round(delta / coverage_hours, 4)

    pressure_hours = _integrate_pressure(values=values, timestamps=timestamps, rule=rule)
    pressure_ratio = _clamp(pressure_hours / max(float(hours), 1.0))
    return {
        "sample_count": len(values),
        "coverage_hours": coverage_hours,
        "delta": delta,
        "rate_per_hour": rate,
        "trend": _trend_label(delta=delta, current=values[-1]),
        "speed": _speed_label(rate=rate, current=values[-1]),
        "pressure_hours": round(pressure_hours, 4),
        "pressure_ratio": round(pressure_ratio, 4),
        "value_sum": round(sum(values), 4),
    }


def _integrate_pressure(
    values: Sequence[float],
    timestamps: Sequence[float],
    rule: SignalRule,
) -> float:
    if len(values) < 2 or len(timestamps) < 2:
        return 0.0
    total = 0.0
    for left_value, right_value, left_ts, right_ts in zip(
        values,
        values[1:],
        timestamps,
        timestamps[1:],
    ):
        if right_ts <= left_ts:
            continue
        left_pressure = _directed_pressure(rule, left_value)
        right_pressure = _directed_pressure(rule, right_value)
        duration_hours = (right_ts - left_ts) / 3600.0
        total += ((left_pressure + right_pressure) / 2.0) * duration_hours
    return total


def _directed_pressure(rule: SignalRule, value: float) -> float:
    low_pressure = _side_pressure_low(rule, value)
    high_pressure = _side_pressure_high(rule, value)
    if rule.direction == "low":
        return low_pressure
    if rule.direction == "high":
        return high_pressure
    return max(low_pressure, high_pressure)


def _trend_profile(
    current_value: float | None,
    previous_value: float | None,
    elapsed_hours: float | None,
) -> dict[str, Any]:
    if current_value is None or previous_value is None:
        return {
            "previous_value": previous_value,
            "delta": None,
            "rate_per_hour": None,
            "trend": "unknown",
            "speed": "unknown",
            "elapsed_hours": elapsed_hours,
        }
    delta = round(current_value - previous_value, 4)
    rate = None
    if elapsed_hours is not None and elapsed_hours > 0:
        rate = round(delta / elapsed_hours, 4)
    return {
        "previous_value": previous_value,
        "delta": delta,
        "rate_per_hour": rate,
        "trend": _trend_label(delta=delta, current=current_value),
        "speed": _speed_label(rate=rate, current=current_value),
        "elapsed_hours": elapsed_hours,
    }


def _trend_label(delta: float | None, current: float) -> str:
    if delta is None:
        return "unknown"
    stable_threshold = max(abs(current) * 0.01, 0.05)
    if abs(delta) <= stable_threshold:
        return "stable"
    return "rising" if delta > 0 else "falling"


def _speed_label(rate: float | None, current: float) -> str:
    if rate is None:
        return "unknown"
    base = max(abs(current) * 0.01, 0.05)
    abs_rate = abs(rate)
    if abs_rate <= base:
        return "slow"
    if abs_rate <= base * 3:
        return "moderate"
    return "fast"
