"""Records in the exact JSON shape the Node2 firmware publishes to RTDB (s4g contract).

Derived by reading (not by running) the firmware:
  firmware/lib/publish_RawTelemetryReporter/src/RawTelemetryReporter.cpp
      populateCoreRecord / populateSht30Record / populateSoilRecord / populate*Network
      (key set, nesting, null-vs-absent, which diagnostics are kept on failure)
      publishRecord (identity.record_id/record_path, sync.telemetry_persisted/path)
  firmware/lib/publish_FirebasePipeline/src/FirebasePipeline.cpp
      updateUploadState / updateSyncState (direct path), bufferRawRecord (buffered),
      replayOfflineIfAnyDetailed + restampReplayRecordIfNeeded (replay)
  firmware/lib/publish_NodeRuntimePublisher/src/NodeRuntimePublisher.cpp
      publishLatestIfNewer / publishLatestMeta (``latest/current`` + ``latest/meta``)

The record stored under ``telemetry/`` is the document as it was at the moment of
``publishRecord`` (later in-memory updates such as http_status/latency are NOT in RTDB);
``latest/current`` is written afterwards and therefore differs (latest_updated=true,
http_status/latency set). Values are made up; firmware constants are copied from
firmware/lib/config_Config/src/Config.h (NODE_ID Node2, sensor ids/types).
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from typing import Any

NODE_ID = "Node2"
TZ = timezone(timedelta(hours=7))  # APP_NODE_TIMEZONE Asia/Ho_Chi_Minh (no DST)
TELEMETRY_ROOT = f"{NODE_ID}/telemetry"  # APP_RTDB_PATH_NODE_TELEMETRY without leading '/'
PAYLOAD_BYTES = 1830
INTERVAL_SEC = 900


def date_key(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=TZ).date().isoformat()


def record_path(ts: int) -> str:
    # makeTelemetryPath: String(APP_RTDB_PATH_NODE_TELEMETRY) + "/" + date + "/" + ts
    return f"/{TELEMETRY_ROOT}/{date_key(ts)}/{ts}"


def _upload_slot(stage: str) -> dict[str, Any]:
    # fillUploadSlotDefaults
    return {
        "attempted": False,
        "upload_ok": False,
        "upload_stage": stage,
        "http_status": None,
        "tls_ok": None,
        "upload_latency_ms": None,
        "payload_bytes": PAYLOAD_BYTES,
        "buffer_reason_code": "",
        "last_error_code": "",
    }


def _set_upload(record: dict, phase: str, *, attempted: bool, ok: bool, stage: str,
                http: int = -1, latency: int = -1, tls: bool, error: str = "", reason: str = "") -> None:
    # updateUploadState: http/latency null when < 0
    slot = record["sim_record"]["upload"][phase]
    slot.update({
        "attempted": attempted,
        "upload_ok": ok,
        "upload_stage": stage,
        "http_status": http if http >= 0 else None,
        "upload_latency_ms": latency if latency >= 0 else None,
        "tls_ok": tls,
        "last_error_code": error,
        "buffer_reason_code": reason,
    })


def _set_sync(record: dict, *, persisted: bool, path: str, buffered: bool, replayed: bool,
              latest_updated: bool, reason: str = "", error: str = "") -> None:
    # updateSyncState: telemetry_record_path null unless persisted
    record["system_record"]["sync"].update({
        "telemetry_persisted": persisted,
        "telemetry_record_path": path if persisted and path else None,
        "buffered": buffered,
        "replayed": replayed,
        "latest_updated": latest_updated,
        "buffer_reason_code": reason,
        "last_error_code": error,
    })


def _sht_ok(temp: float, hum: float) -> dict[str, Any]:
    return {
        "sensor_type": "air_temp_humidity",
        "values": {"air_temp_c": temp, "air_rh_pct": hum},
        "read_status": {
            "read_ok": True, "sample_valid": True, "value_valid": True, "values_available": True,
            "values_recorded_with_error": False, "error_code": "", "retry_count": 0,
            "read_elapsed_ms": 32, "invalid_streak": 0, "i2c_address_ack": True, "i2c_error": 0,
        },
    }


def _sht_zero_frame() -> dict[str, Any]:
    # invalid read: values null, diagnostics kept (keepShtDiagnostics), the known -45 C / 0 % case
    return {
        "sensor_type": "air_temp_humidity",
        "values": {"air_temp_c": None, "air_rh_pct": None},
        "read_status": {
            "read_ok": True, "sample_valid": False, "value_valid": False, "values_available": True,
            "values_recorded_with_error": True, "error_code": "measurement_invalid_zero_frame",
            "retry_count": 2, "read_elapsed_ms": 95, "invalid_streak": 3,
            "i2c_address_ack": True, "i2c_error": 0,
            "init_attempts": 1, "init_error": "ok", "init_probe_read_ok": True,
            "frame_ok": True, "temp_crc_ok": True, "hum_crc_ok": True, "received_bytes": 6,
            "raw_values_available": True, "raw_temp": 0, "raw_hum": 0,
            "observed_temp_c": -45.0, "observed_hum_pct": 0.0,
            "init_probe_temp_c": 27.1, "init_probe_hum_pct": 71.0,
        },
    }


def _soil_ok(i: int) -> dict[str, Any]:
    # compact read_status of a valid read (no field maps)
    return {
        "sensor_type": "soil_multi_sensor",
        "values": {
            "soil_temp_c": 26.5 + i / 10, "soil_moisture_pct": 41.0 + i, "soil_ph": 6.3,
            "soil_ec_us_cm": 410 + i, "soil_n_proxy": 30 + i, "soil_p_proxy": 18, "soil_k_proxy": 90,
        },
        "read_status": {
            "read_ok": True, "sample_valid": True, "crc_ok": True, "frame_ok": True,
            "error_code": "", "raw_error_code": 0, "retry_count": 0, "read_elapsed_ms": 230,
            "timeout_ms": 1000, "consecutive_fail_count": 0, "recovered_after_fail": False,
            "partial_values_included": False,
            "soil_temp_valid": True, "soil_temp_source": "ds18b20",
            "soil_moisture_valid": True, "soil_moisture_source": "soil_moisture_v1_2",
            "ph_protocol_ok": True, "ph_valid": True, "ph_state": "ok",
            "ec_valid": True, "ec_source": "npk_proxy_derived", "ec_measurement_kind": "derived_proxy",
            "n_proxy_valid": True, "p_proxy_valid": True, "k_proxy_valid": True,
            "soil_moisture_calibration_status": "provisional_default",
            "soil_moisture_calibration_profile": "manufacturer_example_scaled_12bit_direction_adjusted",
            "soil_moisture_value_semantics": "relative_index_0_100_not_vwc",
            "soil_moisture_raw_adc": 2630, "soil_moisture_voltage_mv": 2240,
            "soil_moisture_install_depth_cm_min": 10.0, "soil_moisture_install_depth_cm_max": 15.0,
            "read_map": "npk7_v2",
        },
    }


def _soil_timeout() -> dict[str, Any]:
    # failed read: values null; maps + raw registers kept (!sampleValid || !read_ok)
    status = _soil_ok(0)["read_status"]
    status.update({
        "read_ok": False, "sample_valid": False, "crc_ok": False, "frame_ok": False,
        "error_code": "modbus_response_timeout", "raw_error_code": 226, "retry_count": 3,
        "consecutive_fail_count": 2, "soil_temp_valid": False, "soil_moisture_valid": False,
        "ph_protocol_ok": False, "ph_valid": False, "ph_state": "unknown", "ec_valid": False,
        "n_proxy_valid": False, "p_proxy_valid": False, "k_proxy_valid": False,
        "field_validity": {"temp": False, "hum": False, "ph": False, "ec": False, "N": False, "P": False, "K": False},
        "field_value_validity": {"temp": False, "hum": False, "ph": False, "ec": False, "N": False, "P": False, "K": False},
        "field_source": {"temp": "ds18b20", "hum": "soil_moisture_v1_2", "ph": "modbus_register", "ec": "npk_proxy_derived"},
        "raw_registers": [0, 0, 0, 0, 0, 0, 0],
        "map_diagnostics": {"map": "npk7_v2", "frames": 0},
    })
    return {
        "sensor_type": "soil_multi_sensor",
        "values": {k: None for k in ("soil_temp_c", "soil_moisture_pct", "soil_ph", "soil_ec_us_cm",
                                     "soil_n_proxy", "soil_p_proxy", "soil_k_proxy")},
        "read_status": status,
    }


def build_core_record(ts: int | None, seq: int, *, sht: dict, soil: dict, wake: str = "timer",
                      uptime: int = 41) -> dict[str, Any]:
    """populateCoreRecord before publish (ts None = clock not valid yet)."""
    time_valid = ts is not None
    return {
        "sensor_record": {"air_sht30_01": sht, "soil_7in1_01": soil},
        "sim_record": {
            "transport": "sim",
            "network": {
                "registered": True, "attached": True, "pdp_active": True, "operator_valid": True,
                "operator": "Viettel", "rat": None, "signal_dbm": -79, "signal_csq": 17,
                "signal_valid": True, "ip_valid": True, "local_ip_valid": True,
                "local_ip": "10.20.30.40", "local_ip_source": "AT+CGPADDR",
            },
            "upload": {"target": "firebase_rtdb", "direct": _upload_slot("not_attempted"),
                       "replay": _upload_slot("not_replayed")},
        },
        "system_record": {
            "schema_version": 2, "source_level": "raw_telemetry", "synthetic": False,
            "manual_edit": False, "debug_mode": False,
            "identity": {
                "node_id": NODE_ID, "site_id": "contract-site", "device_uid": "esp32-contract-0001",
                "record_id": str(ts) if time_valid else None,
                "record_path": record_path(ts) if time_valid else None,
                "seq_no": seq, "boot_id": "boot-c01",
            },
            "time": {
                "ts_sample": ts, "ts_server": None, "timezone": "Asia/Ho_Chi_Minh",
                "clock_source": "network_time" if time_valid else "unsynced_device",
                "time_valid": time_valid, "time_reconstructed": False,
                "sample_interval_sec": INTERVAL_SEC, "device_uptime_sec": uptime,
            },
            "cycle": {"record_type": "telemetry", "wake_reason": wake, "cycle_type": "periodic",
                      "cycle_duration_ms": 262, "sleep_planned_sec": INTERVAL_SEC},
            "power": {"power_type": "mains", "battery_mv": None, "battery_pct": None, "panel_mv": None,
                      "charge_state": None, "brownout_count": None},
            "device_health": {"heap_free": 187000, "reset_count": None, "reset_reason": "deep_sleep",
                              "watchdog_count": None, "storage_free_bytes": None, "buffer_queue_len": None},
            "firmware": {"firmware_version": "2.3.0", "build_id": "build_Nov_20_2026_10_00_00",
                         "config_version": "cfg-7", "calibration_version": "cal-3",
                         "running_partition": "app0"},
            "integrity": {"record_hash": None, "payload_crc_ok": None,
                          "duplicate_policy": "deterministic_key", "overwrite_protected": True},
            "sync": {"telemetry_persisted": False, "telemetry_record_path": None, "buffered": False,
                     "replayed": False, "latest_updated": False, "buffer_reason_code": "",
                     "last_error_code": ""},
        },
    }


def _publish(record: dict) -> dict:
    """RawTelemetryReporter::publishRecord: identity + persisted path, then PUT (this copy is in RTDB)."""
    ts = record["system_record"]["time"]["ts_sample"]
    path = record_path(ts)
    record["system_record"]["identity"]["record_id"] = str(ts)
    record["system_record"]["identity"]["record_path"] = path
    record["system_record"]["sync"]["telemetry_persisted"] = True
    record["system_record"]["sync"]["telemetry_record_path"] = path
    return copy.deepcopy(record)


def direct_upload(record: dict) -> tuple[dict, dict]:
    """Return (telemetry copy, latest/current copy) for a successful direct upload."""
    _set_upload(record, "direct", attempted=True, ok=True, stage="direct_upload", tls=True)
    _set_sync(record, persisted=False, path="", buffered=False, replayed=False, latest_updated=False)
    stored = _publish(record)
    path = stored["system_record"]["sync"]["telemetry_record_path"]
    _set_upload(record, "direct", attempted=True, ok=True, stage="direct_upload", http=200, latency=840, tls=True)
    _set_sync(record, persisted=True, path=path, buffered=False, replayed=False, latest_updated=False)
    latest = copy.deepcopy(record)
    latest["system_record"]["sync"]["latest_updated"] = True  # publishLatestIfNewer
    return stored, latest


def buffered_then_replayed(record: dict, *, replay_utc: int) -> dict:
    """Direct upload fails -> offline buffer -> later replay (restamped: clock was invalid)."""
    _set_upload(record, "direct", attempted=True, ok=True, stage="direct_upload", tls=True)
    _set_sync(record, persisted=False, path="", buffered=False, replayed=False, latest_updated=False)
    err = "invalid_time_quarantined"  # publishRecord rejects a record without a valid sample time
    _set_upload(record, "direct", attempted=True, ok=False, stage=err, tls=True, error=err, reason=err)
    _set_sync(record, persisted=False, path="", buffered=False, replayed=False, latest_updated=False,
              reason=err, error=err)
    _set_sync(record, persisted=False, path="", buffered=True, replayed=False, latest_updated=False,
              reason=err, error=err)  # bufferRawRecord; this line goes to the SD card
    # replay: restampReplayRecordIfNeeded
    t = record["system_record"]["time"]
    t.update({"ts_sample": replay_utc, "clock_source": "reconstructed_on_replay",
              "time_valid": True, "time_reconstructed": True})
    record["system_record"]["identity"]["record_id"] = str(replay_utc)
    record["system_record"]["identity"]["record_path"] = record_path(replay_utc)
    _set_upload(record, "replay", attempted=True, ok=True, stage="replay_upload", tls=True)
    _set_sync(record, persisted=False, path="", buffered=False, replayed=True, latest_updated=False)
    return _publish(record)


def latest_meta(latest: dict) -> dict[str, Any]:
    """NodeRuntimePublisher::publishLatestMeta."""
    ts = latest["system_record"]["time"]["ts_sample"]
    return {
        "schema_version": 1, "node_id": NODE_ID, "detected_device_uid": "esp32-contract-0001",
        "detected_site_id": "contract-site", "latest_date_key": date_key(ts),
        "latest_event_key": latest["system_record"]["identity"]["record_id"],
        "latest_path": latest["system_record"]["identity"]["record_path"].lstrip("/"),
        "ts_device": latest["system_record"]["time"]["device_uptime_sec"], "ts_server": ts,
        "primary_poll_after_sec": INTERVAL_SEC, "retry_after_no_change_sec": 300,
        "source_type": "firebase", "source_uri": f"firebase://{NODE_ID}/latest/meta",
        "updated_at_utc": ts,
    }


T0 = 1792800000  # 2026-10-23 07:00 +07


def build_node_snapshot() -> dict[str, Any]:
    """The RTDB subtree /Node2 as a JSON export: info + latest/{current,meta} + telemetry."""
    telemetry: dict[str, dict[str, Any]] = {}
    latest = None

    def add(stored: dict) -> None:
        ts = stored["system_record"]["time"]["ts_sample"]
        telemetry.setdefault(date_key(ts), {})[str(ts)] = stored

    for i, (sht, soil, wake) in enumerate([
        (_sht_ok(27.0, 70.0), _soil_ok(0), "power_on_or_reset"),
        (_sht_zero_frame(), _soil_ok(1), "timer"),      # SHT30 error record
        (_sht_ok(27.4, 69.0), _soil_timeout(), "timer"),  # NPK error record
    ]):
        stored, latest = direct_upload(build_core_record(T0 + i * INTERVAL_SEC, i + 1, sht=sht, soil=soil, wake=wake))
        add(stored)
    # sampled while the clock was invalid, buffered, replayed one interval later
    add(buffered_then_replayed(build_core_record(None, 4, sht=_sht_ok(27.9, 68.0), soil=_soil_ok(3)),
                               replay_utc=T0 + 3 * INTERVAL_SEC + 7))
    stored, latest = direct_upload(build_core_record(T0 + 4 * INTERVAL_SEC, 5, sht=_sht_ok(28.1, 67.0), soil=_soil_ok(4)))
    add(stored)
    return {
        "info": {"identity": {"node_id": NODE_ID, "site_id": "contract-site", "device_uid": "esp32-contract-0001"},
                 "config_current": {"wake_interval_sec": INTERVAL_SEC}},
        "latest": {"current": latest, "meta": latest_meta(latest)},
        "telemetry": telemetry,
    }
