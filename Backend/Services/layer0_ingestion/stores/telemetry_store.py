from datetime import date, datetime
from pathlib import Path
from typing import Any

try:
    from Config.runtime import BackendSettings
except ModuleNotFoundError:
    from ....Config.runtime import BackendSettings

from ..utils.file_store import write_json


def write_history_snapshot(
    settings: BackendSettings,
    date_key: str,
    event_key: str,
    latest_path: str,
    current_payload: dict[str, Any],
    checked_at: datetime,
) -> Path:
    history_path = build_history_path(settings, date_key, event_key)
    write_json(
        history_path,
        {
            "event_key": event_key,
            "date_key": date_key,
            "path": latest_path,
            "synced_at_utc": checked_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "record": current_payload,
        },
    )
    return history_path


def write_full_history_snapshots(
    settings: BackendSettings,
    telemetry_payload: dict[str, Any],
    checked_at: datetime,
    start_date: date | None = None,
    end_date: date | None = None,
    start_ts: int | None = None,
    end_ts: int | None = None,
) -> int:
    written_count = 0

    for date_key, day_payload in telemetry_payload.items():
        if not isinstance(day_payload, dict):
            continue
        try:
            current_date = date.fromisoformat(str(date_key))
        except ValueError:
            continue
        if start_date is not None and current_date < start_date:
            continue
        if end_date is not None and current_date > end_date:
            continue

        for event_key, record_payload in day_payload.items():
            if not isinstance(record_payload, dict):
                continue
            event_ts = _resolve_event_timestamp(event_key=event_key, record_payload=record_payload)
            if start_ts is not None and event_ts is not None and event_ts < start_ts:
                continue
            if end_ts is not None and event_ts is not None and event_ts > end_ts:
                continue

            write_history_snapshot(
                settings=settings,
                date_key=str(date_key),
                event_key=str(event_key),
                latest_path=f"{settings.telemetry_root_path}/{date_key}/{event_key}",
                current_payload=record_payload,
                checked_at=checked_at,
            )
            written_count += 1

    return written_count


def _resolve_event_timestamp(event_key: str, record_payload: dict[str, Any]) -> int | None:
    candidates = (
        record_payload.get("ts_server"),
        record_payload.get("ts_sample"),
        record_payload.get("packet", {}).get("system_data", {}).get("sample_epoch_sec"),
        event_key,
    )
    for candidate in candidates:
        try:
            ts_value = int(candidate)
        except (TypeError, ValueError):
            continue
        if ts_value > 0:
            return ts_value
    return None


def build_history_path(settings: BackendSettings, date_key: str, event_key: str) -> Path:
    dt = datetime.strptime(date_key, "%Y-%m-%d")
    safe_event_key = event_key.replace("/", "_")
    return (
        settings.history_root
        / dt.strftime("%Y")
        / dt.strftime("%m")
        / dt.strftime("%d")
        / f"{settings.node_slug}_{safe_event_key}.json"
    )
