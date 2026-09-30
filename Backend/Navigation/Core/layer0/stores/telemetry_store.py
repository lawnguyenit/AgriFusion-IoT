from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any

try:
    from Config.runtime import BackendSettings
except ModuleNotFoundError:
    from .....Config.runtime import BackendSettings

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


def write_full_history_raw_snapshots(
    settings: BackendSettings,
    telemetry_payload: dict[str, Any],
    checked_at: datetime,
    start_date: date | None = None,
    end_date: date | None = None,
    source_metadata: dict[str, Any] | None = None,
) -> int:
    """Persist source records before normalization under content-addressed names."""
    written_count = 0
    eligible_count = 0
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
            eligible_count += 1
            encoded_record = json.dumps(
                record_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            digest = hashlib.sha256(encoded_record).hexdigest()
            raw_path = (
                settings.firebase_raw_history_root
                / current_date.strftime("%Y")
                / current_date.strftime("%m")
                / current_date.strftime("%d")
                / f"{settings.node_slug}_{_safe_filename_fragment(str(event_key))}_{digest}.json"
            )
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            envelope = {
                "date_key": str(date_key),
                "event_key": str(event_key),
                "captured_at_utc": checked_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "record_sha256": digest,
                "record": record_payload,
            }
            serialized = json.dumps(envelope, ensure_ascii=False, indent=2).encode("utf-8")
            if raw_path.exists():
                existing = json.loads(raw_path.read_text(encoding="utf-8"))
                existing_record = json.dumps(
                    existing.get("record"),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                if (
                    existing.get("record_sha256") != digest
                    or hashlib.sha256(existing_record).hexdigest() != digest
                ):
                    raise ValueError(f"Content-addressed raw history collision at {raw_path}.")
                continue
            with raw_path.open("xb") as handle:
                handle.write(serialized)
            written_count += 1
    archive_runs = settings.firebase_raw_history_root / "archive_runs"
    archive_runs.mkdir(parents=True, exist_ok=True)
    run_id = checked_at.strftime("%Y%m%dT%H%M%S%fZ")
    run_manifest = {
        "schema_version": 1,
        "archive_run_id": run_id,
        "completed_at_utc": checked_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "completion_status": "complete",
        "source": source_metadata or {},
        "date_filter": {
            "start_date_inclusive": None if start_date is None else start_date.isoformat(),
            "end_date_inclusive": None if end_date is None else end_date.isoformat(),
        },
        "eligible_record_count": eligible_count,
        "new_record_file_count": written_count,
        "existing_verified_record_file_count": eligible_count - written_count,
    }
    manifest_path = archive_runs / f"{run_id}.json"
    manifest_path.write_text(json.dumps(run_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
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


def _safe_filename_fragment(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "event"


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
