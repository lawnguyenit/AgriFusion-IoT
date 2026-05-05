from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

try:
    from Services.config.settings import ExportSettings, SETTINGS
except ModuleNotFoundError:
    from ..config.settings import ExportSettings, SETTINGS

from .stores.artifact_store import (
    write_latest_meta,
    write_latest_payload,
    write_source_audit_artifacts,
)
from .sync.latest_sync import SyncDecision, build_sync_state, decide_sync, parse_latest_meta
from .sources import FirebaseSourceAdapter, JsonExportSourceAdapter
from .utils.layout import format_iso_utc
from .stores.sync_state_store import load_sync_state, save_sync_state
from .stores.telemetry_store import write_full_history_snapshots, write_history_snapshot


@dataclass(frozen=True)
class ExportResult:
    status: str
    source_type: str
    checked_at_utc: str
    latest_event_key: str | None
    latest_path: str | None
    latest_payload_path: Path | None
    latest_meta_local_path: Path
    sync_state_path: Path
    history_path: Path | None
    next_retry_at_utc: str | None
    next_primary_check_at_utc: str | None
    source_manifest_path: Path
    source_snapshot_path: Path | None
    full_history_written_count: int = 0


class ExportPipeline:
    def __init__(self, firebase_service: Any = None, settings: ExportSettings = SETTINGS):
        self.firebase_service = firebase_service
        self.settings = settings
        self.source_adapter = self._build_source_adapter()

    def run(
        self,
        full_history: bool = False,
        history_start_date: date | None = None,
        history_end_date: date | None = None,
    ) -> ExportResult | None:
        checked_at = _utc_now()
        previous_sync_state = load_sync_state(self.settings)

        latest_meta_payload = self.source_adapter.fetch_latest_meta_payload()
        if latest_meta_payload is None:
            return None

        source_descriptor = self.source_adapter.describe_source()
        meta_snapshot = parse_latest_meta(
            latest_meta_payload,
            self.settings,
            source_descriptor={
                "source_type": source_descriptor.source_type,
                "source_uri": source_descriptor.source_uri,
                "source_sha256": source_descriptor.source_sha256,
            },
        )
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
        source_snapshot_path: Path | None = None
        full_history_written_count = 0

        if decision.status != "duplicate_source":
            write_latest_meta(self.settings, latest_meta_payload)
            audit_artifacts = self.source_adapter.build_audit_artifacts(checked_at)
            _, source_snapshot_path = write_source_audit_artifacts(
                self.settings,
                manifest_payload=audit_artifacts.manifest_payload,
                snapshot_payload=audit_artifacts.snapshot_payload,
            )

        if decision.should_fetch_current:
            latest_current_payload = self.source_adapter.fetch_latest_current_payload(latest_meta_payload)
            if latest_current_payload is None:
                sync_state["status"] = "error_current_missing"
                sync_state["alert_code"] = "latest_current_missing"
                save_sync_state(self.settings, sync_state)
                return ExportResult(
                    status=sync_state["status"],
                    source_type=self.settings.source_type,
                    checked_at_utc=format_iso_utc(checked_at),
                    latest_event_key=meta_snapshot.event_key,
                    latest_path=meta_snapshot.latest_path,
                    latest_payload_path=None,
                    latest_meta_local_path=self.settings.latest_meta_local_path,
                    sync_state_path=self.settings.sync_state_path,
                    history_path=None,
                    next_retry_at_utc=sync_state["next_retry_at_utc"],
                    next_primary_check_at_utc=sync_state["next_primary_check_at_utc"],
                    source_manifest_path=self.settings.source_manifest_path,
                    source_snapshot_path=source_snapshot_path,
                    full_history_written_count=0,
                )

            latest_payload_path = write_latest_payload(self.settings, latest_current_payload)
            history_path = write_history_snapshot(
                settings=self.settings,
                date_key=meta_snapshot.date_key,
                event_key=meta_snapshot.event_key,
                latest_path=meta_snapshot.latest_path,
                current_payload=latest_current_payload,
                checked_at=checked_at,
            )

        if full_history and decision.status != "duplicate_source":
            telemetry_payload = self.source_adapter.fetch_full_history_payload()
            if telemetry_payload is not None:
                full_history_written_count = write_full_history_snapshots(
                    settings=self.settings,
                    telemetry_payload=telemetry_payload,
                    checked_at=checked_at,
                    start_date=history_start_date,
                    end_date=history_end_date,
                )

        save_sync_state(self.settings, sync_state)

        return ExportResult(
            status=sync_state["status"],
            source_type=self.settings.source_type,
            checked_at_utc=format_iso_utc(checked_at),
            latest_event_key=meta_snapshot.event_key,
            latest_path=meta_snapshot.latest_path,
            latest_payload_path=latest_payload_path,
            latest_meta_local_path=self.settings.latest_meta_local_path,
            sync_state_path=self.settings.sync_state_path,
            history_path=history_path,
            next_retry_at_utc=sync_state["next_retry_at_utc"],
            next_primary_check_at_utc=sync_state["next_primary_check_at_utc"],
            source_manifest_path=self.settings.source_manifest_path,
            source_snapshot_path=source_snapshot_path,
            full_history_written_count=full_history_written_count,
        )

    def _build_source_adapter(self) -> Any:
        if self.settings.source_type == "firebase":
            if self.firebase_service is None:
                raise ValueError("firebase_service is required when source_type is 'firebase'")
            return FirebaseSourceAdapter(self.firebase_service, self.settings)

        if self.settings.source_type == "json-export":
            return JsonExportSourceAdapter(self.settings)

        raise ValueError(f"Unsupported export source '{self.settings.source_type}'")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
