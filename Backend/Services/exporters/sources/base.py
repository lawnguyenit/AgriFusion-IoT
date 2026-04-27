from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

try:
    from Services.config.settings import ExportSettings
except ModuleNotFoundError:
    from ...config.settings import ExportSettings

from ..stores.artifact_store import base_source_manifest_payload
from ..utils.file_store import serialize_json, sha256_hex
from ..utils.json_ordering import canonicalize_json


@dataclass(frozen=True)
class SourceAuditArtifacts:
    manifest_payload: dict[str, Any]
    snapshot_payload: dict[str, Any] | None


@dataclass(frozen=True)
class SourceDescriptor:
    source_type: str
    source_uri: str
    source_sha256: str | None


class NormalizedSnapshotMixin:
    def __init__(self, settings: ExportSettings):
        self.settings = settings
        self.source_sha256: str | None = None
        self._source_payload: dict[str, Any] | None = None
        self._ordered_source_payload: dict[str, Any] | None = None
        self._normalized_telemetry: dict[str, Any] | None = None
        self._latest_context: dict[str, Any] | None = None
        self._previous_context: dict[str, Any] | None = None
        self._detected_identity: dict[str, Any] = {}

    def _ensure_prepared(self) -> None:
        return None

    def fetch_latest_meta_payload(self) -> dict[str, Any] | None:
        self._ensure_prepared()
        if self._latest_context is None:
            raise ValueError("Source payload does not contain any telemetry events")
        return self._build_latest_meta_payload()

    def fetch_latest_current_payload(self, latest_meta_payload: dict[str, Any]) -> dict[str, Any] | None:
        self._ensure_prepared()
        if self._latest_context is None:
            return None
        return copy.deepcopy(self._latest_context["record"])

    def fetch_full_history_payload(self) -> dict[str, Any] | None:
        self._ensure_prepared()
        return copy.deepcopy(self._normalized_telemetry)

    def build_audit_artifacts(self, checked_at: datetime) -> SourceAuditArtifacts:
        self._ensure_prepared()
        manifest_payload = base_source_manifest_payload(
            source_type=self.source_type,
            source_uri=self.source_uri,
            source_sha256=self.source_sha256,
            checked_at=checked_at,
            node_id=self.settings.node_id,
            node_slug=self.settings.node_slug,
        )
        manifest_payload.update(
            {
                "detected_identity": self._detected_identity,
                "telemetry_date_count": len(self._normalized_telemetry or {}),
                "telemetry_record_count": sum(
                    len(day_payload)
                    for day_payload in (self._normalized_telemetry or {}).values()
                    if isinstance(day_payload, dict)
                ),
                "latest_event_key": None if self._latest_context is None else self._latest_context["event_key"],
                "latest_date_key": None if self._latest_context is None else self._latest_context["date_key"],
                "latest_ts_server": None
                if self._latest_context is None
                else self._latest_context["ts_server"],
            }
        )
        return SourceAuditArtifacts(
            manifest_payload=manifest_payload,
            snapshot_payload=copy.deepcopy(self._ordered_source_payload),
        )

    def describe_source(self) -> SourceDescriptor:
        return SourceDescriptor(
            source_type=self.source_type,
            source_uri=self.source_uri,
            source_sha256=self.source_sha256,
        )

    def _set_snapshot_payload(self, payload: dict[str, Any], source_sha256: str | None) -> None:
        self._validate_payload(payload)
        self.source_sha256 = source_sha256
        self._source_payload = payload
        self._ordered_source_payload = canonicalize_json(payload)
        self._detected_identity = copy.deepcopy(payload.get("info", {}).get("identity", {}))
        self._normalized_telemetry = self._normalize_telemetry_payload(payload["telemetry"])
        self._latest_context, self._previous_context = self._select_latest_context(self._normalized_telemetry)

    def _validate_payload(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            raise ValueError("Node snapshot root must be a JSON object")

        required_sections = ("info", "live", "status_events", "telemetry")
        for section in required_sections:
            value = payload.get(section)
            if not isinstance(value, dict):
                raise ValueError(f"Node snapshot section '{section}' must be a JSON object")

        identity = payload["info"].get("identity")
        if not isinstance(identity, dict):
            raise ValueError("Node snapshot info.identity must be a JSON object")

        if not payload["telemetry"]:
            raise ValueError("Node snapshot telemetry is empty")

    def _normalize_telemetry_payload(self, telemetry_payload: dict[str, Any]) -> dict[str, Any]:
        normalized_payload: dict[str, Any] = {}

        for date_key, day_payload in telemetry_payload.items():
            if not isinstance(day_payload, dict):
                continue

            normalized_day: dict[str, Any] = {}
            for event_key, record_payload in day_payload.items():
                if not isinstance(record_payload, dict):
                    continue
                normalized_day[str(event_key)] = self._normalize_record_payload(record_payload)

            if normalized_day:
                normalized_payload[str(date_key)] = canonicalize_json(normalized_day)

        if not normalized_payload:
            raise ValueError("Node snapshot telemetry does not contain any valid event payloads")

        return canonicalize_json(normalized_payload)

    def _normalize_record_payload(self, record_payload: dict[str, Any]) -> dict[str, Any]:
        normalized = copy.deepcopy(record_payload)
        packet_payload = normalized.setdefault("packet", {})
        if not isinstance(packet_payload, dict):
            packet_payload = {}
            normalized["packet"] = packet_payload

        npk_payload = packet_payload.get("npk_data")
        if isinstance(npk_payload, dict):
            npk_payload.setdefault("sensor_id", self.settings.npk_sensor_id)
            npk_payload.setdefault("sensor_type", self.settings.npk_sensor_type)

        sht30_payload = packet_payload.get("sht30_data")
        if isinstance(sht30_payload, dict):
            sht30_payload.setdefault("sensor_id", self.settings.sht30_sensor_id)
            sht30_payload.setdefault("sensor_type", self.settings.sht30_sensor_type)

        system_payload = packet_payload.get("system_data")
        if isinstance(system_payload, dict):
            system_payload.setdefault(
                "transport",
                self._source_payload.get("info", {}).get("network", {}).get("transport")
                if isinstance(self._source_payload, dict)
                else None,
            )

        return canonicalize_json(normalized)

    def _select_latest_context(
        self,
        telemetry_payload: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        ranked_records: list[dict[str, Any]] = []

        for date_key, day_payload in telemetry_payload.items():
            if not isinstance(day_payload, dict):
                continue
            for event_key, record_payload in day_payload.items():
                if not isinstance(record_payload, dict):
                    continue

                ts_server = self._as_int(record_payload.get("ts_server"))
                ts_device = self._as_int(record_payload.get("ts_device"))
                if ts_server is None or ts_device is None:
                    continue

                ranked_records.append(
                    {
                        "date_key": str(date_key),
                        "event_key": str(event_key),
                        "record": record_payload,
                        "ts_server": ts_server,
                        "ts_device": ts_device,
                    }
                )

        ranked_records.sort(key=lambda item: (item["ts_server"], item["event_key"]))

        if not ranked_records:
            return None, None

        latest_context = ranked_records[-1]
        previous_context = ranked_records[-2] if len(ranked_records) > 1 else None
        return latest_context, previous_context

    def _build_latest_meta_payload(self) -> dict[str, Any]:
        assert self._latest_context is not None

        latest_record = self._latest_context["record"]
        latest_date_key = self._latest_context["date_key"]
        latest_event_key = self._latest_context["event_key"]
        latest_ts_server = self._latest_context["ts_server"]
        latest_ts_device = self._latest_context["ts_device"]

        previous_context = self._previous_context
        previous_ts_server = None if previous_context is None else previous_context["ts_server"]
        previous_ts_device = None if previous_context is None else previous_context["ts_device"]
        primary_poll_after_sec = int(
            self._source_payload.get("info", {}).get("config", {}).get("wake_interval_sec")
            or self.settings.primary_poll_after_sec
        )
        retry_after_no_change_sec = self.settings.retry_after_no_change_sec
        tolerance = max(60, primary_poll_after_sec // 3)
        expected_min = max(0, primary_poll_after_sec - tolerance)
        expected_max = primary_poll_after_sec + tolerance
        delta_device_sec = None if previous_ts_device is None else latest_ts_device - previous_ts_device
        delta_server_sec = None if previous_ts_server is None else latest_ts_server - previous_ts_server

        return canonicalize_json(
            {
                "schema_version": 1,
                "node_id": self._detected_identity.get("node_id") or self.settings.node_id,
                "detected_device_uid": self._detected_identity.get("device_uid"),
                "detected_site_id": self._detected_identity.get("site_id"),
                "latest_date_key": latest_date_key,
                "latest_event_key": latest_event_key,
                "latest_local_iso": latest_record.get("sample_time_local")
                or latest_record.get("upload_time_local"),
                "latest_path": f"{self.settings.node_id}/telemetry/{latest_date_key}/{latest_event_key}",
                "previous_date_key": None if previous_context is None else previous_context["date_key"],
                "previous_event_key": None if previous_context is None else previous_context["event_key"],
                "previous_path": None
                if previous_context is None
                else f"{self.settings.node_id}/telemetry/{previous_context['date_key']}/{previous_context['event_key']}",
                "previous_ts_device": previous_ts_device,
                "previous_ts_server": previous_ts_server,
                "delta_device_sec": delta_device_sec,
                "delta_server_sec": delta_server_sec,
                "expected_device_min_sec": expected_min,
                "expected_device_max_sec": expected_max,
                "expected_server_min_sec": expected_min,
                "expected_server_max_sec": expected_max,
                "device_in_expected_range": None
                if delta_device_sec is None
                else expected_min <= delta_device_sec <= expected_max,
                "server_in_expected_range": None
                if delta_server_sec is None
                else expected_min <= delta_server_sec <= expected_max,
                "primary_poll_after_sec": primary_poll_after_sec,
                "retry_after_no_change_sec": retry_after_no_change_sec,
                "record_sha256": sha256_hex(serialize_json(canonicalize_json(latest_record))),
                "ts_device": latest_ts_device,
                "ts_server": latest_ts_server,
                "updated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )

    def _as_int(self, value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
