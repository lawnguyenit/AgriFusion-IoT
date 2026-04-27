import json
from typing import Any

try:
    from app_config import ExportSettings
except ModuleNotFoundError:
    from ...app_config import ExportSettings

from ..utils.file_store import write_json


def load_sync_state(settings: ExportSettings) -> dict[str, Any]:
    if not settings.sync_state_path.exists():
        return _default_sync_state(settings)

    try:
        payload = json.loads(settings.sync_state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _default_sync_state(settings)

    if not isinstance(payload, dict):
        return _default_sync_state(settings)
    return payload


def save_sync_state(settings: ExportSettings, payload: dict[str, Any]) -> None:
    write_json(settings.sync_state_path, payload)


def _default_sync_state(settings: ExportSettings) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "node_id": settings.node_id,
        "status": "idle",
        "last_checked_at_utc": None,
        "last_seen_event_key": None,
        "last_seen_date_key": None,
        "latest_path": None,
        "latest_meta_path": settings.latest_meta_path,
        "latest_current_path": settings.latest_current_path,
        "latest_ts_device": None,
        "latest_ts_server": None,
        "record_sha256": None,
        "previous_event_key": None,
        "no_change_retry_count": 0,
        "next_retry_at_utc": None,
        "next_primary_check_at_utc": None,
        "alert_code": None,
        "age_since_latest_sec": None,
        "delta_device_sec": None,
        "delta_server_sec": None,
        "device_delta_in_expected_range": None,
        "server_delta_in_expected_range": None,
        "primary_poll_after_sec": settings.primary_poll_after_sec,
        "retry_after_no_change_sec": settings.retry_after_no_change_sec,
        "source_type": settings.source_type,
        "source_uri": None if settings.input_json_path is None else str(settings.input_json_path),
        "source_sha256": None,
    }
