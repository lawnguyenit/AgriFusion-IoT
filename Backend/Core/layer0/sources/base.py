from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

try:
    from Config.runtime import BackendSettings
except ModuleNotFoundError:
    from ....Config.runtime import BackendSettings

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
    def __init__(self, settings: BackendSettings):
        self.settings = settings
        self.source_sha256: str | None = None
        self._source_payload: dict[str, Any] | None = None
        self._ordered_source_payload: dict[str, Any] | None = None
        self._normalized_telemetry: dict[str, Any] | None = None
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
                "snapshot_mode": self._snapshot_mode,
                "telemetry_date_count": len(self._normalized_telemetry or {}),
                "telemetry_record_count": sum(
                    len(day_payload)
                    for day_payload in (self._normalized_telemetry or {}).values()
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
        self._normalized_telemetry = self._normalize_telemetry_payload(payload.get("telemetry", {}))
        latest_record = self._normalize_latest_payload(payload.get("latest"))
        self._latest_context, self._previous_context = self._select_latest_context(
            telemetry_payload=self._normalized_telemetry,
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

    def _normalize_telemetry_payload(self, telemetry_payload: dict[str, Any]) -> dict[str, Any]:
        normalized_payload: dict[str, Any] = {}

        for date_key, day_payload in telemetry_payload.items():
            if not isinstance(day_payload, dict):
                continue

            normalized_day: dict[str, Any] = {}
            for event_key, record_payload in day_payload.items():
                if not isinstance(record_payload, dict):
                    continue
                normalized_record = self._normalize_record_payload(record_payload)
                if normalized_record is None:
                    continue
                normalized_day[str(event_key)] = normalized_record

            if normalized_day:
                normalized_payload[str(date_key)] = canonicalize_json(normalized_day)

        return canonicalize_json(normalized_payload)

    def _normalize_latest_payload(self, latest_payload: Any) -> dict[str, Any] | None:
        if not isinstance(latest_payload, dict):
            return None
        return self._normalize_record_payload(latest_payload)

    def _normalize_record_payload(self, record_payload: dict[str, Any]) -> dict[str, Any] | None:
        if self._looks_like_canonical_v2_record(record_payload):
            return self._normalize_v2_record_payload(record_payload)
        return self._normalize_legacy_record_payload(record_payload)

    def _looks_like_canonical_v2_record(self, record_payload: dict[str, Any]) -> bool:
        return (
            isinstance(record_payload.get("sensor_record"), dict)
            and isinstance(record_payload.get("sim_record"), dict)
            and isinstance(record_payload.get("system_record"), dict)
        )

    def _normalize_legacy_record_payload(self, record_payload: dict[str, Any]) -> dict[str, Any]:
        normalized = copy.deepcopy(record_payload)
        normalized.pop("quality", None)

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
            if system_payload.get("battery_v") == -1:
                system_payload["battery_v"] = None
            if system_payload.get("ip") == "0.0.0.0":
                system_payload.pop("ip", None)

            for noisy_key in ("buffer_reason", "debug", "debug_log", "at_log", "gps_status"):
                noisy_value = system_payload.get(noisy_key)
                if isinstance(noisy_value, str) and len(noisy_value) > 160:
                    system_payload.pop(noisy_key, None)

        return canonicalize_json(normalized)

    def _normalize_v2_record_payload(self, record_payload: dict[str, Any]) -> dict[str, Any]:
        normalized = copy.deepcopy(record_payload)
        system_record: dict[str, Any] = normalized.get("system_record", {})
        time_payload: dict[str, Any] = system_record.get("time", {})
        identity_payload: dict[str, Any] = system_record.get("identity", {})
        sync_payload: dict[str, Any] = system_record.get("sync", {})
        sensor_record: dict[str, Any] = normalized.get("sensor_record", {})
        sim_record: dict[str, Any] = normalized.get("sim_record", {})

        ts_sample = self._resolve_v2_ts_sample(time_payload)
        ts_server = self._resolve_v2_ts_server(time_payload, ts_sample)
        date_key = self._resolve_v2_date_key(identity_payload, ts_sample)
        sample_time_local = self._format_local_iso(ts_sample)
        upload_time_local = self._format_local_iso(ts_server)

        npk_sensor_id, npk_sensor_payload = self._select_sensor_payload(
            sensor_record=sensor_record,
            preferred_id=self.settings.npk_sensor_id,
            fallback_id="soil_7in1_01",
        )
        sht30_sensor_id, sht30_sensor_payload = self._select_sensor_payload(
            sensor_record=sensor_record,
            preferred_id=self.settings.sht30_sensor_id,
            fallback_id="air_sht30_01",
        )

        npk_packet = self._build_legacy_npk_packet(npk_sensor_id, npk_sensor_payload)
        sht30_packet = self._build_legacy_sht30_packet(sht30_sensor_id, sht30_sensor_payload)

        return canonicalize_json(
            {
                "schema_version": 2,
                "ts_sample": ts_sample,
                "ts_device": ts_sample,
                "ts_server": ts_server,
                "sample_time_local": sample_time_local,
                "upload_time_local": upload_time_local,
                "packet": {
                    "npk_data": npk_packet,
                    "sht30_data": sht30_packet,
                    "system_data": {
                        "sample_epoch_sec": ts_sample,
                        "sample_time_valid": bool(time_payload.get("time_valid")),
                        "sample_date_key": date_key,
                        "transport": sim_record.get("transport"),
                        "send_state": self._derive_send_state(sync_payload),
                    },
                },
                "sensors": {
                    "npk": self._build_sensor_trace_payload(
                        sensor_id=npk_packet.get("sensor_id"),
                        sensor_type=npk_packet.get("sensor_type"),
                        read_status=npk_sensor_payload.get("read_status"),
                    ),
                    "sht30": self._build_sensor_trace_payload(
                        sensor_id=sht30_packet.get("sensor_id"),
                        sensor_type=sht30_packet.get("sensor_type"),
                        read_status=sht30_sensor_payload.get("read_status"),
                    ),
                },
                "system_record": normalized.get("system_record"),
                "sim_record": normalized.get("sim_record"),
                "sensor_record": normalized.get("sensor_record"),
            }
        )

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
        ts_server = self._as_int(record_payload.get("ts_server"))
        ts_device = self._as_int(record_payload.get("ts_device"))

        packet_payload = record_payload.get("packet", {})
        system_payload = packet_payload.get("system_data", {})
        if ts_device is None:
            ts_device = self._as_int(system_payload.get("sample_epoch_sec"))
        if ts_server is None:
            ts_server = ts_device

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

        return canonicalize_json(
            {
                "schema_version": 1,
                "node_id": self._detected_identity.get("node_id") or self.settings.node_id,
                "detected_device_uid": self._detected_identity.get("device_uid"),
                "detected_site_id": self._detected_identity.get("site_id"),
                "latest_date_key": latest_date_key,
                "latest_event_key": latest_event_key,
                "latest_local_iso": latest_record.get("sample_time_local") or latest_record.get("upload_time_local"),
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
                "record_sha256": sha256_hex(serialize_json(canonicalize_json(latest_record))),
                "ts_device": latest_ts_device,
                "ts_server": latest_ts_server,
                "updated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )

    def _resolve_v2_ts_sample(self, time_payload: dict[str, Any]) -> int | None:
        ts_sample = self._as_int(time_payload.get("ts_sample"))
        if ts_sample is not None and ts_sample > 0:
            return ts_sample
        return None

    def _resolve_v2_ts_server(self, time_payload: dict[str, Any], ts_sample: int | None) -> int | None:
        ts_server = self._as_int(time_payload.get("ts_server"))
        if ts_server is not None and ts_server > 0:
            return ts_server
        return ts_sample

    def _resolve_v2_date_key(self, identity_payload: dict[str, Any], ts_sample: int | None) -> str | None:
        record_path = str(identity_payload.get("record_path") or "")
        parts = [part for part in record_path.split("/") if part]
        if len(parts) >= 4 and parts[-3] == "telemetry":
            return parts[-2]
        if ts_sample is not None and ts_sample > 0:
            return datetime.fromtimestamp(ts_sample, tz=self.settings.timezone).date().isoformat()
        return None

    def _select_sensor_payload(
        self,
        *,
        sensor_record: dict[str, Any],
        preferred_id: str,
        fallback_id: str,
    ) -> tuple[str, dict[str, Any]]:
        candidate = sensor_record.get(preferred_id)
        if isinstance(candidate, dict):
            return preferred_id, candidate
        candidate = sensor_record.get(fallback_id)
        if isinstance(candidate, dict):
            return fallback_id, candidate
        for sensor_id, payload in sensor_record.items():
            if isinstance(payload, dict):
                return str(sensor_id), payload
        return preferred_id, {}

    def _build_legacy_npk_packet(self, sensor_id: str, sensor_payload: dict[str, Any]) -> dict[str, Any]:
        values = sensor_payload.get("values", {}) if isinstance(sensor_payload.get("values"), dict) else {}
        status = sensor_payload.get("read_status", {}) if isinstance(sensor_payload.get("read_status"), dict) else {}
        return canonicalize_json(
            {
                "sensor_id": sensor_id or self.settings.npk_sensor_id,
                "sensor_type": sensor_payload.get("sensor_type") or self.settings.npk_sensor_type,
                "read_ok": bool(status.get("read_ok")),
                "npk_values_valid": bool(status.get("sample_valid")),
                "frame_ok": status.get("frame_ok"),
                "crc_ok": status.get("crc_ok"),
                "error_code": status.get("error_code"),
                "error_code_raw": status.get("raw_error_code"),
                "retry_count": status.get("retry_count"),
                "timeout_ms": status.get("timeout_ms"),
                "read_duration_ms": status.get("read_elapsed_ms"),
                "consecutive_fail_count": status.get("consecutive_fail_count"),
                "recovered_after_fail": status.get("recovered_after_fail"),
                "temp": values.get("soil_temp_c"),
                "hum": values.get("soil_moisture_pct"),
                "ph": values.get("soil_ph"),
                "ec": values.get("soil_ec_us_cm"),
                "N": values.get("soil_n_proxy"),
                "P": values.get("soil_p_proxy"),
                "K": values.get("soil_k_proxy"),
            }
        )

    def _build_legacy_sht30_packet(self, sensor_id: str, sensor_payload: dict[str, Any]) -> dict[str, Any]:
        values = sensor_payload.get("values", {}) if isinstance(sensor_payload.get("values"), dict) else {}
        status = sensor_payload.get("read_status", {}) if isinstance(sensor_payload.get("read_status"), dict) else {}
        return canonicalize_json(
            {
                "sensor_id": sensor_id or self.settings.sht30_sensor_id,
                "sensor_type": sensor_payload.get("sensor_type") or self.settings.sht30_sensor_type,
                "sht_read_ok": bool(status.get("read_ok")),
                "sht_sample_valid": bool(status.get("sample_valid")),
                "sht_error": status.get("error_code"),
                "sht_retry_count": status.get("retry_count"),
                "sht_read_elapsed_ms": status.get("read_elapsed_ms"),
                "sht_invalid_streak": status.get("invalid_streak"),
                "sht_temp_c": values.get("air_temp_c"),
                "sht_hum_pct": values.get("air_rh_pct"),
            }
        )

    def _build_sensor_trace_payload(
        self,
        *,
        sensor_id: Any,
        sensor_type: Any,
        read_status: Any,
    ) -> dict[str, Any]:
        read_status = read_status if isinstance(read_status, dict) else {}
        return canonicalize_json(
            {
                "sensor_id": sensor_id,
                "sensor_type": sensor_type,
                "read_ok": read_status.get("read_ok"),
                "sample_valid": read_status.get("sample_valid"),
            }
        )

    def _derive_send_state(self, sync_payload: dict[str, Any]) -> str:
        if not isinstance(sync_payload, dict):
            return "unknown"
        if bool(sync_payload.get("replayed")):
            return "replayed"
        if bool(sync_payload.get("buffered")):
            return "buffered"
        if bool(sync_payload.get("telemetry_persisted")):
            return "persisted"
        return "sampled"

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
