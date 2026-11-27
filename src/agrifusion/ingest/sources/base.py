"""Snapshot source logic shared by the JSON-export and Firebase-root adapters.

Ingest keeps source records verbatim. This module only *reads* a few fields of a
record (timestamps, identity) to choose the latest record and build ``latest_meta``;
it never rewrites records. All translation of firmware records into canonical rows
lives in ``agrifusion.canonical.adapters``.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from agrifusion.settings.runtime import BackendSettings

from ..record_store import record_sha256
from ..stores.artifact_store import base_source_manifest_payload
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


def is_v2_record(record_payload: Any) -> bool:
    """Firmware schema v2 record (RawTelemetryReporter): sensor/sim/system sections."""
    return (
        isinstance(record_payload, dict)
        and isinstance(record_payload.get("sensor_record"), dict)
        and isinstance(record_payload.get("sim_record"), dict)
        and isinstance(record_payload.get("system_record"), dict)
    )


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def record_times(record_payload: dict[str, Any]) -> tuple[int | None, int | None]:
    """Return (ts_device, ts_server) used for ordering/sync; reads, never modifies.

    v2: ts_device = system_record.time.ts_sample (if > 0); ts_server = time.ts_server
    if > 0, else ts_sample. Legacy v1: top-level ts_device (or
    packet.system_data.sample_epoch_sec) and ts_server (default ts_device).
    """
    if is_v2_record(record_payload):
        time_payload = record_payload["system_record"].get("time")
        time_payload = time_payload if isinstance(time_payload, dict) else {}
        ts_sample = _as_int(time_payload.get("ts_sample"))
        ts_sample = ts_sample if ts_sample is not None and ts_sample > 0 else None
        ts_server = _as_int(time_payload.get("ts_server"))
        ts_server = ts_server if ts_server is not None and ts_server > 0 else ts_sample
        return ts_sample, ts_server
    ts_server = _as_int(record_payload.get("ts_server"))
    ts_device = _as_int(record_payload.get("ts_device"))
    packet_payload = record_payload.get("packet")
    system_payload = packet_payload.get("system_data") if isinstance(packet_payload, dict) else None
    if ts_device is None and isinstance(system_payload, dict):
        ts_device = _as_int(system_payload.get("sample_epoch_sec"))
    if ts_server is None:
        ts_server = ts_device
    return ts_device, ts_server


def extract_latest_record(latest_payload: Any) -> dict[str, Any] | None:
    """The firmware writes ``<node>/latest/current`` (record) + ``latest/meta``.

    A Firebase export of the node therefore has ``latest = {current, meta}``; older
    exports (and the golden fixture) put the record directly at ``latest``.
    """
    if not isinstance(latest_payload, dict):
        return None
    current = latest_payload.get("current")
    if isinstance(current, dict):
        return current
    return latest_payload


class SnapshotSourceMixin:
    def __init__(self, settings: BackendSettings):
        self.settings = settings
        self.source_sha256: str | None = None
        self._source_payload: dict[str, Any] | None = None
        self._ordered_source_payload: dict[str, Any] | None = None
        self._telemetry: dict[str, Any] | None = None
        self._latest_context: dict[str, Any] | None = None
        self._previous_context: dict[str, Any] | None = None
        self._detected_identity: dict[str, Any] = {}
        self._snapshot_mode = "legacy_v1"

    def _ensure_prepared(self) -> None:
        return None

    def fetch_latest_meta_payload(self) -> dict[str, Any] | None:
        self._ensure_prepared()
        if self._latest_context is None:
            raise ValueError("Source payload does not contain any latest or telemetry records")
        return self._build_latest_meta_payload()

    def fetch_latest_current_payload(self, latest_meta_payload: dict[str, Any]) -> dict[str, Any] | None:
        self._ensure_prepared()
        if self._latest_context is None:
            return None
        return copy.deepcopy(self._latest_context["record"])

    def fetch_full_history_payload(self) -> dict[str, Any] | None:
        """Source telemetry ``{date_key: {event_key: record}}``, records verbatim."""
        self._ensure_prepared()
        return copy.deepcopy(self._telemetry)

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
                "snapshot_mode": self._snapshot_mode,
                "telemetry_date_count": len(self._telemetry or {}),
                "telemetry_record_count": sum(
                    len(day_payload)
                    for day_payload in (self._telemetry or {}).values()
                    if isinstance(day_payload, dict)
                ),
                "latest_event_key": None if self._latest_context is None else self._latest_context["event_key"],
                "latest_date_key": None if self._latest_context is None else self._latest_context["date_key"],
                "latest_ts_server": None if self._latest_context is None else self._latest_context["ts_server"],
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
        self._snapshot_mode = self._detect_snapshot_mode(payload)
        self._telemetry = self._collect_telemetry(payload.get("telemetry", {}))
        latest_record = extract_latest_record(payload.get("latest"))
        self._latest_context, self._previous_context = self._select_latest_context(
            telemetry_payload=self._telemetry,
            latest_record=latest_record,
        )

    def _detect_snapshot_mode(self, payload: dict[str, Any]) -> str:
        if isinstance(payload.get("latest"), dict):
            return "canonical_v2"
        return "legacy_v1"

    def _validate_payload(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            raise ValueError("Node snapshot root must be a JSON object")

        info_payload = payload.get("info")
        telemetry_payload = payload.get("telemetry")
        if not isinstance(info_payload, dict):
            raise ValueError("Node snapshot section 'info' must be a JSON object")
        if not isinstance(telemetry_payload, dict):
            raise ValueError("Node snapshot section 'telemetry' must be a JSON object")

        identity = info_payload.get("identity")
        if not isinstance(identity, dict):
            raise ValueError("Node snapshot info.identity must be a JSON object")

        looks_legacy = all(isinstance(payload.get(section), dict) for section in ("live", "status_events"))
        looks_v2 = isinstance(payload.get("latest"), dict)
        if not looks_legacy and not looks_v2:
            raise ValueError("Node snapshot must contain legacy live/status_events or canonical latest")

    def _collect_telemetry(self, telemetry_payload: dict[str, Any]) -> dict[str, Any]:
        """Keep every dict record of every dict day, unchanged (only key order is canonical)."""
        collected: dict[str, Any] = {}
        for date_key, day_payload in telemetry_payload.items():
            if not isinstance(day_payload, dict):
                continue
            day = {
                str(event_key): record_payload
                for event_key, record_payload in day_payload.items()
                if isinstance(record_payload, dict)
            }
            if day:
                collected[str(date_key)] = canonicalize_json(day)
        return canonicalize_json(collected)

    def _select_latest_context(
        self,
        telemetry_payload: dict[str, Any],
        latest_record: dict[str, Any] | None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        ranked_records: list[dict[str, Any]] = []

        for date_key, day_payload in telemetry_payload.items():
            if not isinstance(day_payload, dict):
                continue
            for event_key, record_payload in day_payload.items():
                if not isinstance(record_payload, dict):
                    continue
                context = self._build_context(
                    record_payload=record_payload,
                    date_key=str(date_key),
                    event_key=str(event_key),
                    source_path=f"{self.settings.node_id}/telemetry/{date_key}/{event_key}",
                )
                if context is not None:
                    ranked_records.append(context)

        ranked_records.sort(key=lambda item: (item["ts_server"], item["event_key"]))

        telemetry_latest = ranked_records[-1] if ranked_records else None
        telemetry_previous = ranked_records[-2] if len(ranked_records) > 1 else None

        latest_context = None
        if isinstance(latest_record, dict):
            latest_date_key = self._infer_latest_date_key(latest_record, telemetry_latest)
            latest_event_key = self._infer_latest_event_key(latest_record)
            latest_path = self._infer_latest_source_path(latest_record)
            latest_context = self._build_context(
                record_payload=latest_record,
                date_key=latest_date_key,
                event_key=latest_event_key,
                source_path=latest_path,
            )

        if latest_context is not None and (
            telemetry_latest is None or latest_context["ts_server"] >= telemetry_latest["ts_server"]
        ):
            return latest_context, telemetry_latest

        return telemetry_latest, telemetry_previous

    def _build_context(
        self,
        *,
        record_payload: dict[str, Any],
        date_key: str,
        event_key: str,
        source_path: str,
    ) -> dict[str, Any] | None:
        ts_device, ts_server = record_times(record_payload)
        if ts_server is None or ts_device is None:
            return None
        return {
            "date_key": str(date_key),
            "event_key": str(event_key),
            "record": record_payload,
            "source_path": source_path,
            "ts_server": ts_server,
            "ts_device": ts_device,
        }

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
            self._source_payload.get("info", {}).get("config_current", {}).get("wake_interval_sec")
            or self._source_payload.get("info", {}).get("config", {}).get("wake_interval_sec")
            or self.settings.primary_poll_after_sec
        )
        retry_after_no_change_sec = self.settings.retry_after_no_change_sec
        tolerance = max(60, primary_poll_after_sec // 3)
        expected_min = max(0, primary_poll_after_sec - tolerance)
        expected_max = primary_poll_after_sec + tolerance
        delta_device_sec = None if previous_ts_device is None else latest_ts_device - previous_ts_device
        delta_server_sec = None if previous_ts_server is None else latest_ts_server - previous_ts_server

        # No run timestamp here: the same source gives the same latest_meta.
        return canonicalize_json(
            {
                "schema_version": 1,
                "node_id": self._detected_identity.get("node_id") or self.settings.node_id,
                "detected_device_uid": self._detected_identity.get("device_uid"),
                "detected_site_id": self._detected_identity.get("site_id"),
                "latest_date_key": latest_date_key,
                "latest_event_key": latest_event_key,
                "latest_local_iso": self._latest_local_iso(latest_record, latest_ts_device),
                "latest_path": self._latest_context["source_path"],
                "previous_date_key": None if previous_context is None else previous_context["date_key"],
                "previous_event_key": None if previous_context is None else previous_context["event_key"],
                "previous_path": None if previous_context is None else previous_context["source_path"],
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
                # Hash of the verbatim record as stored (record_store.encode_record).
                "record_sha256": record_sha256(latest_record),
                "ts_device": latest_ts_device,
                "ts_server": latest_ts_server,
            }
        )

    def _latest_local_iso(self, latest_record: dict[str, Any], ts_device: int | None) -> str | None:
        explicit = latest_record.get("sample_time_local") or latest_record.get("upload_time_local")
        if explicit:
            return str(explicit)
        if is_v2_record(latest_record) and ts_device is not None and ts_device > 0:
            return datetime.fromtimestamp(ts_device, tz=self.settings.timezone).isoformat()
        return None

    def _resolve_v2_ts_sample(self, time_payload: dict[str, Any]) -> int | None:
        ts_sample = _as_int(time_payload.get("ts_sample"))
        if ts_sample is not None and ts_sample > 0:
            return ts_sample
        return None

    def _resolve_v2_date_key(self, identity_payload: dict[str, Any], ts_sample: int | None) -> str | None:
        record_path = str(identity_payload.get("record_path") or "")
        parts = [part for part in record_path.split("/") if part]
        if len(parts) >= 4 and parts[-3] == "telemetry":
            return parts[-2]
        if ts_sample is not None and ts_sample > 0:
            return datetime.fromtimestamp(ts_sample, tz=self.settings.timezone).date().isoformat()
        return None

    def _infer_latest_date_key(
        self,
        latest_record: dict[str, Any],
        telemetry_latest: dict[str, Any] | None,
    ) -> str:
        system_record = latest_record.get("system_record", {})
        identity_payload = system_record.get("identity", {})
        time_payload = system_record.get("time", {})
        date_key = self._resolve_v2_date_key(identity_payload, self._resolve_v2_ts_sample(time_payload))
        if date_key:
            return date_key
        if telemetry_latest is not None:
            return str(telemetry_latest["date_key"])
        return "latest"

    def _infer_latest_event_key(self, latest_record: dict[str, Any]) -> str:
        system_record = latest_record.get("system_record", {})
        identity_payload = system_record.get("identity", {})
        record_id = identity_payload.get("record_id")
        if record_id:
            return str(record_id)
        ts_sample = self._resolve_v2_ts_sample(system_record.get("time", {}))
        if ts_sample:
            return str(ts_sample)
        return "latest"

    def _infer_latest_source_path(self, latest_record: dict[str, Any]) -> str:
        system_record = latest_record.get("system_record", {})
        sync_payload = system_record.get("sync", {})
        telemetry_record_path = sync_payload.get("telemetry_record_path")
        if telemetry_record_path:
            return str(telemetry_record_path).strip("/")
        identity_payload = system_record.get("identity", {})
        record_path = identity_payload.get("record_path")
        if record_path:
            return str(record_path).strip("/")
        return f"{self.settings.node_id}/latest"

    def _format_local_iso(self, ts_value: int | None) -> str | None:
        if ts_value is None or ts_value <= 0:
            return None
        return datetime.fromtimestamp(ts_value, tz=self.settings.timezone).isoformat()

    def _as_int(self, value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
