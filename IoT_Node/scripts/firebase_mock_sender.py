#!/usr/bin/env python3
"""
Generate mock telemetry records and optionally upload them to Firebase RTDB.

Examples:
  python scripts/firebase_mock_sender.py --dry-run --days 3 --start 2026-03-01
  python scripts/firebase_mock_sender.py --days 7 --start 2026-03-01 --output-file seed_7d.json
  python scripts/firebase_mock_sender.py --days 30 --start 2026-03-01 --upload
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib import error, parse, request
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from backend_env import load_backend_env


def load_runtime_defaults() -> dict[str, str]:
    try:
        _, env_values = load_backend_env()
    except FileNotFoundError:
        return {}

    return env_values


BACKEND_ENV_DEFAULTS = load_runtime_defaults()
DEFAULT_DATABASE_URL = BACKEND_ENV_DEFAULTS.get("DATABASE_URL", "https://agri-fusion-iot-default-rtdb.asia-southeast1.firebasedatabase.app")
DEFAULT_AUTH_TOKEN = BACKEND_ENV_DEFAULTS.get("FIREBASE_LEGACY_TOKEN", "")
DEFAULT_NODE_ROOT = "/Node2"
DEFAULT_NODE_ID = "Node2"
DEFAULT_NODE_NAME = "Vuon sau rieng A"
DEFAULT_SITE_ID = "farm_a_zone_1"
DEFAULT_DEVICE_UID = "esp32s3_node2"
DEFAULT_POWER_TYPE = "solar_battery"
DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"
DEFAULT_FW_VERSION = "ESP32-S3-DEMO1"
DEFAULT_RUNNING_PARTITION = "ota_0"
DEFAULT_SEED = 42
DEFAULT_DAYS = 1
DEFAULT_DEVICE_JITTER_MIN_SEC = 120
DEFAULT_DEVICE_JITTER_MAX_SEC = 420
DEFAULT_SERVER_DELAY_MIN_SEC = 15
DEFAULT_SERVER_DELAY_MAX_SEC = 90
DEFAULT_WAKE_INTERVAL_SEC = 3600
DEFAULT_TELEMETRY_RETENTION_DAYS = 30
DEFAULT_PRIMARY_POLL_AFTER_SEC = DEFAULT_WAKE_INTERVAL_SEC + 300
DEFAULT_RETRY_AFTER_NO_CHANGE_SEC = 300


@dataclass
class AppConfig:
    database_url: str
    auth_token: str
    node_root: str
    node_id: str
    node_name: str
    site_id: str
    device_uid: str
    power_type: str
    timezone_name: str
    firmware_version: str
    running_partition: str
    start: datetime
    days: int
    seed: int
    device_jitter_min_sec: int
    device_jitter_max_sec: int
    server_delay_min_sec: int
    server_delay_max_sec: int
    upload: bool
    update_live: bool
    output_file: Path | None
    print_each: bool


@dataclass
class WriteOp:
    path: str
    data: dict[str, Any]
    category: str
    timestamp_local: str | None = None


@dataclass
class TelemetryEntry:
    local_dt: datetime
    payload: dict[str, Any]
    record: dict[str, Any]
    path: str
    event_id: str


def parse_args() -> AppConfig:
    parser = argparse.ArgumentParser(
        description="Sinh du lieu gia lap NPK + SHT30 va co the day len Firebase RTDB theo tung ngay, moi ngay du 24 moc gio."
    )
    parser.add_argument("--database-url", default=DEFAULT_DATABASE_URL)
    parser.add_argument("--auth-token", default=DEFAULT_AUTH_TOKEN)
    parser.add_argument("--node-root", default=DEFAULT_NODE_ROOT)
    parser.add_argument("--node-id", default=DEFAULT_NODE_ID)
    parser.add_argument("--node-name", default=DEFAULT_NODE_NAME)
    parser.add_argument("--site-id", default=DEFAULT_SITE_ID)
    parser.add_argument("--device-uid", default=DEFAULT_DEVICE_UID)
    parser.add_argument("--power-type", default=DEFAULT_POWER_TYPE)
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument("--firmware-version", default=DEFAULT_FW_VERSION)
    parser.add_argument("--running-partition", default=DEFAULT_RUNNING_PARTITION)
    parser.add_argument(
        "--start",
        help="Ngay bat dau. Chap nhan YYYY-MM-DD hoac ISO datetime. Script se tu dong lay 00:00 local time cua ngay nay.",
    )
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="So ngay can seed. Moi ngay se co du 24 ban ghi.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--device-jitter-min-sec",
        type=int,
        default=DEFAULT_DEVICE_JITTER_MIN_SEC,
        help="Do tre toi thieu cua thoi diem do trong moi khung 1 gio.",
    )
    parser.add_argument(
        "--device-jitter-max-sec",
        type=int,
        default=DEFAULT_DEVICE_JITTER_MAX_SEC,
        help="Do tre toi da cua thoi diem do trong moi khung 1 gio.",
    )
    parser.add_argument(
        "--server-delay-min-sec",
        type=int,
        default=DEFAULT_SERVER_DELAY_MIN_SEC,
        help="Do tre toi thieu giua ts_device va ts_server.",
    )
    parser.add_argument(
        "--server-delay-max-sec",
        type=int,
        default=DEFAULT_SERVER_DELAY_MAX_SEC,
        help="Do tre toi da giua ts_device va ts_server.",
    )
    parser.add_argument("--upload", action="store_true", help="Upload truc tiep len Firebase.")
    parser.add_argument(
        "--no-update-live",
        action="store_true",
        help="Khong update /live sau khi seed xong.",
    )
    parser.add_argument("--output-file", type=Path, help="Ghi toan bo ban ghi ra file JSON.")
    parser.add_argument("--print-each", action="store_true", help="In tung telemetry record ra stdout.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chi sinh du lieu, khong upload. Co the dung cung --output-file.",
    )
    args = parser.parse_args()

    if args.days <= 0:
        parser.error("--days phai > 0")
    if args.device_jitter_min_sec < 0 or args.device_jitter_max_sec < 0:
        parser.error("device jitter khong duoc am")
    if args.server_delay_min_sec < 0 or args.server_delay_max_sec < 0:
        parser.error("server delay khong duoc am")
    if args.device_jitter_min_sec > args.device_jitter_max_sec:
        parser.error("--device-jitter-min-sec phai <= --device-jitter-max-sec")
    if args.server_delay_min_sec > args.server_delay_max_sec:
        parser.error("--server-delay-min-sec phai <= --server-delay-max-sec")
    if args.device_jitter_max_sec >= 3600:
        parser.error("device jitter phai < 3600 giay de khong tran sang khung gio ke")

    start = parse_start_date(args.start, args.timezone)
    upload = bool(args.upload and not args.dry_run)

    if not args.database_url:
        parser.error("--database-url dang trong. Them DATABASE_URL vao Backend/Services/.env hoac truyen tham so.")
    if upload and not args.auth_token:
        parser.error("--auth-token dang trong. Them FIREBASE_LEGACY_TOKEN vao Backend/Services/.env hoac truyen tham so.")

    return AppConfig(
        database_url=args.database_url,
        auth_token=args.auth_token,
        node_root=args.node_root,
        node_id=args.node_id,
        node_name=args.node_name,
        site_id=args.site_id,
        device_uid=args.device_uid,
        power_type=args.power_type,
        timezone_name=args.timezone,
        firmware_version=args.firmware_version,
        running_partition=args.running_partition,
        start=start,
        days=args.days,
        seed=args.seed,
        device_jitter_min_sec=args.device_jitter_min_sec,
        device_jitter_max_sec=args.device_jitter_max_sec,
        server_delay_min_sec=args.server_delay_min_sec,
        server_delay_max_sec=args.server_delay_max_sec,
        upload=upload,
        update_live=not args.no_update_live,
        output_file=args.output_file,
        print_each=args.print_each,
    )


def parse_start_date(raw: str | None, timezone_name: str) -> datetime:
    tz = ZoneInfo(timezone_name)
    if not raw:
        now = datetime.now(tz=tz)
        return now.replace(hour=0, minute=0, second=0, microsecond=0)

    text = raw.strip()
    if len(text) == 10:
        dt = datetime.fromisoformat(text)
        return dt.replace(tzinfo=tz)

    normalized = text.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    else:
        dt = dt.astimezone(tz)
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def calc_day_fraction(local_dt: datetime) -> float:
    return (local_dt.hour * 3600 + local_dt.minute * 60 + local_dt.second) / 86400.0


def clock_hour(local_dt: datetime) -> float:
    return local_dt.hour + local_dt.minute / 60.0 + local_dt.second / 3600.0


def gaussian_peak(x: float, center: float, sigma: float) -> float:
    return math.exp(-((x - center) ** 2) / (2.0 * sigma * sigma))


def smooth_cycle(position: float, period: float, phase: float = 0.0) -> float:
    return math.sin((position / period + phase) * 2.0 * math.pi)


def irrigation_effect_air(local_dt: datetime) -> float:
    hour = clock_hour(local_dt)
    morning = gaussian_peak(hour, 8.5, 0.65)
    afternoon = gaussian_peak(hour, 16.5, 0.75)
    return clamp(morning + afternoon, 0.0, 1.0)


def irrigation_effect_soil(local_dt: datetime) -> float:
    hour = clock_hour(local_dt)
    # Soil reacts more directly and stays wet a bit longer than ambient air.
    morning = gaussian_peak(hour, 8.7, 0.95)
    afternoon = gaussian_peak(hour, 16.7, 1.0)
    return clamp(morning + afternoon, 0.0, 1.0)



def simulated_battery_voltage(local_dt: datetime, day_profile: dict[str, float], rng: random.Random) -> float:
    hour = clock_hour(local_dt)
    solar_support = max(0.0, math.sin(math.pi * (hour - 6.0) / 12.0)) if 6.0 <= hour <= 18.0 else 0.0
    solar_drag = max(0.0, day_profile["cloud_energy_drag"])
    regime_drag = max(0.0, day_profile["system_stress"])
    evening_penalty = 0.08 if (hour >= 19.0 or hour < 5.0) else 0.0
    base = (
        12.16
        + 0.36 * solar_support
        - evening_penalty
        - 0.10 * solar_drag
        - 0.07 * regime_drag
        + 0.03 * day_profile["recovery_bias"]
        + rng.uniform(-0.03, 0.03)
    )
    return round(clamp(base, 11.92, 12.62), 2)


def simulated_heap_free(local_dt: datetime, rng: random.Random) -> int:
    hour = clock_hour(local_dt)
    wake_pressure = 2200.0 * math.sin(2.0 * math.pi * (hour / 24.0))
    value = 243000 + wake_pressure + rng.uniform(-3500, 0)
    return int(clamp(value, 236000, 248500))


def simulated_quality(
    base: float,
    irrigation_factor: float,
    day_profile: dict[str, float],
    rng: random.Random,
    low: float,
    high: float,
    penalty: float = 0.0,
) -> float:
    transient_dip = rng.uniform(0.02, 0.08) if rng.random() < (0.08 + max(0.0, day_profile["system_stress"]) * 0.08) else 0.0
    regime_bias = 0.035 * day_profile["recovery_bias"] - 0.05 * max(0.0, day_profile["system_stress"])
    value = base - 0.05 * irrigation_factor + regime_bias - penalty - transient_dip + rng.uniform(-0.05, 0.035)
    return round(clamp(value, low, high), 3)


def build_day_profile(seed: int, start: datetime, local_dt: datetime) -> dict[str, float]:
    day_index = (local_dt.date() - start.date()).days
    week_cycle = smooth_cycle(float(day_index), 7.0, 0.08)
    biweekly_cycle = smooth_cycle(float(day_index), 14.0, 0.27)
    monthly_cycle = smooth_cycle(float(day_index), 29.0, 0.41)
    block_index = day_index // 5
    day_rng = random.Random(seed * 1009 + local_dt.date().toordinal() * 37)
    block_rng = random.Random(seed * 2029 + block_index * 97 + start.date().toordinal() * 13)
    weather_regime = block_rng.uniform(-1.0, 1.0)
    nutrient_regime = block_rng.uniform(-1.0, 1.0)
    recovery_bias = block_rng.uniform(-1.0, 1.0)
    system_stress = block_rng.uniform(-0.35, 1.0)
    return {
        "day_index": float(day_index),
        "week_cycle": week_cycle,
        "biweekly_cycle": biweekly_cycle,
        "monthly_cycle": monthly_cycle,
        "weather_regime": weather_regime,
        "nutrient_regime": nutrient_regime,
        "recovery_bias": recovery_bias,
        "system_stress": system_stress,
        "cloud_energy_drag": 0.55 * max(0.0, weather_regime) + 0.35 * max(0.0, monthly_cycle),
        "air_temp_offset": day_rng.uniform(-0.7, 0.7) + 0.85 * week_cycle + 1.15 * monthly_cycle + 0.65 * weather_regime,
        "air_temp_amp": day_rng.uniform(0.88, 1.14) + 0.06 * week_cycle,
        "air_hum_offset": day_rng.uniform(-4.5, 4.5) - 3.2 * week_cycle + 4.4 * max(0.0, weather_regime) + 1.4 * biweekly_cycle,
        "air_hum_amp": day_rng.uniform(0.86, 1.16) - 0.05 * weather_regime,
        "soil_temp_offset": day_rng.uniform(-0.45, 0.45) + 0.55 * week_cycle + 0.45 * monthly_cycle,
        "soil_temp_amp": day_rng.uniform(0.90, 1.08) + 0.04 * monthly_cycle,
        "soil_hum_offset": day_rng.uniform(-2.6, 2.6) + 2.8 * max(0.0, weather_regime) - 2.2 * max(0.0, week_cycle),
        "soil_hourly_drydown": day_rng.uniform(0.05, 0.18) + 0.02 * max(0.0, week_cycle),
        "soil_daily_drydown": day_rng.uniform(0.55, 1.95) + 0.55 * max(0.0, -recovery_bias),
        "ec_offset": day_rng.uniform(-24.0, 24.0) - 28.0 * max(0.0, weather_regime) + 18.0 * max(0.0, -recovery_bias),
        "ph_offset": day_rng.uniform(-0.03, 0.03) + 0.012 * nutrient_regime,
        "n_offset": day_rng.uniform(-3.8, 3.8) + 4.2 * nutrient_regime + 1.6 * biweekly_cycle,
        "p_offset": day_rng.uniform(-1.6, 1.6) + 1.9 * nutrient_regime + 0.7 * monthly_cycle,
        "k_offset": day_rng.uniform(-3.0, 3.0) + 3.2 * nutrient_regime - 1.4 * week_cycle,
    }


def telemetry_key(ts_server_sec: int, seq_no: int) -> str:
    return f"{ts_server_sec}_{seq_no % 1000:03d}"


def status_event_key(ts_server_sec: int, seq_no: int) -> str:
    return f"{ts_server_sec}_evt{seq_no % 1000:03d}"


def local_date_key(local_dt: datetime) -> str:
    return local_dt.strftime("%Y-%m-%d")


def stable_sha256(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_schedule(cfg: AppConfig, rng: random.Random) -> list[datetime]:
    out: list[datetime] = []
    for day_offset in range(cfg.days):
        day_start = cfg.start + timedelta(days=day_offset)
        for hour in range(24):
            base_dt = day_start + timedelta(hours=hour)
            jitter_sec = rng.randint(cfg.device_jitter_min_sec, cfg.device_jitter_max_sec)
            out.append(base_dt + timedelta(seconds=jitter_sec))
    return out


def build_packet(cfg: AppConfig, local_dt: datetime, rng: random.Random) -> dict[str, Any]:
    day_phase = calc_day_fraction(local_dt)
    hour = clock_hour(local_dt)
    day_profile = build_day_profile(cfg.seed, cfg.start, local_dt)
    air_water_factor = irrigation_effect_air(local_dt)
    soil_water_factor = irrigation_effect_soil(local_dt)

    temp_air_base = (
        27.1
        + day_profile["air_temp_offset"]
        + 2.4 * day_profile["air_temp_amp"] * math.sin((day_phase - 0.22) * 2 * math.pi)
        + 0.45 * day_profile["biweekly_cycle"]
        + rng.uniform(-0.32, 0.32)
    )
    hum_air_base = (
        71.0
        + day_profile["air_hum_offset"]
        - 8.1 * day_profile["air_hum_amp"] * math.sin((day_phase - 0.18) * 2 * math.pi)
        - 1.1 * day_profile["monthly_cycle"]
        + rng.uniform(-1.2, 1.2)
    )
    soil_temp_base = (
        26.0
        + day_profile["soil_temp_offset"]
        + 1.45 * day_profile["soil_temp_amp"] * math.sin((day_phase - 0.28) * 2 * math.pi)
        + 0.35 * day_profile["week_cycle"]
        + rng.uniform(-0.25, 0.25)
    )
    drydown_phase = max(0.0, float(int(day_profile["day_index"]) % 6) - 1.0)
    soil_drydown = drydown_phase * day_profile["soil_daily_drydown"] + hour * day_profile["soil_hourly_drydown"]
    soil_hum_base = (
        66.0
        + day_profile["soil_hum_offset"]
        - soil_drydown
        + 2.2 * day_profile["recovery_bias"]
        + 1.7 * max(0.0, day_profile["weather_regime"])
        + 0.65 * math.cos((day_phase - 0.10) * 2 * math.pi)
        + rng.uniform(-0.5, 0.5)
    )
    ph_base = (
        6.02
        + day_profile["ph_offset"]
        + 0.018 * math.sin((day_phase + 0.10) * 2 * math.pi)
        - 0.01 * day_profile["weather_regime"]
        + rng.uniform(-0.008, 0.008)
    )
    nutrient_wave = 0.7 * day_profile["week_cycle"] + 1.05 * day_profile["biweekly_cycle"] + 1.2 * day_profile["monthly_cycle"]
    n_base = 100.0 + day_profile["n_offset"] + 3.6 * nutrient_wave - 1.1 * max(0.0, day_profile["weather_regime"]) + rng.uniform(-1.4, 1.4)
    p_base = 37.5 + day_profile["p_offset"] + 1.8 * nutrient_wave - 0.5 * max(0.0, day_profile["weather_regime"]) + rng.uniform(-0.7, 0.7)
    k_base = 78.5 + day_profile["k_offset"] + 2.8 * nutrient_wave - 0.7 * max(0.0, day_profile["weather_regime"]) + rng.uniform(-1.2, 1.2)
    ec_base = 845.0 + day_profile["ec_offset"] + 4.8 * (64.0 - soil_hum_base) + 16.0 * max(0.0, -day_profile["nutrient_regime"]) + rng.uniform(-12.0, 12.0)

    temp_air = clamp(temp_air_base - 2.0 * air_water_factor, 23.0, 31.5)
    hum_air = clamp(hum_air_base + 18.5 * air_water_factor, 52.0, 96.0)
    soil_temp = clamp(soil_temp_base - 2.9 * soil_water_factor, 22.5, 31.0)
    soil_hum = clamp(soil_hum_base + 14.0 * soil_water_factor, 46.0, 84.0)
    ph = clamp(ph_base - 0.018 * soil_water_factor, 5.4, 6.7)
    ec = int(clamp(ec_base - 48.0 * soil_water_factor, 620, 1160))
    n_value = int(clamp(n_base - 1.5 * soil_water_factor, 82, 128))
    p_value = int(clamp(p_base - 0.9 * soil_water_factor, 26, 52))
    k_value = int(clamp(k_base - 1.3 * soil_water_factor, 62, 98))

    rssi = int(clamp(-68 + 6 * math.sin(day_phase * 2 * math.pi) - 4.0 * max(0.0, day_profile["system_stress"]) + rng.uniform(-4, 4), -98, -44))
    ts_device_ms = int(local_dt.timestamp()) * 1000
    npk_retry_roll = rng.random()
    sht_retry_roll = rng.random()
    npk_retry_count = 2 if npk_retry_roll < (0.015 + 0.03 * max(0.0, day_profile["system_stress"])) else (1 if npk_retry_roll < (0.08 + 0.08 * max(0.0, day_profile["system_stress"])) else 0)
    sht_retry_count = 2 if sht_retry_roll < (0.01 + 0.02 * max(0.0, day_profile["system_stress"])) else (1 if sht_retry_roll < (0.06 + 0.06 * max(0.0, day_profile["system_stress"])) else 0)
    npk_sample_valid = rng.random() >= (0.03 + 0.05 * max(0.0, day_profile["system_stress"]))
    sht_sample_valid = rng.random() >= (0.02 + 0.04 * max(0.0, day_profile["system_stress"]))
    npk_duration_ms = int(
        clamp(150 + 28.0 * soil_water_factor + 62 * npk_retry_count + (35 if not npk_sample_valid else 0) + rng.uniform(-24, 30), 90, 380)
    )
    sht_duration_ms = int(
        clamp(44 + 18 * sht_retry_count + (18 if not sht_sample_valid else 0) + rng.uniform(-10, 16), 20, 160)
    )
    npk_error_code = "ok" if npk_sample_valid else "weak_signal"
    sht_error = "ok" if sht_sample_valid else "crc_soft_warning"

    npk_data = {
        "sensor_type": "npk7in1",
        "sensor_id": "npk_7in1_1",
        "read_ok": True,
        "error_code": npk_error_code,
        "error_code_raw": 0 if npk_sample_valid else 12,
        "retry_count": npk_retry_count,
        "timeout_ms": 2000,
        "read_duration_ms": npk_duration_ms,
        "crc_ok": True,
        "frame_ok": True,
        "sample_interval_ms": DEFAULT_WAKE_INTERVAL_SEC * 1000,
        "consecutive_fail_count": 0 if npk_sample_valid else 1,
        "recovered_after_fail": False,
        "fail_streak_before_recover": 0,
        "sensor_alarm": False,
        "npk_values_valid": npk_sample_valid,
        "npk_signal_present": True,
        "temp": round(soil_temp, 2),
        "hum": round(soil_hum, 2),
        "ph": round(ph, 2),
        "ec": ec,
        "N": n_value,
        "P": p_value,
        "K": k_value,
        "edge_system": "soil_npk_edge",
        "edge_system_id": "edge_npk_01",
        "edge_stream": "npk",
    }

    sht30_data = {
        "sensor_type": "sht30_air",
        "sensor_id": "sht30_1",
        "edge_system": "air_climate_edge",
        "edge_system_id": "edge_sht30_01",
        "edge_stream": "sht30",
        "sht_addr": "0x44",
        "sht_sda": 8,
        "sht_scl": 9,
        "sht_retry_limit": 5,
        "sht_retry_delay_ms": 120,
        "sht_max_wait_ms": 1200,
        "sht_read_ok": True,
        "sht_sample_valid": sht_sample_valid,
        "sht_temp_c": round(temp_air, 2),
        "sht_hum_pct": round(hum_air, 2),
        "sht_error": sht_error,
        "sht_retry_count": sht_retry_count,
        "sht_read_elapsed_ms": sht_duration_ms,
        "sht_invalid_streak": 0 if sht_sample_valid else 1,
    }

    system_data = {
        "edge_system_primary": "soil_npk_edge",
        "edge_system_secondary": "air_climate_edge",
        "edge_system_id_primary": "edge_npk_01",
        "edge_system_id_secondary": "edge_sht30_01",
        "wifi_status": 0,
        "wifi_connected": False,
        "rssi": rssi,
        "transport": "sim",
        "npk_alarm": False,
        "sht_ready": True,
        "firmware_version": cfg.firmware_version,
        "running_partition": cfg.running_partition,
        "ts_device_ms": ts_device_ms,
    }

    return {
        "schema_version": 3,
        "node_key": cfg.node_id,
        "node_id": cfg.node_id,
        "node_name": cfg.node_name,
        "packet": {
            "npk_data": npk_data,
            "sht30_data": sht30_data,
            "system_data": system_data,
        },
    }


def build_record(cfg: AppConfig, payload: dict[str, Any], local_dt: datetime, seq_no: int, rng: random.Random) -> tuple[str, str, dict[str, Any]]:
    ts_device_sec = int(local_dt.timestamp())
    server_delay_sec = rng.randint(cfg.server_delay_min_sec, cfg.server_delay_max_sec)
    ts_server_sec = ts_device_sec + server_delay_sec
    event_id = telemetry_key(ts_server_sec, seq_no)
    date_key = local_date_key(local_dt)

    npk_src = payload["packet"]["npk_data"]
    sht_src = payload["packet"]["sht30_data"]
    rssi = payload["packet"]["system_data"]["rssi"]
    day_profile = build_day_profile(cfg.seed, cfg.start, local_dt)
    air_water_factor = irrigation_effect_air(local_dt)
    soil_water_factor = irrigation_effect_soil(local_dt)
    battery_v = simulated_battery_voltage(local_dt, day_profile, rng)
    heap_free = simulated_heap_free(local_dt, rng)
    npk_sample_valid = bool(npk_src["npk_values_valid"])
    sht_sample_valid = bool(sht_src["sht_sample_valid"])
    npk_penalty = 0.035 * npk_src["retry_count"] + (0.06 if not npk_sample_valid else 0.0)
    sht_penalty = 0.03 * sht_src["sht_retry_count"] + (0.05 if not sht_sample_valid else 0.0)
    npk_quality = simulated_quality(0.915, soil_water_factor, day_profile, rng, 0.72, 0.96, penalty=npk_penalty)
    sht_quality = simulated_quality(0.955, air_water_factor, day_profile, rng, 0.82, 0.988, penalty=sht_penalty)
    npk_status = "ok" if npk_sample_valid else "degraded"
    sht_status = "ok" if sht_sample_valid else "degraded"

    record = {
        "schema_version": 1,
        "ts_device": ts_device_sec,
        "ts_server": ts_server_sec,
        "seq_no": seq_no,
        "event_meta": {
            "cycle_type": "periodic",
            "wake_reason": "timer",
            "duration_ms": max(npk_src["read_duration_ms"], sht_src["sht_read_elapsed_ms"]),
        },
        "packet": payload["packet"],
        "sensors": {
            "npk": {
                "read_ok": bool(npk_src["read_ok"]),
                "sample_valid": npk_sample_valid,
                "status": npk_status,
                "quality": npk_quality,
                "ts_sample": ts_device_sec,
                "error_code": "" if npk_sample_valid else npk_src["error_code"],
            },
            "sht30": {
                "read_ok": bool(sht_src["sht_read_ok"]),
                "sample_valid": sht_sample_valid,
                "status": sht_status,
                "quality": sht_quality,
                "ts_sample": ts_device_sec,
                "error_code": "" if sht_sample_valid else sht_src["sht_error"],
            },
        },
        "modules": {
            "sim": {
                "operator": "Viettel",
                "signal_dbm": rssi,
                "network_status": "connected",
                "ts_sample": ts_device_sec,
            },
            "gps": {
                "enabled": False,
                "status": "inactive",
                "ts_sample": 0,
            },
        },
        "health": {
            "overall": {
                "battery_v": battery_v,
                "heap_free": heap_free,
                "rssi": rssi,
                "online": True,
            },
            "npk": {
                "status": npk_status,
                "quality": npk_quality,
                "error_code": "" if npk_sample_valid else npk_src["error_code"],
            },
            "sht30": {
                "status": sht_status,
                "quality": sht_quality,
                "error_code": "" if sht_sample_valid else sht_src["sht_error"],
            },
            "sim": {
                "status": "connected",
                "error_code": "",
            },
        },
        "fallback_used": False,
        "was_buffered": False,
        "replayed": False,
        "_meta_seed": {
            "node_id": cfg.node_id,
            "node_name": cfg.node_name,
            "site_id": cfg.site_id,
            "device_uid": cfg.device_uid,
            "server_delay_sec": server_delay_sec,
            "day_regime": round(day_profile["weather_regime"], 4),
            "system_stress": round(day_profile["system_stress"], 4),
        },
    }

    return date_key, event_id, record


def build_node_info_doc(cfg: AppConfig, last_ts_server_sec: int, last_rssi: int) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "identity": {
            "node_id": cfg.node_id,
            "device_uid": cfg.device_uid,
            "site_id": cfg.site_id,
        },
        "hardware": {
            "board": "ESP32-S3",
            "power_type": cfg.power_type,
            "reset_count": 0,
        },
        "firmware": {
            "version": cfg.firmware_version,
            "build_id": "ESP32-S3-DEMO1",
            "last_update_ts": last_ts_server_sec,
        },
        "config": {
            "sampling_mode": "periodic",
            "wake_interval_sec": DEFAULT_WAKE_INTERVAL_SEC,
            "timezone": cfg.timezone_name,
            "telemetry_retention_days": DEFAULT_TELEMETRY_RETENTION_DAYS,
        },
        "network": {
            "transport": "sim",
            "ip": "",
            "mac": "",
            "last_rssi": last_rssi,
        },
    }


def build_health_overall_doc(last_entry: TelemetryEntry) -> dict[str, Any]:
    overall = dict(last_entry.record["health"]["overall"])
    overall["heartbeat_age_sec"] = 0
    overall["system_state"] = "online"
    overall["state_detail"] = "rtdb write ok"
    overall["ts_device"] = last_entry.record["ts_device"]
    overall["last_sync_ts"] = last_entry.record["ts_server"]
    return overall



def build_telemetry_debug_doc(last_entry: TelemetryEntry) -> dict[str, Any]:
    return {
        "ok": True,
        "ref_or_path": last_entry.event_id,
        "detail": "ok",
        "ts_device": last_entry.record["ts_device"],
        "ts_server": last_entry.record["ts_server"],
    }


def build_telemetry_channel_doc(last_entry: TelemetryEntry, total_records: int) -> dict[str, Any]:
    return {
        "last_stage": "direct_upload",
        "last_ok": True,
        "fallback_active": False,
        "tls_error": False,
        "last_ref_or_path": last_entry.event_id,
        "last_detail": "ok",
        "key_mode": "deterministic_only",
        "counter_ok": total_records,
        "counter_fail": 0,
        "counter_fallback": 0,
        "counter_tls_error": 0,
        "ts_device": last_entry.record["ts_device"],
        "ts_server": last_entry.record["ts_server"],
    }


def build_latest_current_doc(entries: list[TelemetryEntry]) -> dict[str, Any]:
    return entries[-1].record


def build_latest_meta_doc(cfg: AppConfig, entries: list[TelemetryEntry]) -> dict[str, Any]:
    last_entry = entries[-1]
    previous_entry = entries[-2] if len(entries) > 1 else None
    latest_date_key = local_date_key(last_entry.local_dt)
    latest_record = last_entry.record
    jitter_span_sec = cfg.device_jitter_max_sec - cfg.device_jitter_min_sec
    delay_span_sec = cfg.server_delay_max_sec - cfg.server_delay_min_sec
    expected_device_min_sec = max(1, DEFAULT_WAKE_INTERVAL_SEC - jitter_span_sec)
    expected_device_max_sec = DEFAULT_WAKE_INTERVAL_SEC + jitter_span_sec
    expected_server_min_sec = max(1, expected_device_min_sec - delay_span_sec)
    expected_server_max_sec = expected_device_max_sec + delay_span_sec

    previous_event_key = None
    previous_date_key = None
    previous_path = None
    previous_ts_device = None
    previous_ts_server = None
    delta_device_sec = None
    delta_server_sec = None
    device_delta_ok = None
    server_delta_ok = None

    if previous_entry is not None:
        previous_date_key = local_date_key(previous_entry.local_dt)
        previous_event_key = previous_entry.event_id
        previous_path = previous_entry.path.strip("/")
        previous_ts_device = previous_entry.record["ts_device"]
        previous_ts_server = previous_entry.record["ts_server"]
        delta_device_sec = latest_record["ts_device"] - previous_ts_device
        delta_server_sec = latest_record["ts_server"] - previous_ts_server
        device_delta_ok = expected_device_min_sec <= delta_device_sec <= expected_device_max_sec
        server_delta_ok = expected_server_min_sec <= delta_server_sec <= expected_server_max_sec

    return {
        "schema_version": 1,
        "node_id": cfg.node_id,
        "latest_event_key": last_entry.event_id,
        "latest_date_key": latest_date_key,
        "latest_path": last_entry.path.strip("/"),
        "latest_local_iso": last_entry.local_dt.isoformat(),
        "ts_device": latest_record["ts_device"],
        "ts_server": latest_record["ts_server"],
        "record_sha256": stable_sha256(latest_record),
        "previous_event_key": previous_event_key,
        "previous_date_key": previous_date_key,
        "previous_path": previous_path,
        "previous_ts_device": previous_ts_device,
        "previous_ts_server": previous_ts_server,
        "delta_device_sec": delta_device_sec,
        "delta_server_sec": delta_server_sec,
        "expected_device_min_sec": expected_device_min_sec,
        "expected_device_max_sec": expected_device_max_sec,
        "expected_server_min_sec": expected_server_min_sec,
        "expected_server_max_sec": expected_server_max_sec,
        "device_in_expected_range": device_delta_ok,
        "server_in_expected_range": server_delta_ok,
        "primary_poll_after_sec": DEFAULT_PRIMARY_POLL_AFTER_SEC,
        "retry_after_no_change_sec": DEFAULT_RETRY_AFTER_NO_CHANGE_SEC,
        "updated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


def build_live_doc(last_entry: TelemetryEntry, telemetry_debug: dict[str, Any], telemetry_channel: dict[str, Any]) -> dict[str, Any]:
    payload = last_entry.payload
    npk_src = payload["packet"]["npk_data"]
    sht_src = payload["packet"]["sht30_data"]
    rssi = payload["packet"]["system_data"]["rssi"]
    ts_device_sec = last_entry.record["ts_device"]
    ts_server_sec = last_entry.record["ts_server"]
    npk_sensor = last_entry.record["sensors"]["npk"]
    sht_sensor = last_entry.record["sensors"]["sht30"]

    return {
        "schema_version": 1,
        "meta": {
            "last_event_id": last_entry.event_id,
            "last_seen_ts": ts_device_sec,
            "uptime_sec": 0,
            "boot_reason": "timer",
            "last_sync_ts": ts_server_sec,
            "telemetry_debug": telemetry_debug,
            "telemetry_channel": telemetry_channel,
        },
        "sensors": {
            "npk": {
                "n": npk_src["N"],
                "p": npk_src["P"],
                "k": npk_src["K"],
                "ec": npk_src["ec"],
                "ph": npk_src["ph"],
                "temperature_c": npk_src["temp"],
                "humidity_percent": npk_src["hum"],
                "ts_sample": ts_device_sec,
                "read_ok": bool(npk_src["read_ok"]),
                "sample_valid": bool(npk_src["npk_values_valid"]),
                "status": npk_sensor["status"],
                "quality": npk_sensor["quality"],
                "error_code": npk_sensor["error_code"],
            },
            "sht30": {
                "temperature_c": sht_src["sht_temp_c"],
                "humidity_percent": sht_src["sht_hum_pct"],
                "ts_sample": ts_device_sec,
                "read_ok": bool(sht_src["sht_read_ok"]),
                "sample_valid": bool(sht_src["sht_sample_valid"]),
                "retry_count": sht_src["sht_retry_count"],
                "read_elapsed_ms": sht_src["sht_read_elapsed_ms"],
                "invalid_streak": sht_src["sht_invalid_streak"],
                "status": sht_sensor["status"],
                "quality": sht_sensor["quality"],
                "error_code": sht_sensor["error_code"],
            },
        },
        "modules": {
            "sim": {
                "operator": "Viettel",
                "signal_dbm": rssi,
                "network_status": "connected",
                "ts_sample": ts_device_sec,
            },
            "gps": {
                "enabled": False,
                "status": "inactive",
                "ts_sample": 0,
            },
        },
        "health": {
            "overall": build_health_overall_doc(last_entry),
            "sensors": {
                "npk": {
                    "read_ok": bool(npk_src["read_ok"]),
                    "sample_valid": bool(npk_src["npk_values_valid"]),
                    "status": npk_sensor["status"],
                    "last_success_ts": ts_device_sec if npk_sensor["sample_valid"] else 0,
                },
                "sht30": {
                    "read_ok": bool(sht_src["sht_read_ok"]),
                    "sample_valid": bool(sht_src["sht_sample_valid"]),
                    "status": sht_sensor["status"],
                    "last_success_ts": ts_device_sec if sht_sensor["sample_valid"] else 0,
                },
            },
            "modules": {
                "sim": {
                    "status": "connected",
                    "last_success_ts": ts_device_sec,
                },
                "gps": {
                    "status": "inactive",
                    "last_success_ts": 0,
                },
            },
        },
    }


def build_status_event(from_state: str, to_state: str, reason: str, ts_server_sec: int, severity: str) -> dict[str, Any]:
    return {
        "component": "system",
        "from": from_state,
        "to": to_state,
        "reason": reason,
        "ts": ts_server_sec,
        "severity": severity,
        "ts_server_ms": ts_server_sec * 1000,
    }


def build_ota_docs(cfg: AppConfig, last_entry: TelemetryEntry) -> list[WriteOp]:
    uptime_ms = last_entry.record["ts_device"] * 1000
    status_doc = {
        "stage": "status",
        "status": "idle",
        "detail": "ESP32-S3-DEMO1",
        "request_id": "",
        "firmware_version": cfg.firmware_version,
        "running_partition": cfg.running_partition,
        "uptime_ms": uptime_ms,
    }
    history_doc = {
        "stage": "status",
        "status": "idle",
        "detail": "ESP32-S3-DEMO1",
        "target_version": cfg.firmware_version,
        "request_id": "",
        "firmware_version": cfg.firmware_version,
        "running_partition": cfg.running_partition,
        "uptime_ms": uptime_ms,
    }
    command_doc = {
        "enabled": False,
        "request_id": "",
        "version": "",
        "url": "",
        "md5": "",
        "force": False,
    }
    history_key = f"seed_{last_entry.record['ts_server']}"
    return [
        WriteOp(path="/ota/status", data=status_doc, category="ota_status"),
        WriteOp(path=f"/ota/history/{history_key}", data=history_doc, category="ota_history"),
        WriteOp(path="/ota/command", data=command_doc, category="ota_command"),
    ]


def build_aux_writes(cfg: AppConfig, entries: list[TelemetryEntry]) -> list[WriteOp]:
    node_root = cfg.node_root.rstrip("/")
    last_entry = entries[-1]
    info_doc = build_node_info_doc(cfg, last_entry.record["ts_server"], last_entry.payload["packet"]["system_data"]["rssi"])
    telemetry_debug = build_telemetry_debug_doc(last_entry)
    telemetry_channel = build_telemetry_channel_doc(last_entry, len(entries))
    live_doc = build_live_doc(last_entry, telemetry_debug, telemetry_channel)
    health_overall = build_health_overall_doc(last_entry)
    latest_meta_doc = build_latest_meta_doc(cfg, entries)
    latest_current_doc = build_latest_current_doc(entries)

    writes: list[WriteOp] = [
        WriteOp(path=f"{node_root}/info", data=info_doc, category="info"),
        WriteOp(path=f"{node_root}/latest/meta", data=latest_meta_doc, category="latest_meta"),
        WriteOp(path=f"{node_root}/latest/current", data=latest_current_doc, category="latest_current"),
        WriteOp(path=f"{node_root}/live", data=live_doc, category="live"),
        WriteOp(path=f"{node_root}/live/health/overall", data=health_overall, category="live_health_overall"),
        WriteOp(path=f"{node_root}/live/meta/telemetry_debug", data=telemetry_debug, category="telemetry_debug"),
        WriteOp(path=f"{node_root}/live/meta/telemetry_channel", data=telemetry_channel, category="telemetry_channel"),
    ]

    first_entry_by_day: dict[str, TelemetryEntry] = {}
    for entry in entries:
        day_key = local_date_key(entry.local_dt)
        first_entry_by_day.setdefault(day_key, entry)

    status_seq = 1
    previous_state = "unknown"
    for day in sorted(first_entry_by_day.keys()):
        entry = first_entry_by_day[day]
        boot_ts = entry.record["ts_server"]
        online_ts = boot_ts + 1
        boot_key = status_event_key(boot_ts, status_seq)
        writes.append(
            WriteOp(
                path=f"{node_root}/status_events/{boot_key}",
                data=build_status_event(previous_state, "boot", "network task started", boot_ts, "info"),
                category="status_event",
            )
        )
        status_seq += 1
        online_key = status_event_key(online_ts, status_seq)
        writes.append(
            WriteOp(
                path=f"{node_root}/status_events/{online_key}",
                data=build_status_event("boot", "online", "rtdb write ok", online_ts, "info"),
                category="status_event",
            )
        )
        status_seq += 1
        previous_state = "online"

    writes.extend(build_ota_docs(cfg, last_entry))
    return writes


def make_rtdb_url(base_url: str, path: str, auth_token: str) -> str:
    clean_base = base_url.rstrip("/")
    clean_path = path.strip("/")
    query = parse.urlencode({"auth": auth_token}) if auth_token else ""
    suffix = f"?{query}" if query else ""
    return f"{clean_base}/{clean_path}.json{suffix}"


def put_json(base_url: str, auth_token: str, path: str, data: dict[str, Any]) -> None:
    body = json.dumps(data, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    url = make_rtdb_url(base_url, path, auth_token)
    req = request.Request(url, data=body, method="PUT", headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=20) as resp:
        if resp.status >= 300:
            raise RuntimeError(f"Firebase PUT failed: {resp.status} {resp.read().decode('utf-8', errors='replace')}")


def write_output_file(output_file: Path, telemetry_writes: list[WriteOp], aux_writes: list[WriteOp]) -> None:
    serializable = {
        "telemetry_writes": [op.__dict__ for op in telemetry_writes],
        "aux_writes": [op.__dict__ for op in aux_writes],
    }
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    cfg = parse_args()
    rng = random.Random(cfg.seed)
    schedule = build_schedule(cfg, rng)

    telemetry_entries: list[TelemetryEntry] = []
    telemetry_writes: list[WriteOp] = []
    per_day_counts: dict[str, int] = {}

    for idx, local_dt in enumerate(schedule, start=1):
        payload = build_packet(cfg, local_dt, rng)
        date_key, event_id, record = build_record(cfg, payload, local_dt, idx, rng)
        path = f"{cfg.node_root.rstrip('/')}/telemetry/{date_key}/{event_id}"
        entry = TelemetryEntry(local_dt=local_dt, payload=payload, record=record, path=path, event_id=event_id)
        telemetry_entries.append(entry)
        telemetry_writes.append(
            WriteOp(path=path, data=record, category="telemetry", timestamp_local=local_dt.isoformat())
        )
        day_key = local_date_key(local_dt)
        per_day_counts[day_key] = per_day_counts.get(day_key, 0) + 1

        if cfg.print_each:
            print(
                json.dumps(
                    {
                        "path": path,
                        "timestamp_local": local_dt.isoformat(),
                        "timestamp_utc": local_dt.astimezone(timezone.utc).isoformat(),
                        "record": record,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )

    aux_writes = build_aux_writes(cfg, telemetry_entries)

    if cfg.upload:
        for op in telemetry_writes:
            put_json(cfg.database_url, cfg.auth_token, op.path, op.data)
            print(f"uploaded {op.path}")
        for op in aux_writes:
            put_json(cfg.database_url, cfg.auth_token, op.path, op.data)
            print(f"uploaded {op.path}")

    if cfg.output_file:
        write_output_file(cfg.output_file, telemetry_writes, aux_writes)
        print(f"saved {len(telemetry_writes)} telemetry writes and {len(aux_writes)} aux writes to {cfg.output_file}")

    print(f"generated {len(telemetry_writes)} telemetry records across {cfg.days} day(s)")
    print(f"generated {len(aux_writes)} auxiliary writes")
    print(f"local start: {schedule[0].isoformat()}")
    print(f"local end:   {schedule[-1].isoformat()}")
    for day, count in per_day_counts.items():
        print(f"{day}: {count} records")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"firebase http error: {exc.code} {body}", file=sys.stderr)
        raise SystemExit(1)
    except error.URLError as exc:
        print(f"firebase network error: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        print("cancelled", file=sys.stderr)
        raise SystemExit(130)













