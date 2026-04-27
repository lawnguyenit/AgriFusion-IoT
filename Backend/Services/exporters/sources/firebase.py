from __future__ import annotations

from datetime import datetime
from typing import Any

try:
    from app_config import ExportSettings
except ModuleNotFoundError:
    from ...app_config import ExportSettings

from ..stores.artifact_store import base_source_manifest_payload
from ..utils.file_store import serialize_json, sha256_hex
from ..utils.json_ordering import canonicalize_json
from .base import NormalizedSnapshotMixin, SourceAuditArtifacts, SourceDescriptor


class FirebaseSourceAdapter(NormalizedSnapshotMixin):
    source_type = "firebase"
    skip_duplicate_on_same_source = False

    def __init__(self, firebase_service: Any, settings: ExportSettings):
        super().__init__(settings)
        self.firebase_service = firebase_service
        self.source_uri = f"firebase://{settings.node_id}"
        self._mode = "snapshot_root"
        self._legacy_latest_meta_payload: dict[str, Any] | None = None

    def fetch_latest_meta_payload(self) -> dict[str, Any] | None:
        root_payload = self.firebase_service.pull_data(node_path=self.settings.node_id)
        if self._looks_like_normalized_snapshot(root_payload):
            ordered_root_payload = canonicalize_json(root_payload)
            self._set_snapshot_payload(
                payload=ordered_root_payload,
                source_sha256=sha256_hex(serialize_json(ordered_root_payload)),
            )
            self._mode = "snapshot_root"
            return super().fetch_latest_meta_payload()

        latest_meta_payload = self.firebase_service.pull_data(node_path=self.settings.latest_meta_path)
        if latest_meta_payload is None:
            return None
        if not isinstance(latest_meta_payload, dict):
            raise ValueError("Firebase latest meta payload must be a JSON object")

        ordered_meta_payload = canonicalize_json(latest_meta_payload)
        self.source_sha256 = sha256_hex(serialize_json(ordered_meta_payload))
        self._legacy_latest_meta_payload = dict(ordered_meta_payload)
        self._mode = "legacy_paths"
        return dict(ordered_meta_payload)

    def fetch_latest_current_payload(self, latest_meta_payload: dict[str, Any]) -> dict[str, Any] | None:
        if self._mode == "snapshot_root":
            return super().fetch_latest_current_payload(latest_meta_payload)

        latest_current_payload = self.firebase_service.pull_data(node_path=self.settings.latest_current_path)
        if latest_current_payload is None:
            return None
        if not isinstance(latest_current_payload, dict):
            raise ValueError("Firebase latest current payload must be a JSON object")
        return canonicalize_json(latest_current_payload)

    def fetch_full_history_payload(self) -> dict[str, Any] | None:
        if self._mode == "snapshot_root":
            return super().fetch_full_history_payload()

        telemetry_payload = self.firebase_service.pull_data(node_path=self.settings.telemetry_root_path)
        if telemetry_payload is None:
            return None
        if not isinstance(telemetry_payload, dict):
            raise ValueError("Firebase telemetry payload must be a JSON object")
        return canonicalize_json(telemetry_payload)

    def build_audit_artifacts(self, checked_at: datetime) -> SourceAuditArtifacts:
        if self._mode == "snapshot_root":
            artifacts = super().build_audit_artifacts(checked_at)
            artifacts.manifest_payload["firebase_mode"] = "node_snapshot_root"
            return artifacts

        manifest_payload = base_source_manifest_payload(
            source_type=self.source_type,
            source_uri=f"firebase://{self.settings.latest_meta_path}",
            source_sha256=self.source_sha256,
            checked_at=checked_at,
            node_id=self.settings.node_id,
            node_slug=self.settings.node_slug,
        )
        manifest_payload.update(
            {
                "firebase_mode": "legacy_paths",
                "latest_meta_path": self.settings.latest_meta_path,
                "latest_current_path": self.settings.latest_current_path,
                "telemetry_root_path": self.settings.telemetry_root_path,
                "latest_event_key": None
                if self._legacy_latest_meta_payload is None
                else self._legacy_latest_meta_payload.get("latest_event_key"),
            }
        )
        return SourceAuditArtifacts(
            manifest_payload=manifest_payload,
            snapshot_payload=self._legacy_latest_meta_payload,
        )

    def describe_source(self) -> SourceDescriptor:
        if self._mode == "snapshot_root":
            return super().describe_source()

        return SourceDescriptor(
            source_type=self.source_type,
            source_uri=f"firebase://{self.settings.latest_meta_path}",
            source_sha256=self.source_sha256,
        )

    def _looks_like_normalized_snapshot(self, payload: Any) -> bool:
        return (
            isinstance(payload, dict)
            and all(isinstance(payload.get(section), dict) for section in ("info", "live", "status_events", "telemetry"))
        )
