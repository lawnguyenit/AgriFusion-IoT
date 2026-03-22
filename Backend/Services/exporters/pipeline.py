from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from app_config import ExportSettings, SETTINGS
except ModuleNotFoundError:
    from ..app_config import ExportSettings, SETTINGS

from .file_store import write_json
from .json_ordering import canonicalize_json
from .latest_sync import build_sync_state, decide_sync, parse_latest_meta
from .layout import format_iso_utc
from .sync_state_store import load_sync_state, save_sync_state
from .telemetry_store import write_full_history_snapshots, write_history_snapshot


@dataclass(frozen=True)
class ExportResult:
    status: str
    checked_at_utc: str
    latest_event_key: str | None
    latest_path: str | None
    latest_payload_path: Path | None
    latest_meta_local_path: Path
    sync_state_path: Path
    history_path: Path | None
    next_retry_at_utc: str | None
    next_primary_check_at_utc: str | None
    full_history_written_count: int = 0


class ExportPipeline:
    def __init__(self, firebase_service: Any, settings: ExportSettings = SETTINGS):
        self.firebase_service = firebase_service
        self.settings = settings

    def run(self, full_history: bool = False) -> ExportResult | None:
        checked_at = _utc_now()
        previous_sync_state = load_sync_state(self.settings)

        latest_meta_payload = self.firebase_service.pull_data(
            node_path=self.settings.latest_meta_path
        )
        if latest_meta_payload is None:
            return None

        ordered_meta_payload = canonicalize_json(latest_meta_payload)
        write_json(self.settings.latest_meta_local_path, ordered_meta_payload)

        meta_snapshot = parse_latest_meta(ordered_meta_payload, self.settings)
        decision = decide_sync(
            snapshot=meta_snapshot,
            previous_state=previous_sync_state,
            checked_at=checked_at,
            settings=self.settings,
        )
        sync_state = build_sync_state(
            snapshot=meta_snapshot,
            decision=decision,
            checked_at=checked_at,
            previous_state=previous_sync_state,
            settings=self.settings,
        )

        latest_payload_path: Path | None = None
        history_path: Path | None = None
        full_history_written_count = 0

        if decision.should_fetch_current:
            latest_current_payload = self.firebase_service.pull_data(
                node_path=self.settings.latest_current_path
            )
            if latest_current_payload is None:
                sync_state["status"] = "error_current_missing"
                sync_state["alert_code"] = "latest_current_missing"
                save_sync_state(self.settings, sync_state)
                return ExportResult(
                    status=sync_state["status"],
                    checked_at_utc=format_iso_utc(checked_at),
                    latest_event_key=meta_snapshot.event_key,
                    latest_path=meta_snapshot.latest_path,
                    latest_payload_path=None,
                    latest_meta_local_path=self.settings.latest_meta_local_path,
                    sync_state_path=self.settings.sync_state_path,
                    history_path=None,
                    next_retry_at_utc=sync_state["next_retry_at_utc"],
                    next_primary_check_at_utc=sync_state["next_primary_check_at_utc"],
                    full_history_written_count=0,
                )

            ordered_current_payload = canonicalize_json(latest_current_payload)
            write_json(self.settings.latest_payload_path, ordered_current_payload)
            latest_payload_path = self.settings.latest_payload_path
            history_path = write_history_snapshot(
                settings=self.settings,
                date_key=meta_snapshot.date_key,
                event_key=meta_snapshot.event_key,
                latest_path=meta_snapshot.latest_path,
                current_payload=ordered_current_payload,
                checked_at=checked_at,
            )

        if full_history:
            telemetry_payload = self.firebase_service.pull_data(
                node_path=self.settings.telemetry_root_path
            )
            if telemetry_payload is not None:
                ordered_telemetry_payload = canonicalize_json(telemetry_payload)
                full_history_written_count = write_full_history_snapshots(
                    settings=self.settings,
                    telemetry_payload=ordered_telemetry_payload,
                    checked_at=checked_at,
                )

        save_sync_state(self.settings, sync_state)

        return ExportResult(
            status=sync_state["status"],
            checked_at_utc=format_iso_utc(checked_at),
            latest_event_key=meta_snapshot.event_key,
            latest_path=meta_snapshot.latest_path,
            latest_payload_path=latest_payload_path,
            latest_meta_local_path=self.settings.latest_meta_local_path,
            sync_state_path=self.settings.sync_state_path,
            history_path=history_path,
            next_retry_at_utc=sync_state["next_retry_at_utc"],
            next_primary_check_at_utc=sync_state["next_primary_check_at_utc"],
            full_history_written_count=full_history_written_count,
        )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
