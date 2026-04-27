from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from Services.config.settings import ExportSettings
except ModuleNotFoundError:
    from ...config.settings import ExportSettings

from ..utils.file_store import write_json


def write_history_snapshot(
    settings: ExportSettings,
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
    settings: ExportSettings,
    telemetry_payload: dict[str, Any],
    checked_at: datetime,
) -> int:
    written_count = 0

    for date_key, day_payload in telemetry_payload.items():
        if not isinstance(day_payload, dict):
            continue

        for event_key, record_payload in day_payload.items():
            if not isinstance(record_payload, dict):
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


def build_history_path(settings: ExportSettings, date_key: str, event_key: str) -> Path:
    dt = datetime.strptime(date_key, "%Y-%m-%d")
    safe_event_key = event_key.replace("/", "_")
    return (
        settings.history_root
        / dt.strftime("%Y")
        / dt.strftime("%m")
        / dt.strftime("%d")
        / f"{settings.node_slug}_{safe_event_key}.json"
    )
