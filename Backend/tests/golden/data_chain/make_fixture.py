"""Deterministic generator for the synthetic Node2 JSON-export fixture.

Shape follows what IoT_Node/lib/RawTelemetryReporter publishes under /Node2
(``info``, ``latest``, ``telemetry/<local-date>/<ts_sample>``), schema_version 2.
All values are made up (no real data, no secrets).

Usage (from repo root):  python Backend/tests/golden/data_chain/make_fixture.py
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
TZ = timezone(timedelta(hours=7))  # Asia/Ho_Chi_Minh, no DST
NODE_ID = "Node2"
DEVICE_UID = "esp32-synthetic-0001"
SITE_ID = "Synthetic Site"
START = datetime(2026, 9, 1, 6, 0, 0, tzinfo=TZ)
INTERVAL_SEC = 3600
# Sample indexes that are missing (acquisition gap) and special cases.
GAP_INDEXES = {5, 6, 7}
SHT_INVALID = {3}
NPK_INVALID = {9}
REPLAYED = {11}
SAMPLE_COUNT = 30  # ~30 h => spans two local dates


def sht30(i: int) -> dict:
    valid = i not in SHT_INVALID
    status = {
        "read_ok": valid,
        "sample_valid": valid,
        "value_valid": valid,
        "values_available": valid,
        "values_recorded_with_error": False,
        "error_code": "" if valid else "crc_mismatch",
        "retry_count": 0 if valid else 2,
        "read_elapsed_ms": 31,
        "invalid_streak": 0 if valid else 1,
        "i2c_address_ack": True,
        "i2c_error": 0 if valid else 255,
    }
    if not valid:
        status.update({"frame_ok": True, "temp_crc_ok": False, "hum_crc_ok": True,
                       "received_bytes": 6, "raw_values_available": True,
                       "raw_temp": 28000, "raw_hum": 40000,
                       "observed_temp_c": None, "observed_hum_pct": None})
    values = {
        "air_temp_c": round(27.0 + (i % 12) * 0.35, 2) if valid else None,
        "air_rh_pct": round(70.0 - (i % 10) * 1.25, 2) if valid else None,
    }
    return {"sensor_type": "air_temp_humidity", "values": values, "read_status": status}


def soil(i: int) -> dict:
    valid = i not in NPK_INVALID
    values = {
        "soil_temp_c": round(26.0 + (i % 8) * 0.2, 2) if valid else None,
        "soil_moisture_pct": round(55.0 + (i % 6) * 1.5, 2) if valid else None,
        "soil_ph": round(6.4 + (i % 4) * 0.05, 2) if valid else None,
        "soil_ec_us_cm": 400 + (i % 5) * 12 if valid else None,
        "soil_n_proxy": 30 + (i % 7) if valid else None,
        "soil_p_proxy": 18 + (i % 3) if valid else None,
        "soil_k_proxy": 90 + (i % 9) if valid else None,
    }
    status = {
        "read_ok": valid,
        "sample_valid": valid,
        "crc_ok": valid,
        "frame_ok": valid,
        "error_code": "" if valid else "timeout",
        "raw_error_code": 0 if valid else 4,
        "retry_count": 0 if valid else 3,
        "read_elapsed_ms": 220,
        "timeout_ms": 1000,
        "consecutive_fail_count": 0 if valid else 1,
        "recovered_after_fail": False,
        "partial_values_included": False,
        "soil_temp_valid": valid,
        "soil_temp_source": "sensor",
        "soil_moisture_valid": valid,
        "soil_moisture_source": "sensor",
        "ph_protocol_ok": valid,
        "ph_valid": valid,
        "ph_state": "ok" if valid else "unknown",
        "ec_valid": valid,
        "ec_source": "sensor",
        "ec_measurement_kind": "raw_conductivity",
        "n_proxy_valid": valid,
        "p_proxy_valid": valid,
        "k_proxy_valid": valid,
        "soil_moisture_calibration_status": "uncalibrated",
        "soil_moisture_calibration_profile": "synthetic_profile",
        "soil_moisture_value_semantics": "relative_index",
        "read_map": "synthetic_map_v1",
    }
    return {"sensor_type": "soil_multi_sensor", "values": values, "read_status": status}


def slot(stage: str) -> dict:
    return {"attempted": False, "upload_ok": False, "upload_stage": stage, "http_status": None,
            "tls_ok": None, "upload_latency_ms": None, "payload_bytes": 1500,
            "buffer_reason_code": "", "last_error_code": ""}


def record(i: int) -> tuple[str, str, dict]:
    ts = int((START + timedelta(seconds=i * INTERVAL_SEC)).timestamp())
    date_key = datetime.fromtimestamp(ts, tz=TZ).date().isoformat()
    replayed = i in REPLAYED
    rec = {
        "sensor_record": {"air_sht30_01": sht30(i), "soil_7in1_01": soil(i)},
        "sim_record": {
            "transport": "wifi",
            "network": {"registered": True, "attached": True, "pdp_active": True,
                        "operator_valid": False, "operator": None, "rat": None,
                        "signal_dbm": -60 - (i % 5), "signal_csq": None, "signal_valid": True,
                        "ip_valid": True, "local_ip_valid": True,
                        "local_ip": "192.0.2.10", "local_ip_source": "wifi.localIP"},
            "upload": {"target": "firebase_rtdb", "direct": slot("not_attempted"),
                       "replay": slot("not_replayed")},
        },
        "system_record": {
            "schema_version": 2, "source_level": "raw_telemetry", "synthetic": False,
            "manual_edit": False, "debug_mode": False,
            "identity": {"node_id": NODE_ID, "site_id": SITE_ID, "device_uid": DEVICE_UID,
                         "record_id": str(ts), "record_path": f"/{NODE_ID}/telemetry/{date_key}/{ts}",
                         "seq_no": i + 1, "boot_id": f"boot-{i // 10:03d}"},
            "time": {"ts_sample": ts, "ts_server": ts + (900 if replayed else 2),
                     "timezone": "Asia/Ho_Chi_Minh", "clock_source": "network_time",
                     "time_valid": True, "time_reconstructed": False,
                     "sample_interval_sec": INTERVAL_SEC, "device_uptime_sec": 40 + (i % 10) * 3600},
            "cycle": {"record_type": "telemetry", "wake_reason": "timer",
                      "cycle_type": "periodic", "cycle_duration_ms": 251, "sleep_planned_sec": INTERVAL_SEC},
            "power": {"power_type": "mains", "battery_mv": None, "battery_pct": None,
                      "panel_mv": None, "charge_state": None, "brownout_count": None},
            "device_health": {"heap_free": 210000 - i * 10, "reset_count": None,
                              "reset_reason": "deepsleep", "watchdog_count": None,
                              "storage_free_bytes": None, "buffer_queue_len": None},
            "firmware": {"firmware_version": "0.0.0-synthetic", "build_id": "synthetic",
                         "config_version": "cfg-1", "calibration_version": "cal-1",
                         "running_partition": "app0"},
            "integrity": {"record_hash": None, "payload_crc_ok": None,
                          "duplicate_policy": "deterministic_key", "overwrite_protected": True},
            "sync": {"telemetry_persisted": True, "telemetry_record_path": f"{NODE_ID}/telemetry/{date_key}/{ts}",
                     "buffered": replayed, "replayed": replayed, "latest_updated": True,
                     "buffer_reason_code": "network_down" if replayed else "", "last_error_code": ""},
        },
    }
    return date_key, str(ts), rec


def build() -> dict:
    telemetry: dict = {}
    last = None
    for i in range(SAMPLE_COUNT):
        if i in GAP_INDEXES:
            continue
        date_key, event_key, rec = record(i)
        telemetry.setdefault(date_key, {})[event_key] = rec
        last = rec
    return {
        "info": {
            "identity": {"node_id": NODE_ID, "site_id": SITE_ID, "device_uid": DEVICE_UID},
            "config_current": {"wake_interval_sec": INTERVAL_SEC},
            "network": {"transport": "wifi"},
        },
        "latest": last,
        "telemetry": telemetry,
    }


if __name__ == "__main__":
    target = HERE / "input_export.json"
    target.write_text(json.dumps(build(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {target}")
