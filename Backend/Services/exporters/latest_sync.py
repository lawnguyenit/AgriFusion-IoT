from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

try:
    from app_config import ExportSettings
except ModuleNotFoundError:
    from ..app_config import ExportSettings

from .layout import format_iso_utc


@dataclass(frozen=True)
class LatestMetaSnapshot:
    event_key: str
    date_key: str
    latest_path: str
    ts_device: int
    ts_server: int
    record_sha256: str | None
    delta_device_sec: int | None
    delta_server_sec: int | None
    device_delta_ok: bool | None
    server_delta_ok: bool | None
    primary_poll_after_sec: int
    retry_after_no_change_sec: int


@dataclass(frozen=True)
class SyncDecision:
    status: str
    should_fetch_current: bool
    no_change_retry_count: int
    next_primary_check_at_utc: str
    next_retry_at_utc: str | None
    alert_code: str | None


def parse_latest_meta(meta: dict[str, Any], settings: ExportSettings) -> LatestMetaSnapshot:
    return LatestMetaSnapshot(
        event_key=str(meta["latest_event_key"]),
        date_key=str(meta["latest_date_key"]),
        latest_path=str(meta["latest_path"]),
        ts_device=int(meta["ts_device"]),
        ts_server=int(meta["ts_server"]),
        record_sha256=meta.get("record_sha256"),
        delta_device_sec=_as_optional_int(meta.get("delta_device_sec")),
        delta_server_sec=_as_optional_int(meta.get("delta_server_sec")),
        device_delta_ok=_as_optional_bool(meta.get("device_in_expected_range")),
        server_delta_ok=_as_optional_bool(meta.get("server_in_expected_range")),
        primary_poll_after_sec=int(meta.get("primary_poll_after_sec") or settings.primary_poll_after_sec),
        retry_after_no_change_sec=int(
            meta.get("retry_after_no_change_sec") or settings.retry_after_no_change_sec
        ),
    )


def decide_sync(
    snapshot: LatestMetaSnapshot,
    previous_state: dict[str, Any],
    checked_at: datetime,
    settings: ExportSettings,
) -> SyncDecision:
    previous_event_key = previous_state.get("last_seen_event_key")
    next_primary = checked_at + timedelta(seconds=snapshot.primary_poll_after_sec)

    if previous_event_key != snapshot.event_key:
        return SyncDecision(
            status="new_data",
            should_fetch_current=True,
            no_change_retry_count=0,
            next_primary_check_at_utc=format_iso_utc(next_primary),
            next_retry_at_utc=None,
            alert_code=None,
        )

    previous_retry_count = int(previous_state.get("no_change_retry_count", 0))
    next_retry_count = previous_retry_count + 1
    if next_retry_count <= settings.no_change_retry_limit:
        next_retry = checked_at + timedelta(seconds=snapshot.retry_after_no_change_sec)
        return SyncDecision(
            status="retry_waiting",
            should_fetch_current=False,
            no_change_retry_count=next_retry_count,
            next_primary_check_at_utc=format_iso_utc(next_primary),
            next_retry_at_utc=format_iso_utc(next_retry),
            alert_code=None,
        )

    return SyncDecision(
        status="stale_after_retry",
        should_fetch_current=False,
        no_change_retry_count=next_retry_count,
        next_primary_check_at_utc=format_iso_utc(next_primary),
        next_retry_at_utc=None,
        alert_code="possible_upload_delay",
    )


def build_sync_state(
    snapshot: LatestMetaSnapshot,
    decision: SyncDecision,
    checked_at: datetime,
    previous_state: dict[str, Any],
    settings: ExportSettings,
) -> dict[str, Any]:
    age_since_latest_sec = max(0, int(checked_at.timestamp()) - snapshot.ts_server)
    return {
        "schema_version": 1,
        "node_id": settings.node_id,
        "status": decision.status,
        "last_checked_at_utc": format_iso_utc(checked_at),
        "last_seen_event_key": snapshot.event_key,
        "last_seen_date_key": snapshot.date_key,
        "latest_path": snapshot.latest_path,
        "latest_meta_path": settings.latest_meta_path,
        "latest_current_path": settings.latest_current_path,
        "latest_ts_device": snapshot.ts_device,
        "latest_ts_server": snapshot.ts_server,
        "record_sha256": snapshot.record_sha256,
        "previous_event_key": previous_state.get("last_seen_event_key"),
        "no_change_retry_count": decision.no_change_retry_count,
        "next_retry_at_utc": decision.next_retry_at_utc,
        "next_primary_check_at_utc": decision.next_primary_check_at_utc,
        "alert_code": decision.alert_code,
        "age_since_latest_sec": age_since_latest_sec,
        "delta_device_sec": snapshot.delta_device_sec,
        "delta_server_sec": snapshot.delta_server_sec,
        "device_delta_in_expected_range": snapshot.device_delta_ok,
        "server_delta_in_expected_range": snapshot.server_delta_ok,
        "primary_poll_after_sec": snapshot.primary_poll_after_sec,
        "retry_after_no_change_sec": snapshot.retry_after_no_change_sec,
    }


def _as_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _as_optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)
