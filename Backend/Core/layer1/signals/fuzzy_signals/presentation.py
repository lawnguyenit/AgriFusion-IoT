from __future__ import annotations

from typing import Any, Mapping, Sequence


def compact_fuzzy_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {
        key: payload.get(key)
        for key in (
            "schema_version",
            "ruleset_version",
            "layer",
            "source_object",
            "window_hours",
            "ts",
            "perception",
        )
    }
    compact["signals"] = {}
    compact["evaluated_signal_count"] = 0
    compact["active_signal_count"] = 0

    signals = payload.get("signals")
    if not isinstance(signals, Mapping):
        return compact
    compact["evaluated_signal_count"] = len(signals)

    for signal_name, signal_payload in signals.items():
        if not isinstance(signal_payload, Mapping):
            continue
        is_active = _signal_is_active(signal_payload)
        fuzzy = signal_payload.get("fuzzy")
        fuzzy = fuzzy if isinstance(fuzzy, Mapping) else {}
        compact["signals"][str(signal_name)] = {
            "is_active": is_active,
            "value": signal_payload.get("value"),
            "unit": signal_payload.get("unit"),
            "state": fuzzy.get("state"),
            "level": fuzzy.get("level"),
            "side": fuzzy.get("side"),
            "risk_score": fuzzy.get("risk_score"),
            "smoothed_score": fuzzy.get("smoothed_score"),
            "distance_to_normal": fuzzy.get("distance_to_normal"),
            "accumulation": _compact_accumulation(signal_payload.get("accumulation")),
        }
    compact["active_signal_count"] = sum(
        1
        for signal_payload in compact["signals"].values()
        if isinstance(signal_payload, Mapping) and signal_payload.get("is_active")
    )
    return compact


def _compact_accumulation(accumulation: Any) -> dict[str, Any]:
    if not isinstance(accumulation, Mapping):
        return {}
    compact: dict[str, Any] = {}
    for window_key, profile in accumulation.items():
        if not isinstance(profile, Mapping):
            continue
        compact[str(window_key)] = {
            "pressure_hours": profile.get("pressure_hours"),
            "pressure_ratio": profile.get("pressure_ratio"),
            "sample_count": profile.get("sample_count"),
            "coverage_hours": profile.get("coverage_hours"),
        }
    return compact


def _signal_is_active(signal_payload: Mapping[str, Any]) -> bool:
    fuzzy = signal_payload.get("fuzzy")
    if isinstance(fuzzy, Mapping):
        risk_score = _safe_float(fuzzy.get("risk_score"))
        smoothed_score = _safe_float(fuzzy.get("smoothed_score"))
        if risk_score is not None and risk_score > 0.0:
            return True
        if smoothed_score is not None and smoothed_score >= 0.01:
            return True

    accumulation = signal_payload.get("accumulation")
    if isinstance(accumulation, Mapping):
        for profile in accumulation.values():
            if not isinstance(profile, Mapping):
                continue
            pressure_ratio = _safe_float(profile.get("pressure_ratio"))
            pressure_hours = _safe_float(profile.get("pressure_hours"))
            if pressure_ratio is not None and pressure_ratio > 0.0:
                return True
            if pressure_hours is not None and pressure_hours > 0.0:
                return True
    return False


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def previous_signals_from_history(
    history_records: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    for record in reversed(history_records):
        fuzzy_payload = record.get("fuzzy_signals")
        if not isinstance(fuzzy_payload, Mapping):
            continue
        signals = fuzzy_payload.get("signals")
        if isinstance(signals, Mapping):
            return signals
    return None
