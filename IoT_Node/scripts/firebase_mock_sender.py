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
import copy
import hashlib
import json
import math
import random
import sys
from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
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
DEFAULT_NODE_ROOT = "/Node1"
DEFAULT_NODE_ID = "Node1"
DEFAULT_NODE_NAME = "Binh Phu"
DEFAULT_SITE_ID = "Binh Phu, Vinh Long"
DEFAULT_DEVICE_UID = "esp32s3_node1"
DEFAULT_POWER_TYPE = "solar_battery"
DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"
DEFAULT_FW_VERSION = "esp-idf: v4.4.6 3572900934"
DEFAULT_RUNNING_PARTITION = "ota_0"
DEFAULT_SEED = 42
DEFAULT_DAYS = 1
DEFAULT_DEVICE_JITTER_MIN_SEC = 25
DEFAULT_DEVICE_JITTER_MAX_SEC = 170
DEFAULT_SERVER_DELAY_MIN_SEC = 50
DEFAULT_SERVER_DELAY_MAX_SEC = 116
DEFAULT_WAKE_INTERVAL_SEC = 900
DEFAULT_TELEMETRY_RETENTION_DAYS = 30
DEFAULT_PRIMARY_POLL_AFTER_SEC = DEFAULT_WAKE_INTERVAL_SEC + 300
DEFAULT_RETRY_AFTER_NO_CHANGE_SEC = 300
WATERING_HOUR = 7
FERTILIZING_MONTH = 4
FERTILIZING_DAY = 4
FERTILIZING_HOUR = 8
PH_DISTURBANCE_DAY_OFFSET = 24
PH_DISTURBANCE_START_HOUR = 15.0
PH_DISTURBANCE_RECOVERY_HOURS = 72.0
MOCK_RECONSTRUCTED_CUTOFF_DATE = date(2026, 4, 24)
EC_LINEAR_SLOPE = 0.849334
EC_LINEAR_INTERCEPT = 113.839755
EC_HUMIDITY_PARABOLA_A = -0.5063
EC_HUMIDITY_PARABOLA_B = 79.34
EC_HUMIDITY_PARABOLA_C = -2550.61
MAX_N_PPM = 260.0
MAX_P_PPM = 420.0
MAX_K_PPM = 420.0
BACKUP_PH_STABLE_MIN = 5.8
BACKUP_PH_STABLE_MAX = 7.0
BACKUP_RECONSTRUCTED_RATE = 0.015
BACKUP_BUFFERED_RATE = 0.006
BACKUP_FALLBACK_RATE = 0.003
DEFAULT_LAYER0_HISTORY_ROOT = SCRIPT_DIR.parents[1] / "Backend" / "Output_data" / "Layer0" / "Firebase_data" / "history"
DEFAULT_BACKUP_LAYER1_ROOT = SCRIPT_DIR.parents[1] / "Backend" / "Output_data_bk" / "Output_data_bk" / "Layer1"
DEFAULT_BACKUP_LAYER1_FALLBACK_ROOT = SCRIPT_DIR.parents[1] / "Backend" / "Output_data copy" / "Layer1"
DEFAULT_ARCHIVE_METEO_HISTORY_ROOT = SCRIPT_DIR.parents[1] / "Backend" / "Output_data" / "Layer0" / "OpenMeteo_Data" / "Meteo_archive_era5" / "history"
SHT_HUMIDITY_HOURLY_TARGETS = [
    99.99, 99.99, 99.99, 99.99, 99.99, 99.99, 99.99, 97.84,
    91.23, 83.06, 75.23, 70.81, 66.52, 67.01, 67.88, 66.35,
    68.82, 75.98, 85.45, 90.06, 93.67, 95.96, 97.81, 98.66,
]
SHT_TEMP_HOURLY_TARGETS = [
    26.71, 26.56, 26.57, 26.39, 26.38, 26.10, 26.82, 28.18,
    29.60, 31.11, 32.76, 33.54, 34.04, 33.96, 33.86, 33.90,
    33.13, 31.11, 28.96, 28.16, 27.67, 27.39, 27.12, 26.84,
]
NPK_HUMIDITY_HOURLY_TARGETS = [
    63.43, 62.75, 63.21, 62.42, 63.05, 64.54, 67.40, 68.15,
    68.05, 67.70, 67.16, 67.20, 66.14, 65.54, 65.01, 63.75,
    63.16, 61.16, 62.93, 63.95, 63.46, 63.93, 63.42, 63.32,
]
NPK_TEMP_HOURLY_TARGETS = [
    28.57, 28.41, 28.37, 28.20, 28.22, 27.93, 27.71, 27.75,
    27.74, 27.83, 27.91, 28.37, 28.90, 29.33, 28.59, 28.75,
    28.17, 27.08, 28.35, 29.04, 28.99, 28.88, 28.81, 28.65,
]
N_TARGETS_HOURLY = [
    57.54, 53.84, 56.25, 51.97, 56.02, 55.25, 63.67, 67.39,
    66.44, 66.30, 63.90, 65.90, 62.42, 63.51, 61.46, 62.75,
    59.67, 61.45, 60.92, 59.36, 58.71, 58.67, 58.83, 55.93,
]
P_TARGETS_HOURLY = [
    179.77, 171.18, 176.80, 167.03, 176.38, 174.42, 193.74, 202.53,
    200.41, 199.95, 194.28, 199.24, 191.02, 193.41, 188.61, 190.52,
    183.53, 185.41, 186.51, 184.00, 182.59, 182.33, 182.55, 176.02,
]
K_TARGETS_HOURLY = [
    173.13, 164.37, 170.07, 160.29, 169.67, 167.58, 187.31, 195.94,
    193.82, 193.38, 187.72, 192.71, 184.42, 186.77, 181.93, 184.14,
    177.16, 179.45, 180.18, 177.39, 175.93, 175.71, 175.97, 169.36,
]


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
    auto_stop_before_layer0_start: bool
    seed: int
    device_jitter_min_sec: int
    device_jitter_max_sec: int
    server_delay_min_sec: int
    server_delay_max_sec: int
    upload: bool
    update_live: bool
    output_file: Path | None
    print_each: bool
    source_mode: str


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


@dataclass(frozen=True)
class SchedulePoint:
    local_dt: datetime
    is_retry: bool = False


@dataclass
class MockSoilState:
    soil_humidity_pct: float
    ec_value: float
    nutrient_n: float
    nutrient_p: float
    nutrient_k: float
    soil_ph: float
    npk_soil_humidity_memory: float
    ec_hold_remaining: int = 0
    npk_response_delay_remaining: int = 0
    npk_pending_wetness_boost: float = 0.0
    npk_hold_n: int = 0
    npk_hold_p: int = 0
    npk_hold_k: int = 0
    npk_warmup_remaining: int = 18
    ph_disturbance_started_at: datetime | None = None
    last_valid_npk_values: dict[str, float | int] | None = None
    applied_watering_dates: set[str] | None = None
    applied_fertilizing_dates: set[str] | None = None
    ph_disturbance_dates: set[str] | None = None


@dataclass
class BackupReplayState:
    last_raw_ec: float | None = None
    last_raw_soil_hum: float | None = None
    last_raw_air_hum: float | None = None
    last_ec: int | None = None
    last_soil_hum: float | None = None
    last_soil_temp: float | None = None
    last_air_hum: float | None = None
    last_air_temp: float | None = None
    last_ph: float | None = None
    last_n: int | None = None
    last_p: int | None = None
    last_k: int | None = None
    ec_hold_remaining: int = 0
    npk_hold_n: int = 0
    npk_hold_p: int = 0
    npk_hold_k: int = 0
    npk_warmup_remaining: int = 12


@dataclass(frozen=True)
class ArchiveMeteoDayProfile:
    hours: tuple[float, ...]
    temperature_2m: tuple[float, ...]
    relative_humidity_2m: tuple[float, ...]
    rain: tuple[float, ...]
    precipitation: tuple[float, ...]
    temp_min: float
    temp_max: float
    hum_min: float
    hum_max: float
    rain_total: float
    precip_total: float


def parse_args() -> AppConfig:
    parser = argparse.ArgumentParser(
        description="Sinh du lieu gia lap NPK + SHT30 theo nhip 15 phut, co retry burst khi loi, va co the day len Firebase RTDB."
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
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="So ngay can seed theo lich 96 slot/ngay.")
    parser.add_argument(
        "--end",
        help="Ngay ket thuc inclusive theo YYYY-MM-DD hoac ISO datetime. Neu co, script tu tinh lai --days.",
    )
    parser.add_argument(
        "--stop-before-layer0-start",
        action="store_true",
        help="Tu dong dung o ngay truoc moc dau tien dang co trong Backend/Output_data/Layer0/Firebase_data/history.",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--source-mode",
        choices=("backup", "generated"),
        default="backup",
        help="Nguon sinh du lieu: replay truc tiep tu backup Layer1 hoac mo hinh sinh moi.",
    )
    parser.add_argument(
        "--device-jitter-min-sec",
        type=int,
        default=DEFAULT_DEVICE_JITTER_MIN_SEC,
        help="Do tre toi thieu cua thoi diem do trong moi slot 15 phut.",
    )
    parser.add_argument(
        "--device-jitter-max-sec",
        type=int,
        default=DEFAULT_DEVICE_JITTER_MAX_SEC,
        help="Do tre toi da cua thoi diem do trong moi slot 15 phut.",
    )
    parser.add_argument(
        "--server-delay-min-sec",
        type=int,
        default=DEFAULT_SERVER_DELAY_MIN_SEC,
        help="Do tre toi thieu tu sample_time sang upload_time label.",
    )
    parser.add_argument(
        "--server-delay-max-sec",
        type=int,
        default=DEFAULT_SERVER_DELAY_MAX_SEC,
        help="Do tre toi da tu sample_time sang upload_time label.",
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
    if args.device_jitter_max_sec >= DEFAULT_WAKE_INTERVAL_SEC:
        parser.error("device jitter phai < 900 giay de khong tran sang slot 15 phut ke")

    start = parse_start_date(args.start, args.timezone)
    end = parse_start_date(args.end, args.timezone) if args.end else None
    if args.stop_before_layer0_start:
        detected_start = detect_first_layer0_date()
        if detected_start is None:
            parser.error("Khong tim thay moc Layer0 dau tien de tinh --stop-before-layer0-start.")
        candidate_end = datetime.combine(
            detected_start.date() - timedelta(days=1),
            datetime.min.time(),
            tzinfo=start.tzinfo,
        )
        end = candidate_end if end is None else min(end, candidate_end)
    if end is not None and end < start:
        parser.error("--end phai >= --start sau khi ap dung --stop-before-layer0-start")
    days = args.days if end is None else ((end.date() - start.date()).days + 1)
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
        days=days,
        auto_stop_before_layer0_start=bool(args.stop_before_layer0_start),
        seed=args.seed,
        device_jitter_min_sec=args.device_jitter_min_sec,
        device_jitter_max_sec=args.device_jitter_max_sec,
        server_delay_min_sec=args.server_delay_min_sec,
        server_delay_max_sec=args.server_delay_max_sec,
        upload=upload,
        update_live=not args.no_update_live,
        output_file=args.output_file,
        print_each=args.print_each,
        source_mode=args.source_mode,
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


def detect_first_layer0_date() -> datetime | None:
    history_root = DEFAULT_LAYER0_HISTORY_ROOT
    if not history_root.exists():
        return None
    history_files = sorted(history_root.rglob("*.json"))
    if not history_files:
        return None
    first_file = history_files[0]
    year = int(first_file.parent.parent.parent.name)
    month = int(first_file.parent.parent.name)
    day = int(first_file.parent.name)
    return datetime(year, month, day, tzinfo=ZoneInfo(DEFAULT_TIMEZONE))


def parse_local_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=ZoneInfo(DEFAULT_TIMEZONE))
    return parsed.astimezone(ZoneInfo(DEFAULT_TIMEZONE))


@lru_cache(maxsize=1)
def load_archive_meteo_day_profiles() -> dict[str, ArchiveMeteoDayProfile]:
    root = DEFAULT_ARCHIVE_METEO_HISTORY_ROOT
    if not root.exists():
        return {}

    grouped: dict[str, list[dict[str, float]]] = {}
    for path in sorted(root.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        record = payload.get("record")
        if not isinstance(record, dict):
            continue
        packet = record.get("packet")
        if not isinstance(packet, dict):
            continue
        meteo = packet.get("meteo_data")
        if not isinstance(meteo, dict):
            continue
        observed = parse_local_iso_datetime(str(record.get("observed_at_local") or ""))
        if observed is None:
            continue
        entry = {
            "hour": observed.hour + observed.minute / 60.0 + observed.second / 3600.0,
            "temperature_2m": float(meteo.get("temperature_2m") or 0.0),
            "relative_humidity_2m": float(meteo.get("relative_humidity_2m") or 0.0),
            "rain": float(meteo.get("rain") or 0.0),
            "precipitation": float(meteo.get("precipitation") or 0.0),
        }
        grouped.setdefault(observed.date().isoformat(), []).append(entry)

    profiles: dict[str, ArchiveMeteoDayProfile] = {}
    for date_key, entries in grouped.items():
        ordered = sorted(entries, key=lambda item: item["hour"])
        hours = tuple(item["hour"] for item in ordered)
        temp_values = tuple(item["temperature_2m"] for item in ordered)
        hum_values = tuple(item["relative_humidity_2m"] for item in ordered)
        rain_values = tuple(item["rain"] for item in ordered)
        precip_values = tuple(item["precipitation"] for item in ordered)
        profiles[date_key] = ArchiveMeteoDayProfile(
            hours=hours,
            temperature_2m=temp_values,
            relative_humidity_2m=hum_values,
            rain=rain_values,
            precipitation=precip_values,
            temp_min=min(temp_values) if temp_values else 0.0,
            temp_max=max(temp_values) if temp_values else 0.0,
            hum_min=min(hum_values) if hum_values else 0.0,
            hum_max=max(hum_values) if hum_values else 0.0,
            rain_total=sum(rain_values),
            precip_total=sum(precip_values),
        )
    return profiles


def _load_history_jsonl_by_event_key(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return rows
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return rows
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        source = rec.get("source")
        if not isinstance(source, dict):
            continue
        event_key = str(source.get("event_key") or "").strip()
        if not event_key:
            continue
        rows[event_key] = rec
    return rows


def _backup_replay_start_index(rows: list[dict[str, Any]]) -> int:
    if len(rows) < 12:
        return 0
    for idx in range(len(rows) - 11):
        window = rows[idx : idx + 12]
        ph_values = [float(item["npk_per"]["soil_ph"]) for item in window]
        stable_count = sum(1 for value in ph_values if 5.8 <= value <= 7.2)
        low_ph_count = sum(1 for value in ph_values if value <= 4.5)
        if stable_count >= 10 and low_ph_count == 0:
            return idx
    return 0


def _backup_replay_rotation_index(rows: list[dict[str, Any]]) -> int:
    if len(rows) < 4:
        return 0
    tail = rows[-1]
    best_idx = 0
    best_score: float | None = None
    for idx, item in enumerate(rows[:-1]):
        score = (
            abs(float(item["npk_per"]["soil_ec_us_cm"]) - float(tail["npk_per"]["soil_ec_us_cm"])) * 1.0
            + abs(float(item["npk_per"]["soil_humidity_pct"]) - float(tail["npk_per"]["soil_humidity_pct"])) * 3.0
            + abs(float(item["sht_per"]["humidity_air_pct"]) - float(tail["sht_per"]["humidity_air_pct"])) * 1.2
            + abs(float(item["sht_per"]["temp_air_c"]) - float(tail["sht_per"]["temp_air_c"])) * 4.0
            + abs(float(item["npk_per"]["soil_ph"]) - float(tail["npk_per"]["soil_ph"])) * 10.0
        )
        if best_score is None or score < best_score:
            best_score = score
            best_idx = idx
    return best_idx


@lru_cache(maxsize=1)
def load_backup_replay_payloads() -> list[dict[str, Any]]:
    root = DEFAULT_BACKUP_LAYER1_ROOT
    if not root.exists():
        root = DEFAULT_BACKUP_LAYER1_FALLBACK_ROOT
    npk_rows = _load_history_jsonl_by_event_key(root / "npk" / "history.jsonl")
    sht_rows = _load_history_jsonl_by_event_key(root / "sht30" / "history.jsonl")
    common_keys = sorted(set(npk_rows).intersection(sht_rows), key=lambda value: int(value))
    joined_rows: list[dict[str, Any]] = []
    for event_key in common_keys:
        npk_rec = npk_rows[event_key]
        sht_rec = sht_rows[event_key]
        npk_per = npk_rec.get("perception") or {}
        sht_per = sht_rec.get("perception") or {}
        ts_info = npk_rec.get("timestamps") or sht_rec.get("timestamps") or {}
        observed_at_local = str(ts_info.get("observed_at_local") or "")
        observed_dt = parse_local_iso_datetime(observed_at_local)
        if observed_dt is None:
            continue
        joined_rows.append(
            {
                "event_key": event_key,
                "observed_dt": observed_dt,
                "npk_per": npk_per,
                "sht_per": sht_per,
            }
        )

    if not joined_rows:
        return []

    start_idx = _backup_replay_start_index(joined_rows)
    stable_rows = joined_rows[start_idx:]
    if not stable_rows:
        stable_rows = joined_rows
    rotate_idx = _backup_replay_rotation_index(stable_rows)
    ordered_rows = stable_rows[rotate_idx:] + stable_rows[:rotate_idx]

    payloads: list[dict[str, Any]] = []
    for row in ordered_rows:
        event_key = row["event_key"]
        npk_per = row["npk_per"]
        sht_per = row["sht_per"]
        observed_dt = row["observed_dt"]
        day_phase = calc_day_fraction(observed_dt)
        rssi = int(clamp(-67 + 5.0 * math.sin(day_phase * 2.0 * math.pi) - 2.0 + (int(event_key) % 5) * 0.4, -96, -45))
        payloads.append(
            {
                "packet": {
                    "npk_data": {
                        "read_ok": True,
                        "error_code": "",
                        "error_code_raw": 0,
                        "retry_count": 0,
                        "timeout_ms": 2000,
                        "read_duration_ms": 64,
                        "crc_ok": True,
                        "frame_ok": True,
                        "sample_interval_ms": DEFAULT_WAKE_INTERVAL_SEC * 1000,
                        "consecutive_fail_count": 0,
                        "recovered_after_fail": False,
                        "fail_streak_before_recover": 0,
                        "sensor_alarm": False,
                        "npk_values_valid": True,
                        "npk_signal_present": True,
                        "temp": round(float(npk_per.get("soil_temp_c") or 0.0), 2),
                        "hum": round(float(npk_per.get("soil_humidity_pct") or 0.0), 2),
                        "ph": round(float(npk_per.get("soil_ph") or 0.0), 1),
                        "ec": int(round(float(npk_per.get("soil_ec_us_cm") or 0.0))),
                        "N": round(float(npk_per.get("n_ppm") or 0.0), 1),
                        "P": round(float(npk_per.get("p_ppm") or 0.0), 1),
                        "K": round(float(npk_per.get("k_ppm") or 0.0), 1),
                    },
                    "sht30_data": {
                        "sht_read_ok": True,
                        "sht_sample_valid": True,
                        "sht_temp_c": round(float(sht_per.get("temp_air_c") or 0.0), 2),
                        "sht_hum_pct": round(float(sht_per.get("humidity_air_pct") or 0.0), 2),
                        "sht_error": "",
                        "sht_retry_count": 0,
                        "sht_read_elapsed_ms": 22,
                        "sht_invalid_streak": 0,
                    },
                    "system_data": {
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
                        "heap_free": 327800,
                        "stack_high_water": 4160,
                        "task_name": "sensor-cycle",
                        "fw_version": DEFAULT_FW_VERSION,
                        "running_partition": DEFAULT_RUNNING_PARTITION,
                    },
                }
            }
        )
    return payloads


def archive_profile_for(local_dt: datetime) -> ArchiveMeteoDayProfile | None:
    return load_archive_meteo_day_profiles().get(local_dt.date().isoformat())


def build_backup_replay_profile(seed: int, local_dt: datetime) -> dict[str, float]:
    rng = random.Random(seed * 1013 + local_dt.date().toordinal() * 53 + 1337)
    return {
        "ec_scale": 0.88 + rng.uniform(-0.02, 0.03),
        "ec_offset": 85.0 + rng.uniform(-14.0, 18.0),
        "ec_delta_scale": 1.0 + rng.uniform(-0.03, 0.06),
        "cycle_ec_drift": rng.uniform(-12.0, 12.0),
        "cycle_hum_drift": rng.uniform(-1.4, 1.6),
        "soil_hum_offset": rng.uniform(-2.0, 2.4),
        "soil_temp_offset": rng.uniform(-0.35, 0.45),
        "air_temp_offset": rng.uniform(-0.55, 0.65),
        "air_hum_offset": rng.uniform(-3.2, 3.2),
        "ph_offset": rng.choice((-0.1, 0.0, 0.1)),
    }


def advance_backup_ph_value(
    last_value: float | None,
    target_value: float,
    event_strength: int,
) -> float:
    del event_strength
    stable_target = round(clamp(target_value, BACKUP_PH_STABLE_MIN, BACKUP_PH_STABLE_MAX) * 10.0) / 10.0
    if last_value is None:
        return round(clamp(stable_target, 6.0, 6.8), 1)

    current = round(clamp(last_value, BACKUP_PH_STABLE_MIN, BACKUP_PH_STABLE_MAX) * 10.0) / 10.0
    delta = stable_target - current
    if abs(delta) < 0.05:
        return round(current, 1)

    step = 0.1
    direction = 1.0 if delta > 0.0 else -1.0
    updated = current + direction * min(step, abs(delta))
    return round(clamp(updated, BACKUP_PH_STABLE_MIN, BACKUP_PH_STABLE_MAX), 1)


def transform_backup_payload(
    cfg: AppConfig,
    raw_payload: dict[str, Any],
    local_dt: datetime,
    replay_state: BackupReplayState,
    cycle_index: int,
) -> dict[str, Any]:
    payload = copy.deepcopy(raw_payload)
    packet = payload["packet"]
    npk = packet["npk_data"]
    sht = packet["sht30_data"]
    profile = build_backup_replay_profile(cfg.seed, local_dt)
    row_rng = random.Random(cfg.seed * 4099 + int(local_dt.timestamp()) + cycle_index * 971)

    raw_ec = float(npk.get("ec") or 0.0)
    raw_soil_hum = float(npk.get("hum") or 0.0)
    raw_soil_temp = float(npk.get("temp") or 0.0)
    raw_air_hum = float(sht.get("sht_hum_pct") or 0.0)
    raw_air_temp = float(sht.get("sht_temp_c") or 0.0)
    raw_ph = float(npk.get("ph") or 0.0)

    raw_ec_diff = 0.0 if replay_state.last_raw_ec is None else raw_ec - replay_state.last_raw_ec
    raw_soil_hum_diff = 0.0 if replay_state.last_raw_soil_hum is None else raw_soil_hum - replay_state.last_raw_soil_hum
    raw_air_hum_diff = 0.0 if replay_state.last_raw_air_hum is None else raw_air_hum - replay_state.last_raw_air_hum

    transformed_ec_base = raw_ec * profile["ec_scale"] + profile["ec_offset"] + cycle_index * profile["cycle_ec_drift"]
    transformed_soil_hum_base = raw_soil_hum + profile["soil_hum_offset"] + cycle_index * profile["cycle_hum_drift"]
    transformed_soil_temp_base = raw_soil_temp + profile["soil_temp_offset"]
    transformed_air_temp_base = raw_air_temp + profile["air_temp_offset"]
    transformed_ph_base = round((raw_ph + profile["ph_offset"]) * 10.0) / 10.0

    if replay_state.last_soil_hum is None:
        soil_hum = round(clamp(transformed_soil_hum_base, 44.0, 85.6), 2)
    else:
        soil_hum_target = 0.62 * (replay_state.last_soil_hum + raw_soil_hum_diff) + 0.38 * transformed_soil_hum_base
        soil_hum = round(clamp(soil_hum_target, 44.0, 85.6), 2)

    if replay_state.last_soil_temp is None:
        soil_temp = round(clamp(transformed_soil_temp_base, 24.2, 34.0), 2)
    else:
        soil_temp = round(
            clamp(0.70 * (replay_state.last_soil_temp + (raw_soil_temp - (replay_state.last_soil_temp - profile["soil_temp_offset"]))) + 0.30 * transformed_soil_temp_base, 24.2, 34.0),
            2,
        )

    if raw_air_hum >= 99.95:
        air_hum = 99.99
    elif replay_state.last_air_hum is None:
        air_hum = round(clamp(raw_air_hum + profile["air_hum_offset"], 41.0, 99.95), 2)
    else:
        air_hum_target = 0.66 * (replay_state.last_air_hum + raw_air_hum_diff) + 0.34 * (raw_air_hum + profile["air_hum_offset"])
        air_hum = round(clamp(air_hum_target, 41.0, 99.95), 2)

    if replay_state.last_air_temp is None:
        air_temp = round(clamp(transformed_air_temp_base, 20.0, 39.9), 2)
    else:
        air_temp = round(clamp(0.68 * replay_state.last_air_temp + 0.32 * transformed_air_temp_base, 20.0, 39.9), 2)

    if abs(raw_ec_diff) >= 18.0 or raw_soil_hum_diff >= 3.0 or abs(raw_air_hum_diff) >= 8.0:
        event_strength = 2
    elif abs(raw_ec_diff) >= 5.0 or raw_soil_hum_diff >= 1.2 or abs(raw_air_hum_diff) >= 3.5:
        event_strength = 1
    else:
        event_strength = 0

    soil_ph = advance_backup_ph_value(replay_state.last_ph, transformed_ph_base, event_strength)

    if replay_state.last_ec is None:
        ec_value = int(round(clamp(transformed_ec_base, 120.0, 900.0)))
        replay_state.ec_hold_remaining = 0
    else:
        ec_delta_target = replay_state.last_ec + raw_ec_diff * profile["ec_delta_scale"] + 0.35 * raw_soil_hum_diff
        ec_target = 0.74 * ec_delta_target + 0.26 * transformed_ec_base
        ec_target = clamp(ec_target, 120.0, 900.0)
        ec_value, replay_state.ec_hold_remaining = advance_ec_value(
            replay_state.last_ec,
            ec_target,
            replay_state.ec_hold_remaining,
            row_rng,
            event_strength,
            replay_state.npk_warmup_remaining,
        )
        ec_value = int(round(clamp(ec_value, 120.0, 900.0)))

    target_n, target_p, target_k = nutrient_targets_from_ec(ec_value)
    n_value = int(round(clamp(target_n, 0.0, MAX_N_PPM)))
    p_value = int(round(clamp(target_p, 0.0, MAX_P_PPM)))
    k_value = int(round(clamp(target_k, 0.0, MAX_K_PPM)))

    replay_state.npk_warmup_remaining = max(0, replay_state.npk_warmup_remaining - 1)
    replay_state.last_raw_ec = raw_ec
    replay_state.last_raw_soil_hum = raw_soil_hum
    replay_state.last_raw_air_hum = raw_air_hum
    replay_state.last_ec = ec_value
    replay_state.last_soil_hum = soil_hum
    replay_state.last_soil_temp = soil_temp
    replay_state.last_air_hum = air_hum
    replay_state.last_air_temp = air_temp
    replay_state.last_ph = soil_ph
    replay_state.last_n = n_value
    replay_state.last_p = p_value
    replay_state.last_k = k_value

    npk["temp"] = soil_temp
    npk["hum"] = soil_hum
    npk["ph"] = soil_ph
    npk["ec"] = ec_value
    npk["N"] = n_value
    npk["P"] = p_value
    npk["K"] = k_value
    sht["sht_temp_c"] = air_temp
    sht["sht_hum_pct"] = air_hum
    return payload


def interpolate_archive_value(hours: tuple[float, ...], values: tuple[float, ...], hour: float) -> float | None:
    if not hours or not values or len(hours) != len(values):
        return None
    if len(hours) == 1:
        return values[0]
    if hour <= hours[0]:
        return values[0]
    if hour >= hours[-1]:
        return values[-1]
    pos = bisect_right(hours, hour)
    left = max(0, pos - 1)
    right = min(len(hours) - 1, pos)
    if left == right:
        return values[left]
    left_hour = hours[left]
    right_hour = hours[right]
    if right_hour == left_hour:
        return values[left]
    ratio = (hour - left_hour) / (right_hour - left_hour)
    return values[left] * (1.0 - ratio) + values[right] * ratio


def normalized_value(value: float | None, low: float, high: float) -> float:
    if value is None:
        return 0.5
    if high <= low:
        return 0.5
    return clamp((value - low) / (high - low), 0.0, 1.0)


def soft_clip(value: float, low: float, high: float, low_softness: float = 0.55, high_softness: float = 0.45) -> float:
    if low >= high:
        return value
    if value < low:
        return low + (value - low) * low_softness
    if value > high:
        return high + (value - high) * high_softness
    return value


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def calc_day_fraction(local_dt: datetime) -> float:
    return (local_dt.hour * 3600 + local_dt.minute * 60 + local_dt.second) / 86400.0


def clock_hour(local_dt: datetime) -> float:
    return local_dt.hour + local_dt.minute / 60.0 + local_dt.second / 3600.0


def gaussian_peak(x: float, center: float, sigma: float) -> float:
    return math.exp(-((x - center) ** 2) / (2.0 * sigma * sigma))


def gaussian_noise(rng: random.Random, sigma: float, mean: float = 0.0) -> float:
    if sigma <= 0.0:
        return mean
    return rng.gauss(mean, sigma)


def ec_humidity_baseline(soil_humidity_pct: float) -> float:
    base = (
        EC_HUMIDITY_PARABOLA_A * (soil_humidity_pct ** 2)
        + EC_HUMIDITY_PARABOLA_B * soil_humidity_pct
        + EC_HUMIDITY_PARABOLA_C
    )
    return clamp(base, 120.0, 620.0)


def smooth_cycle(position: float, period: float, phase: float = 0.0) -> float:
    return math.sin((position / period + phase) * 2.0 * math.pi)


def day_seed(cfg: AppConfig, local_dt: datetime, salt: int) -> int:
    return cfg.seed * 1009 + local_dt.date().toordinal() * 37 + salt


def daily_watering_hour(cfg: AppConfig, local_dt: datetime) -> float:
    rng = random.Random(day_seed(cfg, local_dt, 711))
    return 6.5 + rng.uniform(0.0, 1.5)


def fertilizing_hour(_cfg: AppConfig, _local_dt: datetime) -> float:
    return 8.0


def irrigation_effect_air(cfg: AppConfig, local_dt: datetime) -> float:
    hour = clock_hour(local_dt)
    watering_hour = daily_watering_hour(cfg, local_dt)
    morning = gaussian_peak(hour, watering_hour + 0.25, 0.85)
    residue = gaussian_peak(hour, watering_hour + 1.2, 0.95)
    return clamp(0.9 * morning + 0.35 * residue, 0.0, 1.0)


def irrigation_effect_soil(cfg: AppConfig, local_dt: datetime) -> float:
    hour = clock_hour(local_dt)
    watering_hour = daily_watering_hour(cfg, local_dt)
    morning = gaussian_peak(hour, watering_hour + 0.15, 1.05)
    residue = gaussian_peak(hour, watering_hour + 1.55, 1.25)
    return clamp(morning + 0.45 * residue, 0.0, 1.0)


def fertilizing_effect(cfg: AppConfig, local_dt: datetime) -> float:
    hour = clock_hour(local_dt)
    if local_dt.month != FERTILIZING_MONTH or local_dt.day != FERTILIZING_DAY:
        return 0.0
    event_hour = fertilizing_hour(cfg, local_dt)
    spike = gaussian_peak(hour, event_hour + 0.1, 0.65)
    tail = gaussian_peak(hour, event_hour + 1.4, 1.05)
    return clamp(spike + 0.35 * tail, 0.0, 1.0)


def is_watering_event(cfg: AppConfig, soil_state: MockSoilState, local_dt: datetime) -> bool:
    date_key = local_dt.strftime("%Y-%m-%d")
    if soil_state.applied_watering_dates is None:
        soil_state.applied_watering_dates = set()
    if date_key in soil_state.applied_watering_dates:
        return False
    event_hour = daily_watering_hour(cfg, local_dt)
    return clock_hour(local_dt) >= event_hour


def is_fertilizing_event(cfg: AppConfig, soil_state: MockSoilState, local_dt: datetime) -> bool:
    if local_dt.month != FERTILIZING_MONTH or local_dt.day != FERTILIZING_DAY:
        return False
    date_key = local_dt.strftime("%Y-%m-%d")
    if soil_state.applied_fertilizing_dates is None:
        soil_state.applied_fertilizing_dates = set()
    if date_key in soil_state.applied_fertilizing_dates:
        return False
    return clock_hour(local_dt) >= fertilizing_hour(cfg, local_dt)



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
    is_backfill_period = local_dt.date() < MOCK_RECONSTRUCTED_CUTOFF_DATE
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
    weather_mode = day_rng.choice([-3, -2, -1, 0, 1, 2, 3]) if is_backfill_period else day_rng.choice([-2, -1, 0, 1, 2])
    humidity_floor = clamp(
        (
            50.0 if is_backfill_period else 58.0
        )
        + day_rng.uniform(-12.0, 12.5)
        + (7.4 if is_backfill_period else 4.0) * max(0.0, weather_regime)
        - (4.8 if is_backfill_period else 3.0) * max(0.0, week_cycle)
        + (2.7 if is_backfill_period else 1.8) * weather_mode,
        40.0 if is_backfill_period else 48.0,
        86.5 if is_backfill_period else 82.0,
    )
    humidity_ceiling = clamp(
        99.35 + day_rng.uniform(-0.70, 0.55) + (0.12 if is_backfill_period else 0.0) * max(0.0, weather_regime),
        98.15 if is_backfill_period else 98.8,
        99.99,
    )
    temp_floor = clamp(
        (22.2 if is_backfill_period else 23.4)
        + day_rng.uniform(-2.4, 2.0)
        - (1.0 if is_backfill_period else 0.7) * max(0.0, weather_regime)
        - (0.7 if is_backfill_period else 0.5) * max(0.0, week_cycle)
        + (0.48 if is_backfill_period else 0.35) * weather_mode,
        20.5 if is_backfill_period else 21.5,
        29.8 if is_backfill_period else 29.0,
    )
    temp_ceiling = clamp(
        (30.8 if is_backfill_period else 31.3)
        + day_rng.uniform(-3.8, 4.5)
        + (2.3 if is_backfill_period else 1.7) * max(0.0, weather_regime)
        + (1.2 if is_backfill_period else 0.9) * max(0.0, monthly_cycle)
        + (0.82 if is_backfill_period else 0.65) * weather_mode,
        28.2 if is_backfill_period else 29.0,
        40.4 if is_backfill_period else 39.2,
    )
    return {
        "day_index": float(day_index),
        "is_backfill_period": is_backfill_period,
        "week_cycle": week_cycle,
        "biweekly_cycle": biweekly_cycle,
        "monthly_cycle": monthly_cycle,
        "weather_regime": weather_regime,
        "weather_mode": float(weather_mode),
        "nutrient_regime": nutrient_regime,
        "recovery_bias": recovery_bias,
        "system_stress": system_stress,
        "temp_hour_warp": day_rng.uniform(0.74, 1.28) if is_backfill_period else day_rng.uniform(0.82, 1.18),
        "hum_hour_warp": day_rng.uniform(0.72, 1.34) if is_backfill_period else day_rng.uniform(0.80, 1.22),
        "temp_curve_mix": day_rng.uniform(0.22, 0.58) if is_backfill_period else day_rng.uniform(0.12, 0.42),
        "hum_curve_mix": day_rng.uniform(0.24, 0.66) if is_backfill_period else day_rng.uniform(0.14, 0.46),
        "cloud_energy_drag": 0.55 * max(0.0, weather_regime) + 0.35 * max(0.0, monthly_cycle),
        "air_temp_offset": day_rng.uniform(-0.7, 0.7) + 0.85 * week_cycle + 1.15 * monthly_cycle + 0.65 * weather_regime,
        "air_temp_amp": day_rng.uniform(0.88, 1.14) + 0.06 * week_cycle,
        "air_hum_offset": day_rng.uniform(-4.5, 4.5) - 3.2 * week_cycle + 4.4 * max(0.0, weather_regime) + 1.4 * biweekly_cycle,
        "air_hum_amp": day_rng.uniform(0.86, 1.16) - 0.05 * weather_regime,
        "sht_temp_phase_shift": day_rng.uniform(-1.9, 2.1) + 0.45 * weather_regime - 0.18 * recovery_bias if is_backfill_period else day_rng.uniform(-0.75, 0.95) + 0.25 * weather_regime,
        "sht_temp_scale": day_rng.uniform(0.78, 1.24) + 0.07 * week_cycle if is_backfill_period else day_rng.uniform(0.84, 1.18) + 0.05 * week_cycle,
        "sht_temp_bias": day_rng.uniform(-1.8, 1.8) + 1.0 * week_cycle + 0.9 * monthly_cycle + 0.6 * weather_mode if is_backfill_period else day_rng.uniform(-1.1, 1.1) + 0.7 * week_cycle + 0.55 * monthly_cycle + 0.35 * weather_mode,
        "sht_temp_floor": temp_floor,
        "sht_temp_ceiling": temp_ceiling,
        "sht_temp_gamma": clamp(day_rng.uniform(0.70, 1.60) + 0.06 * weather_mode, 0.65, 1.60) if is_backfill_period else clamp(day_rng.uniform(0.82, 1.28) + 0.05 * weather_mode, 0.75, 1.45),
        "sht_hum_phase_shift": day_rng.uniform(-2.85, 2.85) + 0.70 * weather_regime - 0.40 * recovery_bias if is_backfill_period else day_rng.uniform(-2.0, 2.0) + 0.55 * weather_regime - 0.25 * recovery_bias,
        "sht_hum_scale": day_rng.uniform(0.78, 1.26) + 0.05 * max(0.0, weather_regime) if is_backfill_period else day_rng.uniform(0.84, 1.20) + 0.04 * max(0.0, weather_regime),
        "sht_hum_bias": day_rng.uniform(-8.0, 8.0) - 3.8 * week_cycle + 5.6 * max(0.0, weather_regime) + 2.0 * biweekly_cycle if is_backfill_period else day_rng.uniform(-5.5, 5.5) - 2.8 * week_cycle + 4.2 * max(0.0, weather_regime) + 1.5 * biweekly_cycle,
        "sht_hum_floor": humidity_floor,
        "sht_hum_ceiling": humidity_ceiling,
        "sht_hum_gamma": clamp(day_rng.uniform(0.62, 1.70) + 0.05 * weather_mode, 0.58, 1.68) if is_backfill_period else clamp(day_rng.uniform(0.72, 1.42) + 0.04 * weather_mode, 0.65, 1.55),
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
        "humidity_day_shock": day_rng.uniform(0.0, 1.0),
        "temp_day_shock": day_rng.uniform(0.0, 1.0),
    }


def nutrient_targets_from_ec(ec_value: float, rng: random.Random | None = None) -> tuple[float, float, float]:
    del rng
    n_target = max(0.0, 0.2090 * ec_value - 39.10)
    p_target = max(0.0, 0.4821 * ec_value - 43.16)
    k_target = max(0.0, 0.4863 * ec_value - 51.76)
    return (n_target, p_target, k_target)


def _npk_hold_window(abs_gap: int, warmup: bool, channel: str) -> int:
    if warmup:
        if abs_gap <= 1:
            return 1
        if abs_gap <= 3:
            return 2
        if abs_gap <= 10:
            return 2 if channel == "N" else 3
        return 1 if channel == "N" else 2
    if abs_gap <= 1:
        return 10 if channel == "N" else 8
    if abs_gap <= 3:
        return 6 if channel == "N" else 5
    if abs_gap <= 10:
        return 3 if channel == "N" else 3
    return 1 if channel == "N" else 1


def _npk_step_limit(abs_gap: int, warmup: bool, channel: str) -> int:
    if channel == "N":
        if abs_gap <= 1:
            return 1
        if abs_gap <= 3:
            return 1 if warmup else 1
        if abs_gap <= 10:
            return 2 if warmup else 1
        return 2
    if abs_gap <= 1:
        return 1
    if abs_gap <= 3:
        return 1 if warmup else 2
    if abs_gap <= 10:
        return 2
    return 2


def sticky_npk_channel(
    current_value: float,
    target_value: float,
    rng: random.Random,
    warmup_remaining: int,
    hold_remaining: int,
    channel: str,
) -> tuple[int, int, int]:
    current = int(round(current_value))
    target = int(round(target_value))
    gap = target - current
    abs_gap = abs(gap)
    warmup = warmup_remaining > 0

    if not warmup and hold_remaining > 0:
        return current, hold_remaining - 1, warmup_remaining

    if abs_gap == 0:
        hold_next = _npk_hold_window(abs_gap, warmup, channel)
        return current, hold_next, warmup_remaining

    if warmup:
        move_prob = 0.58 if abs_gap <= 3 else 0.72 if abs_gap <= 10 else 0.86
    else:
        if abs_gap <= 1:
            move_prob = 0.10
        elif abs_gap <= 3:
            move_prob = 0.22
        elif abs_gap <= 10:
            move_prob = 0.48
        else:
            move_prob = 0.78

    if rng.random() > move_prob:
        hold_next = _npk_hold_window(abs_gap, warmup, channel)
        return current, hold_next, warmup_remaining

    step_limit = _npk_step_limit(abs_gap, warmup, channel)
    if abs_gap <= 1:
        step = 1
    elif abs_gap <= 3:
        step = 1 if rng.random() < 0.82 else min(2, step_limit)
    elif abs_gap <= 10:
        step = 1 if rng.random() < 0.55 else min(2, step_limit)
    else:
        step = 2 if rng.random() < 0.72 else 1

    direction = 1 if gap > 0 else -1
    updated = current + direction * min(step, step_limit)
    hold_next = _npk_hold_window(abs_gap, warmup, channel)
    return updated, hold_next, warmup_remaining


def _ec_hold_window(abs_gap: int, event_strength: int, warmup_remaining: int) -> int:
    if warmup_remaining > 0:
        if abs_gap <= 1:
            return 4
        if abs_gap <= 3:
            return 3
        if abs_gap <= 10:
            return 2
        return 1
    if event_strength >= 2:
        if abs_gap <= 1:
            return 2
        if abs_gap <= 3:
            return 2
        if abs_gap <= 10:
            return 1
        return 1
    if abs_gap <= 1:
        return 10
    if abs_gap <= 3:
        return 8
    if abs_gap <= 10:
        return 4
    return 2


def advance_ec_value(
    current_value: float,
    target_value: float,
    hold_remaining: int,
    rng: random.Random,
    event_strength: int,
    warmup_remaining: int,
) -> tuple[int, int]:
    current = int(round(current_value))
    target = int(round(target_value))
    gap = target - current
    abs_gap = abs(gap)

    if abs_gap == 0:
        return current, _ec_hold_window(abs_gap, event_strength, warmup_remaining)

    if hold_remaining > 0 and event_strength < 2 and warmup_remaining <= 0:
        return current, hold_remaining - 1

    if event_strength <= 0:
        if abs_gap <= 1:
            move_prob = 0.06 if warmup_remaining <= 0 else 0.18
        elif abs_gap <= 3:
            move_prob = 0.12 if warmup_remaining <= 0 else 0.28
        elif abs_gap <= 10:
            move_prob = 0.22 if warmup_remaining <= 0 else 0.40
        else:
            move_prob = 0.34 if warmup_remaining <= 0 else 0.52
        if rng.random() > move_prob:
            return current, _ec_hold_window(abs_gap, event_strength, warmup_remaining)
        step = 1
    elif event_strength == 1:
        if abs_gap <= 1:
            move_prob = 0.26
            step = 1
        elif abs_gap <= 3:
            move_prob = 0.48
            step = 1 if rng.random() < 0.90 else 2
        elif abs_gap <= 10:
            move_prob = 0.72
            step = 2 if rng.random() < 0.60 else 3
        else:
            move_prob = 0.88
            step = min(abs_gap, max(6, int(round(abs_gap * 0.18))))
        if warmup_remaining > 0:
            move_prob = min(0.95, move_prob + 0.10)
        if rng.random() > move_prob:
            return current, _ec_hold_window(abs_gap, event_strength, warmup_remaining)
    else:
        if abs_gap <= 1:
            move_prob = 0.46
            step = 1
        elif abs_gap <= 3:
            move_prob = 0.72
            step = 2 if rng.random() < 0.70 else 3
        elif abs_gap <= 10:
            move_prob = 0.92
            step = min(abs_gap, max(8, int(round(abs_gap * 0.24))))
        else:
            move_prob = 0.98
            step = min(abs_gap, max(12, int(round(abs_gap * 0.32))))
        if warmup_remaining > 0:
            move_prob = min(0.99, move_prob + 0.05)
        if rng.random() > move_prob:
            return current, _ec_hold_window(abs_gap, event_strength, warmup_remaining)

    direction = 1 if gap > 0 else -1
    updated = current + direction * min(step, abs_gap)
    return updated, _ec_hold_window(abs_gap, event_strength, warmup_remaining)


def ph_target(day_profile: dict[str, float]) -> float:
    value = (
        6.18
        + 0.10 * day_profile["week_cycle"]
        + 0.16 * day_profile["biweekly_cycle"]
        + 0.22 * day_profile["monthly_cycle"]
        + 0.08 * day_profile["recovery_bias"]
        - 0.06 * max(0.0, day_profile["weather_regime"])
        + day_profile["ph_offset"]
    )
    return clamp(value, 5.95, 6.88)


def ph_diurnal_adjustment(hour: float) -> float:
    morning_peak = 0.52 * gaussian_peak(hour, 7.2, 2.35)
    evening_peak = 0.22 * gaussian_peak(hour, 20.4, 2.7)
    midday_pull = 0.28 * gaussian_peak(hour, 13.4, 3.0)
    return morning_peak + evening_peak - midday_pull


def hourly_anchor(hour: float, anchors: list[float]) -> float:
    base = int(math.floor(hour)) % 24
    nxt = (base + 1) % 24
    frac = hour - math.floor(hour)
    return anchors[base] * (1.0 - frac) + anchors[nxt] * frac


def season_shift(day_index: float, early_shift: float, late_shift: float, total_days: float = 33.0) -> float:
    progress = clamp(day_index / total_days, 0.0, 1.0)
    return early_shift + (late_shift - early_shift) * progress


def backfill_diurnal_value(
    cfg: AppConfig,
    local_dt: datetime,
    day_profile: dict[str, float],
    anchors: list[float],
    low: float,
    high: float,
    kind: str,
) -> float:
    hour = clock_hour(local_dt)
    rng = random.Random(day_seed(cfg, local_dt, 911 if kind == "hum" else 917))

    if kind == "hum":
        phase_shift = day_profile["sht_hum_phase_shift"] + gaussian_noise(rng, 1.1)
        main_mix = 0.34 + 0.14 * day_profile["hum_curve_mix"]
        side_mix = 0.20 + 0.10 * abs(day_profile["weather_regime"])
        mirror_mix = 0.15 + 0.08 * max(0.0, day_profile["recovery_bias"])
        bias = gaussian_noise(rng, 3.2) + 4.8 * max(0.0, day_profile["weather_regime"]) - 2.9 * day_profile["week_cycle"]
        ripple = (
            8.4 * math.sin(2.0 * math.pi * (hour / 24.0 + gaussian_noise(rng, 0.05)))
            + 4.1 * math.sin(4.0 * math.pi * (hour / 24.0 + gaussian_noise(rng, 0.04)))
            + 1.6 * math.sin(6.0 * math.pi * (hour / 24.0 + gaussian_noise(rng, 0.03)))
        )
        shock_center = 8.5 + abs(gaussian_noise(rng, 2.2, 5.0))
        shock_width = clamp(abs(gaussian_noise(rng, 0.9, 2.7)), 1.3, 4.1)
        shock = gaussian_peak(hour, shock_center, shock_width) * gaussian_noise(rng, 5.2, -1.2)
    else:
        phase_shift = day_profile["sht_temp_phase_shift"] + gaussian_noise(rng, 0.7)
        main_mix = 0.46 + 0.16 * day_profile["temp_curve_mix"]
        side_mix = 0.22 + 0.08 * abs(day_profile["weather_regime"])
        mirror_mix = 0.12 + 0.05 * max(0.0, day_profile["recovery_bias"])
        bias = gaussian_noise(rng, 0.7) + 1.0 * day_profile["week_cycle"] + 0.9 * day_profile["monthly_cycle"] + 0.6 * day_profile["weather_mode"]
        ripple = (
            2.2 * math.sin(2.0 * math.pi * (hour / 24.0 + gaussian_noise(rng, 0.06)))
            + 0.9 * math.sin(4.0 * math.pi * (hour / 24.0 + gaussian_noise(rng, 0.05)))
        )
        shock_center = 9.5 + abs(gaussian_noise(rng, 1.8, 3.8))
        shock_width = clamp(abs(gaussian_noise(rng, 0.8, 2.4)), 1.4, 3.9)
        shock = gaussian_peak(hour, shock_center, shock_width) * gaussian_noise(rng, 2.2, 0.7)

    base_hour = (hour + phase_shift) % 24.0
    mirrored_hour = (24.0 - base_hour + gaussian_noise(rng, 0.7)) % 24.0
    side_hour = (base_hour + clamp(gaussian_noise(rng, 1.3, 5.0), 2.5, 8.0) + 0.7 * day_profile["weather_mode"]) % 24.0
    base_anchor = hourly_anchor(base_hour, anchors)
    side_anchor = hourly_anchor(side_hour, anchors)
    mirror_anchor = hourly_anchor(mirrored_hour, anchors)
    value = base_anchor * main_mix + side_anchor * side_mix + mirror_anchor * mirror_mix + bias + ripple + shock
    return clamp(value, low, high)


def ph_recovery_target(
    cfg: AppConfig,
    local_dt: datetime,
    day_profile: dict[str, float],
    soil_state: MockSoilState,
) -> float:
    base_target = ph_target(day_profile) + ph_diurnal_adjustment(clock_hour(local_dt))
    base_target = clamp(base_target, 5.9, 7.55)
    if soil_state.ph_disturbance_started_at is None:
        return base_target

    elapsed_hours = (local_dt - soil_state.ph_disturbance_started_at).total_seconds() / 3600.0
    if elapsed_hours <= 0.45:
        return 3.0
    if elapsed_hours <= 1.5:
        return 3.0 + ((elapsed_hours - 0.45) / 1.05) * 1.8
    if elapsed_hours <= 24.0:
        return 4.8 + ((elapsed_hours - 1.5) / 22.5) * (5.9 - 4.8)
    if elapsed_hours <= PH_DISTURBANCE_RECOVERY_HOURS:
        return 5.9 + ((elapsed_hours - 24.0) / (PH_DISTURBANCE_RECOVERY_HOURS - 24.0)) * (base_target - 5.9)
    return base_target


def maybe_start_ph_disturbance(cfg: AppConfig, soil_state: MockSoilState, local_dt: datetime) -> None:
    if soil_state.ph_disturbance_started_at is not None:
        return
    day_index = (local_dt.date() - cfg.start.date()).days
    if day_index != PH_DISTURBANCE_DAY_OFFSET:
        return
    if clock_hour(local_dt) < PH_DISTURBANCE_START_HOUR:
        return
    if soil_state.ph_disturbance_dates is None:
        soil_state.ph_disturbance_dates = set()
    date_key = local_dt.strftime("%Y-%m-%d")
    if date_key in soil_state.ph_disturbance_dates:
        return
    soil_state.ph_disturbance_started_at = local_dt
    soil_state.ph_disturbance_dates.add(date_key)


def initial_soil_humidity(day_profile: dict[str, float]) -> float:
    base = 52.0 + 1.6 * day_profile["recovery_bias"] + 1.2 * max(0.0, day_profile["weather_regime"])
    return clamp(base, 48.0, 64.0)


def create_mock_soil_state(cfg: AppConfig) -> MockSoilState:
    profile = build_day_profile(cfg.seed, cfg.start, cfg.start)
    initial_ec = ec_humidity_baseline(initial_soil_humidity(profile))
    target_n, target_p, target_k = nutrient_targets_from_ec(initial_ec)
    return MockSoilState(
        soil_humidity_pct=initial_soil_humidity(profile),
        ec_value=initial_ec,
        nutrient_n=target_n,
        nutrient_p=target_p,
        nutrient_k=target_k,
        soil_ph=ph_target(profile),
        npk_soil_humidity_memory=initial_soil_humidity(profile),
        ec_hold_remaining=0,
        npk_response_delay_remaining=0,
        npk_pending_wetness_boost=0.0,
        ph_disturbance_started_at=None,
        applied_watering_dates=set(),
        applied_fertilizing_dates=set(),
        ph_disturbance_dates=set(),
    )


def telemetry_key(ts_server_sec: int, seq_no: int) -> str:
    return str(ts_server_sec)


def status_event_key(ts_server_sec: int, seq_no: int) -> str:
    return f"{ts_server_sec}_evt{seq_no % 1000:03d}"


def local_date_key(local_dt: datetime) -> str:
    return local_dt.strftime("%Y-%m-%d")


def stable_sha256(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_schedule(cfg: AppConfig, rng: random.Random) -> list[SchedulePoint]:
    out: list[SchedulePoint] = []
    for day_offset in range(cfg.days):
        day_start = cfg.start + timedelta(days=day_offset)
        day_end = day_start + timedelta(days=1)
        current_dt = day_start + timedelta(seconds=rng.randint(cfg.device_jitter_min_sec, cfg.device_jitter_max_sec))
        while current_dt < day_end:
            out.append(SchedulePoint(local_dt=current_dt, is_retry=False))

            # Rare retry bursts create the short recovery cadence seen after failures.
            if rng.random() < 0.0055:
                retry_dt = current_dt
                retry_count = rng.randint(1, 4)
                for _ in range(retry_count):
                    retry_dt = retry_dt + timedelta(seconds=rng.choice((80, 120, 180)) + rng.randint(10, 60))
                    if retry_dt >= day_end:
                        break
                    out.append(SchedulePoint(local_dt=retry_dt, is_retry=True))

            current_dt = current_dt + timedelta(seconds=DEFAULT_WAKE_INTERVAL_SEC + rng.randint(45, 140))

    return sorted(out, key=lambda item: item.local_dt)


def build_packet(
    cfg: AppConfig,
    local_dt: datetime,
    rng: random.Random,
    soil_state: MockSoilState,
) -> dict[str, Any]:
    day_phase = calc_day_fraction(local_dt)
    hour = clock_hour(local_dt)
    day_profile = build_day_profile(cfg.seed, cfg.start, local_dt)
    archive_profile = archive_profile_for(local_dt)
    air_water_factor = irrigation_effect_air(cfg, local_dt)
    soil_water_factor = irrigation_effect_soil(cfg, local_dt)
    fertilizer_factor = fertilizing_effect(cfg, local_dt)
    watering_event = is_watering_event(cfg, soil_state, local_dt)
    fertilizing_event = is_fertilizing_event(cfg, soil_state, local_dt)
    maybe_start_ph_disturbance(cfg, soil_state, local_dt)
    sht_temp_hour = (hour * day_profile["temp_hour_warp"] + day_profile["sht_temp_phase_shift"]) % 24.0
    sht_hum_hour = (hour * day_profile["hum_hour_warp"] + day_profile["sht_hum_phase_shift"]) % 24.0

    if archive_profile is not None:
        archive_temp = interpolate_archive_value(archive_profile.hours, archive_profile.temperature_2m, hour)
        archive_hum = interpolate_archive_value(archive_profile.hours, archive_profile.relative_humidity_2m, hour)
        archive_rain = interpolate_archive_value(archive_profile.hours, archive_profile.rain, hour) or 0.0
        archive_precip = interpolate_archive_value(archive_profile.hours, archive_profile.precipitation, hour) or 0.0
        temp_floor = clamp(archive_profile.temp_min - 0.9 + 0.15 * day_profile["weather_mode"], 21.0, 30.0)
        temp_ceiling = clamp(archive_profile.temp_max + 1.2 + 0.35 * day_profile["temp_day_shock"], 28.0, 39.5)
        hum_floor = clamp(archive_profile.hum_min - 7.0 + 1.4 * day_profile["weather_mode"], 45.0, 86.0)
        hum_ceiling = 99.99
    else:
        if local_dt.date() < MOCK_RECONSTRUCTED_CUTOFF_DATE:
            archive_temp = backfill_diurnal_value(
                cfg=cfg,
                local_dt=local_dt,
                day_profile=day_profile,
                anchors=SHT_TEMP_HOURLY_TARGETS,
                low=20.0,
                high=39.9,
                kind="temp",
            )
            archive_hum = backfill_diurnal_value(
                cfg=cfg,
                local_dt=local_dt,
                day_profile=day_profile,
                anchors=SHT_HUMIDITY_HOURLY_TARGETS,
                low=41.0,
                high=99.99,
                kind="hum",
            )
        else:
            archive_temp = hourly_anchor(sht_temp_hour, SHT_TEMP_HOURLY_TARGETS)
            archive_hum = hourly_anchor(sht_hum_hour, SHT_HUMIDITY_HOURLY_TARGETS)
        archive_rain = 0.0
        archive_precip = 0.0
        temp_floor = day_profile["sht_temp_floor"]
        temp_ceiling = day_profile["sht_temp_ceiling"]
        hum_floor = day_profile["sht_hum_floor"]
        hum_ceiling = day_profile["sht_hum_ceiling"]

    temp_norm = normalized_value(
        archive_temp,
        archive_profile.temp_min if archive_profile is not None else 24.0,
        archive_profile.temp_max if archive_profile is not None else 34.0,
    )
    temp_norm = clamp(
        (temp_norm ** day_profile["sht_temp_gamma"]) * (1.0 - day_profile["temp_curve_mix"])
        + (1.0 - temp_norm) * day_profile["temp_curve_mix"] * 0.45
        + 0.10 * math.sin(2.0 * math.pi * (sht_temp_hour / 24.0 + day_profile["sht_temp_phase_shift"] / 7.0))
        + 0.06 * day_profile["temp_day_shock"] * (1.0 - temp_norm)
        + 0.04 * math.sin(6.0 * math.pi * (day_phase + day_profile["week_cycle"] * 0.15)),
        0.0,
        1.0,
    )

    hum_norm = normalized_value(
        archive_hum,
        archive_profile.hum_min if archive_profile is not None else 60.0,
        archive_profile.hum_max if archive_profile is not None else 99.99,
    )
    hum_norm = clamp(
        (hum_norm ** day_profile["sht_hum_gamma"]) * (1.0 - day_profile["hum_curve_mix"])
        + (1.0 - hum_norm) * day_profile["hum_curve_mix"] * 0.40
        + 0.14 * math.sin(2.0 * math.pi * (sht_hum_hour / 24.0 + day_profile["sht_hum_phase_shift"] / 4.5))
        + 0.07 * math.sin(4.0 * math.pi * (sht_hum_hour / 24.0 + day_profile["sht_hum_phase_shift"] / 6.5))
        - 0.08 * day_profile["humidity_day_shock"] * gaussian_peak(hour, 13.7, 2.6)
        + 0.03 * math.sin(8.0 * math.pi * (day_phase + day_profile["biweekly_cycle"] * 0.11)),
        0.0,
        1.0,
    )

    temp_air = soft_clip(
        temp_floor
        + (temp_ceiling - temp_floor) * temp_norm
        + day_profile["sht_temp_bias"]
        + 0.24 * day_profile["air_temp_offset"]
        + 0.20 * day_profile["biweekly_cycle"]
        + 0.10 * day_profile["monthly_cycle"]
        + 0.45 * day_profile["temp_day_shock"] * gaussian_peak(hour, 14.2 + 0.5 * day_profile["weather_regime"], 2.8)
        - 0.25 * air_water_factor
        - 0.12 * fertilizer_factor
        + gaussian_noise(rng, 0.24),
        temp_floor,
        temp_ceiling,
    )
    if temp_air <= temp_floor + 1e-9:
        temp_air = temp_floor + max(0.06, gaussian_noise(rng, 0.05, 0.12))

    day_rainy = archive_rain > 0.04 or archive_precip > 0.04
    if hour >= 21.0 or hour < 6.5:
        hum_air = 99.99
    else:
        hum_target = (
            hum_floor
            + (hum_ceiling - hum_floor) * hum_norm
            + day_profile["sht_hum_bias"]
            + 0.35 * day_profile["air_hum_offset"] / 4.5
            - 0.52 * max(0.0, day_profile["weather_regime"])
            + 0.92 * air_water_factor
            + 0.22 * fertilizer_factor
            + 0.95 * day_profile["humidity_day_shock"] * gaussian_peak(hour, 11.5 + 1.0 * day_profile["weather_mode"], 3.1)
            - 1.55 * gaussian_peak(hour, 13.4 + 0.7 * day_profile["weather_mode"], 2.05)
            + gaussian_noise(rng, 0.34)
        )
        day_rainy = archive_rain > 0.04 or archive_precip > 0.04
        if watering_event or day_rainy:
            hum_air = 99.99 if hour < 8.2 else soft_clip(hum_target, hum_floor, 99.95, 0.52, 0.22)
        else:
            hum_air = soft_clip(hum_target, hum_floor, 99.95, 0.60, 0.18)
        if hum_air <= hum_floor + 1e-9:
            hum_air = hum_floor + max(0.10, gaussian_noise(rng, 0.12, 0.26))
        hum_air = min(hum_air, 99.95 if not (watering_event and hour < 8.2) and not day_rainy else 99.99)
    soil_temp = clamp(
        hourly_anchor(hour, NPK_TEMP_HOURLY_TARGETS)
        + 0.18 * day_profile["soil_temp_offset"]
        + 0.12 * day_profile["week_cycle"]
        - 0.18 * soil_water_factor
        - 0.10 * fertilizer_factor
        + gaussian_noise(rng, 0.07),
        24.2,
        34.0,
    )

    target_ph = ph_target(day_profile)

    soil_humidity_target = clamp(
        hourly_anchor(hour, NPK_HUMIDITY_HOURLY_TARGETS)
        + season_shift(day_profile["day_index"], -8.0, 8.5)
        + 1.8 * max(0.0, day_profile["weather_regime"])
        + 1.1 * day_profile["recovery_bias"],
        44.0,
        85.6,
    )
    soil_state.soil_humidity_pct += 0.19 * (soil_humidity_target - soil_state.soil_humidity_pct) + gaussian_noise(rng, 0.15)
    if watering_event:
        soil_state.soil_humidity_pct += 9.4 + gaussian_noise(rng, 0.72, 1.8)
        assert soil_state.applied_watering_dates is not None
        soil_state.applied_watering_dates.add(local_dt.strftime("%Y-%m-%d"))
    if fertilizing_event:
        soil_state.soil_humidity_pct += 5.8 + gaussian_noise(rng, 0.62, 1.4)
        assert soil_state.applied_fertilizing_dates is not None
        soil_state.applied_fertilizing_dates.add(local_dt.strftime("%Y-%m-%d"))
    soil_state.soil_humidity_pct = clamp(soil_state.soil_humidity_pct, 44.0, 85.6)

    soil_hum = round(clamp(soil_state.soil_humidity_pct, 44.0, 86.0), 2)
    ph_target_now = ph_recovery_target(cfg, local_dt, day_profile, soil_state)
    if soil_state.ph_disturbance_started_at is not None:
        soil_state.soil_ph = clamp(ph_target_now + gaussian_noise(rng, 0.018), 3.0, 7.6)
    else:
        soil_state.soil_ph += 0.10 * (ph_target_now - soil_state.soil_ph) + gaussian_noise(rng, 0.01)
    ph = round(clamp(soil_state.soil_ph, 3.0, 7.6), 1)

    if watering_event or day_rainy:
        soil_state.npk_response_delay_remaining = max(soil_state.npk_response_delay_remaining, 4)
        soil_state.npk_pending_wetness_boost = clamp(
            soil_state.npk_pending_wetness_boost + 1.20 + 0.30 * air_water_factor + 0.22 * fertilizer_factor,
            0.0,
            2.4,
        )

    npk_mem = soil_state.npk_soil_humidity_memory
    if soil_state.npk_response_delay_remaining > 0:
        memory_pull = 0.03
        memory_boost = 0.0
        soil_state.npk_response_delay_remaining -= 1
        soil_state.npk_pending_wetness_boost = max(0.0, soil_state.npk_pending_wetness_boost * 0.92)
    elif soil_state.npk_pending_wetness_boost > 0.02:
        memory_pull = 0.26
        memory_boost = 5.80 * soil_state.npk_pending_wetness_boost
        npk_mem = max(npk_mem, soil_state.soil_humidity_pct + 6.5 + 1.5 * air_water_factor)
        soil_state.npk_pending_wetness_boost = max(0.0, soil_state.npk_pending_wetness_boost * 0.86)
    elif watering_event or day_rainy:
        memory_pull = 0.34
        memory_boost = 5.20 + 1.10 * air_water_factor + 0.50 * fertilizer_factor + 4.80 * soil_state.npk_pending_wetness_boost
        npk_mem = max(npk_mem, soil_state.soil_humidity_pct + 6.5 + 1.5 * air_water_factor)
        soil_state.npk_pending_wetness_boost = max(0.0, soil_state.npk_pending_wetness_boost * 0.88)
    elif soil_state.soil_humidity_pct >= npk_mem:
        memory_pull = 0.20
        memory_boost = 0.20 * (soil_state.soil_humidity_pct - npk_mem)
    else:
        memory_pull = 0.02
        memory_boost = -0.02 * (npk_mem - soil_state.soil_humidity_pct)
    npk_mem = npk_mem + memory_pull * (soil_state.soil_humidity_pct - npk_mem) + memory_boost
    soil_state.npk_soil_humidity_memory = clamp(npk_mem, 50.5, 86.0)

    ec_humidity_driver = clamp(
        0.72 * soil_state.soil_humidity_pct + 0.28 * soil_state.npk_soil_humidity_memory,
        44.0,
        85.6,
    )
    ec_humidity_base = ec_humidity_baseline(ec_humidity_driver)
    ec_target = ec_humidity_base + 0.08 * day_profile["ec_offset"] + 20.0
    ec_target += 120.0 * soil_state.npk_pending_wetness_boost
    if watering_event:
        ec_target += 10.0 + 3.5 * air_water_factor
    if day_rainy:
        ec_target += 6.0 + 2.0 * air_water_factor
    if fertilizing_event:
        ec_target += 18.0 + 4.0 * fertilizer_factor
    ec_target = clamp(ec_target, 120.0, 900.0)

    event_strength = 0
    if watering_event or day_rainy:
        event_strength += 1
    if fertilizing_event:
        event_strength += 2
    soil_state.ec_value, soil_state.ec_hold_remaining = advance_ec_value(
        soil_state.ec_value,
        ec_target,
        soil_state.ec_hold_remaining,
        rng,
        event_strength,
        soil_state.npk_warmup_remaining,
    )
    ec = int(round(clamp(soil_state.ec_value, 120.0, 900.0)))

    target_n, target_p, target_k = nutrient_targets_from_ec(ec)
    soil_state.nutrient_n = float(target_n)
    soil_state.nutrient_p = float(target_p)
    soil_state.nutrient_k = float(target_k)
    soil_state.npk_hold_n = 0
    soil_state.npk_hold_p = 0
    soil_state.npk_hold_k = 0
    soil_state.npk_warmup_remaining = max(0, soil_state.npk_warmup_remaining - 1)
    soil_state.soil_ph += 0.08 * (target_ph - soil_state.soil_ph) + gaussian_noise(rng, 0.006)

    if fertilizing_event:
        soil_state.soil_ph -= 0.12 + gaussian_noise(rng, 0.008, 0.02)

    n_value = round(clamp(soil_state.nutrient_n, 0.0, MAX_N_PPM), 1)
    p_value = round(clamp(soil_state.nutrient_p, 0.0, MAX_P_PPM), 1)
    k_value = round(clamp(soil_state.nutrient_k, 0.0, MAX_K_PPM), 1)

    rssi = int(clamp(-68 + 6 * math.sin(day_phase * 2 * math.pi) - 4.0 * max(0.0, day_profile["system_stress"]) + rng.uniform(-4, 4), -98, -44))
    ts_device_ms = int(local_dt.timestamp()) * 1000
    npk_retry_roll = rng.random()
    sht_retry_roll = rng.random()
    npk_retry_count = 2 if npk_retry_roll < (0.015 + 0.03 * max(0.0, day_profile["system_stress"])) else (1 if npk_retry_roll < (0.08 + 0.08 * max(0.0, day_profile["system_stress"])) else 0)
    sht_retry_count = 2 if sht_retry_roll < (0.01 + 0.02 * max(0.0, day_profile["system_stress"])) else (1 if sht_retry_roll < (0.06 + 0.06 * max(0.0, day_profile["system_stress"])) else 0)
    npk_sample_valid = rng.random() >= (0.03 + 0.05 * max(0.0, day_profile["system_stress"]))
    sht_sample_valid = rng.random() >= (0.02 + 0.04 * max(0.0, day_profile["system_stress"]))
    npk_duration_ms = 64 + rng.randint(0, 3)
    sht_duration_ms = 22
    npk_error_code = "ok" if npk_sample_valid else "weak_signal"
    sht_error = "ok" if sht_sample_valid else "crc_soft_warning"

    live_npk_values = {
        "temp": round(soil_temp, 2),
        "hum": soil_hum,
        "ph": ph,
        "ec": ec,
        "N": n_value,
        "P": p_value,
        "K": k_value,
    }
    if npk_sample_valid:
        soil_state.last_valid_npk_values = dict(live_npk_values)
    elif soil_state.last_valid_npk_values is not None and rng.random() < 0.65:
        live_npk_values = dict(soil_state.last_valid_npk_values)
    else:
        live_npk_values = {
            "temp": round(soil_temp, 2),
            "hum": soil_hum,
            "ph": ph,
            "ec": ec,
            "N": n_value,
            "P": p_value,
            "K": k_value,
        }

    npk_data = {
        "read_ok": npk_sample_valid,
        "error_code": npk_error_code,
        "error_code_raw": 0 if npk_sample_valid else 12,
        "retry_count": npk_retry_count,
        "timeout_ms": 2000,
        "read_duration_ms": npk_duration_ms,
        "crc_ok": npk_sample_valid,
        "frame_ok": npk_sample_valid,
        "sample_interval_ms": DEFAULT_WAKE_INTERVAL_SEC * 1000,
        "consecutive_fail_count": 0 if npk_sample_valid else 1,
        "recovered_after_fail": False,
        "fail_streak_before_recover": 0,
        "sensor_alarm": False,
        "npk_values_valid": npk_sample_valid,
        "npk_signal_present": npk_sample_valid,
        "temp": live_npk_values["temp"],
        "hum": live_npk_values["hum"],
        "ph": live_npk_values["ph"],
        "ec": live_npk_values["ec"],
        "N": live_npk_values["N"],
        "P": live_npk_values["P"],
        "K": live_npk_values["K"],
    }

    sht30_data = {
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


def build_record(
    cfg: AppConfig,
    payload: dict[str, Any],
    local_dt: datetime,
    seq_no: int,
    rng: random.Random,
    schedule_point: SchedulePoint,
) -> tuple[str, str, dict[str, Any]]:
    is_backfill_period = local_dt.date() < MOCK_RECONSTRUCTED_CUTOFF_DATE
    is_backup_mode = cfg.source_mode == "backup"
    sample_epoch_sec = int(local_dt.timestamp())
    upload_delay_sec = rng.randint(cfg.server_delay_min_sec, cfg.server_delay_max_sec)
    upload_dt = local_dt + timedelta(seconds=upload_delay_sec)
    ts_device_sec = int(clamp(40 + rng.uniform(0, 220), 28, 280))
    ts_server_sec = int(upload_dt.timestamp())
    event_id = telemetry_key(ts_server_sec, seq_no)
    date_key = local_date_key(local_dt)
    sample_time_label = local_dt.strftime("%H:%M")
    upload_time_label = upload_dt.strftime("%H:%M")
    sample_time_local = local_dt.strftime("%Y-%m-%d %H:%M:%S")
    upload_time_local = upload_dt.strftime("%Y-%m-%d %H:%M:%S")
    sample_slot_no = ((local_dt.hour * 60) + local_dt.minute) // 15

    npk_src = payload["packet"]["npk_data"]
    sht_src = payload["packet"]["sht30_data"]
    rssi = payload["packet"]["system_data"]["rssi"]
    day_profile = build_day_profile(cfg.seed, cfg.start, local_dt)
    air_water_factor = irrigation_effect_air(cfg, local_dt)
    soil_water_factor = irrigation_effect_soil(cfg, local_dt)
    heap_free = int(clamp(327800 + rng.uniform(-4200, 6200), 323000, 335500))
    npk_sample_valid = bool(npk_src["npk_values_valid"])
    sht_sample_valid = bool(sht_src["sht_sample_valid"])
    npk_penalty = 0.04 * npk_src["retry_count"] + (0.15 if not npk_sample_valid else 0.0)
    sht_penalty = 0.05 * sht_src["sht_retry_count"] + (0.12 if not sht_sample_valid else 0.0)
    npk_quality = 0.0 if not npk_sample_valid else simulated_quality(0.93, soil_water_factor, day_profile, rng, 0.88, 0.94, penalty=npk_penalty)
    sht_quality = 0.0 if not sht_sample_valid else simulated_quality(0.98, air_water_factor, day_profile, rng, 0.95, 0.985, penalty=sht_penalty)
    npk_status = "ok" if npk_sample_valid else "error"
    sht_status = "ok" if sht_sample_valid else "error"
    packet_payload = dict(payload["packet"])
    packet_payload["system_data"] = {
        "sample_date_key": date_key,
        "sample_epoch_sec": sample_epoch_sec,
        "sample_slot_count_day": 96,
        "sample_slot_no": sample_slot_no,
        "sample_time_reconstructed": True,
        "sample_time_valid": True,
        "transport": "cellular",
    }

    full_read_fail = (not npk_sample_valid) and (not sht_sample_valid) and not is_backfill_period
    if full_read_fail:
        packet_payload = {"system_data": packet_payload["system_data"]}
        npk_error_code = "read_fail"
        sht_error_code = "read_fail"
        npk_duration_ms = 0
        buffered_at_ms = int(clamp(115000 + rng.uniform(-12000, 160000), 45000, 310000))
        replayed_at_ms = int(clamp(95000 + rng.uniform(-10000, 45000), 30000, 190000))
        fallback_used = not is_backfill_period
        was_buffered = not is_backfill_period
        replayed = not is_backfill_period
    else:
        npk_error_code = "" if npk_sample_valid else str(npk_src["error_code"])
        sht_error_code = "" if sht_sample_valid else str(sht_src["sht_error"])
        npk_duration_ms = int(max(npk_src["read_duration_ms"], sht_src["sht_read_elapsed_ms"]))
        buffered_at_ms = None
        replayed_at_ms = None
        fallback_used = False
        was_buffered = False
        replayed = False

    if is_backup_mode:
        random_reconstructed = rng.random() < BACKUP_RECONSTRUCTED_RATE
        random_buffered = rng.random() < BACKUP_BUFFERED_RATE
        random_fallback = rng.random() < BACKUP_FALLBACK_RATE
        sample_time_reconstructed = bool(full_read_fail or schedule_point.is_retry or random_reconstructed or random_buffered or random_fallback)
        was_buffered = was_buffered or schedule_point.is_retry or random_buffered or full_read_fail
        replayed = replayed or schedule_point.is_retry or random_buffered or full_read_fail
        fallback_used = fallback_used or random_fallback or full_read_fail
    elif is_backfill_period:
        sample_time_reconstructed = True
    else:
        sample_time_reconstructed = bool(
            full_read_fail or schedule_point.is_retry or rng.random() < 0.04
        )
        if sample_time_reconstructed:
            was_buffered = was_buffered or schedule_point.is_retry
            replayed = replayed or schedule_point.is_retry
            fallback_used = fallback_used or full_read_fail

    packet_npk = packet_payload.get("npk_data", {}) if isinstance(packet_payload, dict) else {}
    packet_sht = packet_payload.get("sht30_data", {}) if isinstance(packet_payload, dict) else {}
    packet_npk_valid = bool(packet_npk.get("npk_values_valid", False)) and not full_read_fail
    packet_sht_valid = bool(packet_sht.get("sht_sample_valid", False)) and not full_read_fail
    npk_sample_valid = packet_npk_valid
    sht_sample_valid = packet_sht_valid
    npk_status = "ok" if packet_npk_valid else "error"
    sht_status = "ok" if packet_sht_valid else "error"
    npk_quality = 0.0 if not packet_npk_valid else npk_quality
    sht_quality = 0.0 if not packet_sht_valid else sht_quality
    npk_error_code = "read_fail" if full_read_fail else ("" if packet_npk_valid else str(packet_npk.get("error_code") or "weak_signal"))
    sht_error_code = "read_fail" if full_read_fail else ("" if packet_sht_valid else str(packet_sht.get("sht_error") or "crc_soft_warning"))

    record = {
        "schema_version": 1,
        "ts_device": ts_device_sec,
        "ts_sample": sample_epoch_sec,
        "ts_server": ts_server_sec,
        "sample_time_label": sample_time_label,
        "upload_time_label": upload_time_label,
        "sample_time_local": sample_time_local,
        "upload_time_local": upload_time_local,
        "sample_time_reconstructed": sample_time_reconstructed,
        "replayed": replayed,
        "was_buffered": was_buffered,
        "fallback_used": fallback_used,
        "event_meta": {
            "cycle_type": "periodic",
            "wake_reason": "power_on_or_reset" if seq_no == 1 else "timer",
            "duration_ms": npk_duration_ms,
            "sample_time_label": sample_time_label,
            "upload_time_label": upload_time_label,
        },
        "packet": packet_payload,
        "sensors": {
            "npk": {
                "read_ok": bool(npk_src["read_ok"]) if not full_read_fail else False,
                "sample_valid": npk_sample_valid,
                "status": npk_status,
                "quality": npk_quality,
                "ts_sample": ts_device_sec,
                "error_code": npk_error_code,
            },
            "sht30": {
                "read_ok": bool(sht_src["sht_read_ok"]) if not full_read_fail else False,
                "sample_valid": sht_sample_valid,
                "status": sht_status,
                "quality": sht_quality,
                "ts_sample": ts_device_sec,
                "error_code": sht_error_code,
            },
        },
        "modules": {
            "sim": {
                "attached": True,
                "gprs": True,
                "ip": "0.0.0.0",
                "network_status": "online",
                "operator": "45204",
                "registered": True,
                "signal_dbm": rssi,
                "transport": "cellular",
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
                "battery_v": -1,
                "heap_free": heap_free,
                "rssi": rssi,
                "online": True,
            },
            "npk": {
                "status": npk_status,
                "quality": npk_quality,
                "error_code": npk_error_code,
            },
            "sht30": {
                "status": sht_status,
                "quality": sht_quality,
                "error_code": sht_error_code,
            },
            "sim": {
                "status": "online",
                "error_code": "",
            },
        },
    }

    if full_read_fail:
        record["buffer_reason"] = "publish_blocked_transport_not_ready"
        record["buffered_at_ms"] = buffered_at_ms
        record["replayed_at_ms"] = replayed_at_ms

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
            "build_id": "build_Apr 22 2026_15:52:20",
            "last_update_ts": last_ts_server_sec,
        },
        "config": {
            "sampling_mode": "periodic",
            "wake_interval_sec": DEFAULT_WAKE_INTERVAL_SEC,
            "timezone": cfg.timezone_name,
            "telemetry_retention_days": DEFAULT_TELEMETRY_RETENTION_DAYS,
        },
        "network": {
            "attached": True,
            "gprs": True,
            "ip": "0.0.0.0",
            "mac": "",
            "operator": "45204",
            "registered": True,
            "last_rssi": last_rssi,
            "transport": "cellular",
        },
    }


def build_health_overall_doc(last_entry: TelemetryEntry) -> dict[str, Any]:
    overall = dict(last_entry.record["health"]["overall"])
    overall["heartbeat_age_sec"] = 0
    overall["system_state"] = "online"
    overall["state_detail"] = "wake upload ok"
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
    last_ok = not bool(last_entry.record.get("fallback_used"))
    return {
        "last_stage": "direct_upload",
        "last_ok": last_ok,
        "fallback_active": bool(last_entry.record.get("fallback_used")),
        "tls_error": False,
        "last_ref_or_path": last_entry.event_id,
        "last_detail": "ok" if last_ok else "buffered_replay",
        "key_mode": "deterministic_only",
        "counter_ok": total_records if last_ok else max(0, total_records - 1),
        "counter_fail": 0 if last_ok else 1,
        "counter_fallback": 1 if last_entry.record.get("fallback_used") else 0,
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
    expected_device_min_sec = 600
    expected_device_max_sec = 1200
    expected_server_min_sec = 600
    expected_server_max_sec = 1200

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
        "latest_local_iso": latest_record.get("sample_time_local"),
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
    record_packet = last_entry.record.get("packet", {})
    npk_src = record_packet.get("npk_data", {})
    sht_src = record_packet.get("sht30_data", {})
    rssi = last_entry.record["health"]["overall"]["rssi"]
    ts_device_sec = last_entry.record["ts_device"]
    ts_server_sec = last_entry.record["ts_server"]
    npk_sensor = last_entry.record["sensors"]["npk"]
    sht_sensor = last_entry.record["sensors"]["sht30"]

    return {
        "schema_version": 1,
        "meta": {
            "last_event_id": last_entry.event_id,
            "last_seen_ts": ts_device_sec,
            "uptime_sec": ts_device_sec + 7,
            "boot_reason": "timer",
            "last_sync_ts": ts_server_sec,
            "telemetry_debug": telemetry_debug,
            "telemetry_channel": telemetry_channel,
        },
        "sensors": {
            "npk": {
                "n": npk_src.get("N", 0),
                "p": npk_src.get("P", 0),
                "k": npk_src.get("K", 0),
                "ec": npk_src.get("ec", 0),
                "ph": npk_src.get("ph", 0),
                "temperature_c": npk_src.get("temp", 0),
                "humidity_percent": npk_src.get("hum", 0),
                "ts_sample": ts_device_sec,
                "read_ok": bool(npk_src.get("read_ok", False)),
                "sample_valid": bool(npk_src.get("npk_values_valid", False)),
                "status": npk_sensor["status"],
                "quality": npk_sensor["quality"],
                "error_code": npk_sensor["error_code"],
            },
            "sht30": {
                "temperature_c": sht_src.get("sht_temp_c", 0),
                "humidity_percent": sht_src.get("sht_hum_pct", 0),
                "ts_sample": ts_device_sec,
                "read_ok": bool(sht_src.get("sht_read_ok", False)),
                "sample_valid": bool(sht_src.get("sht_sample_valid", False)),
                "retry_count": sht_src.get("sht_retry_count", 0),
                "read_elapsed_ms": sht_src.get("sht_read_elapsed_ms", 0),
                "invalid_streak": sht_src.get("sht_invalid_streak", 0),
                "status": sht_sensor["status"],
                "quality": sht_sensor["quality"],
                "error_code": sht_sensor["error_code"],
            },
        },
        "modules": {
            "sim": {
                "attached": True,
                "gprs": True,
                "ip": "0.0.0.0",
                "operator": "45204",
                "registered": True,
                "signal_dbm": rssi,
                "network_status": "online",
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
                    "status": "online",
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
    soil_state = create_mock_soil_state(cfg)
    replay_payloads = load_backup_replay_payloads() if cfg.source_mode == "backup" else []
    replay_state = BackupReplayState()
    if cfg.source_mode == "backup" and not replay_payloads:
        print("warning: backup replay source not found; falling back to generated mode", file=sys.stderr)
        cfg.source_mode = "generated"

    telemetry_entries: list[TelemetryEntry] = []
    telemetry_writes: list[WriteOp] = []
    per_day_counts: dict[str, int] = {}

    for idx, point in enumerate(schedule, start=1):
        local_dt = point.local_dt
        if cfg.source_mode == "backup" and replay_payloads:
            replay_index = (idx - 1) % len(replay_payloads)
            replay_cycle = (idx - 1) // len(replay_payloads)
            payload = transform_backup_payload(cfg, replay_payloads[replay_index], local_dt, replay_state, replay_cycle)
        else:
            payload = build_packet(cfg, local_dt, rng, soil_state)
        date_key, event_id, record = build_record(cfg, payload, local_dt, idx, rng, point)
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
    print(f"source mode: {cfg.source_mode}")
    print(f"local start: {schedule[0].local_dt.isoformat()}")
    print(f"local end:   {schedule[-1].local_dt.isoformat()}")
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
