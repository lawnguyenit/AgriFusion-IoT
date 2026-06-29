from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from Backend.Benchmark.common.paths import BENCHMARK_DATASETS_ROOT
from Backend.Config.IO.io_csv import write_csv
from Backend.Config.paths import BACKEND_PATHS
from Backend.Config.storage import read_json, write_json
from Backend.Core.layer2.timeseries import add_datetime_columns


LOCAL_TIMEZONE = "Asia/Ho_Chi_Minh"
SYSTEM_RESET_PH_THRESHOLD = 3.05
POST_RESET_WARMUP_HOURS = 6.0
POST_RESET_WARMUP_PH_MAX = 5.2
TELEMETRY_GAP_MINUTES = 60.0
DEBUG_TIGHT_GAP_MINUTES = 12.0
LOW_EC_THRESHOLD = 220.0
LOW_N_THRESHOLD = 5.0
LOW_P_THRESHOLD = 60.0
LOW_K_THRESHOLD = 60.0
MORNING_IRRIGATION_START_HOUR = 5.0
MORNING_IRRIGATION_END_HOUR = 9.0
SOIL_HUMIDITY_RISE_THRESHOLD = 5.0
AIR_HUMIDITY_RAIN_RISE_THRESHOLD = 8.0
EC_RECOVERY_RISE_THRESHOLD = 50.0
POST_REPLUG_RECOVERY_LOOKBACK_HOURS = 36.0
HEAT_EPISODE_AIR_TEMP_MIN = 35.0
DRY_SOIL_EPISODE_HUMIDITY_MAX = 55.0
EPISODE_MAX_GAP_MINUTES = 30.0
EPISODE_MIN_ROWS = 3
EPISODE_MIN_DURATION_MINUTES = 45.0
FERTILIZER_EC_DELTA_MIN = 80.0
FERTILIZER_N_DELTA_MIN = 15.0
FERTILIZER_P_DELTA_MIN = 35.0
FERTILIZER_K_DELTA_MIN = 35.0

ALIGNMENT_SENSOR_COLUMNS = [
    "soil_temp",
    "soil_humidity",
    "air_temp",
    "air_humidity",
    "EC",
    "pH",
    "N",
    "P",
    "K",
]

EVENT_FLAG_COLUMNS = [
    "event_system_reset",
    "event_telemetry_gap_since_prev",
    "event_telemetry_gap_to_next",
    "event_post_reset_warmup",
    "event_sensor_missing_row",
    "event_npk_sensor_fault",
    "event_sht30_sensor_fault",
    "event_debug_sensor_pull_candidate",
    "event_ec_npk_replug_low_candidate",
    "event_post_replug_recovery_candidate",
    "event_morning_irrigation_candidate",
    "event_rain_weather_candidate",
    "event_fertilizer_context_candidate",
    "event_ec_npk_anomaly",
    "event_heat_episode",
    "event_dry_soil_episode",
]

OUTPUT_COLUMNS = [
    "timestamp",
    "sample_time_local",
    "sample_time_reconstructed",
    "gap_minutes_since_prev",
    "gap_minutes_to_next",
    "soil_temp",
    "soil_humidity",
    "air_temp",
    "air_humidity",
    "EC",
    "pH",
    "N",
    "P",
    "K",
    "soil_humidity_delta",
    "air_humidity_delta",
    "EC_delta",
    "pH_delta",
    "N_delta",
    "P_delta",
    "K_delta",
    *EVENT_FLAG_COLUMNS,
    "event_primary",
    "big_label",
]


@dataclass(frozen=True)
class RawTelemetryMeta:
    ts_server: int
    sample_time_local: str
    sample_time_reconstructed: bool
    wake_reason: str
    npk_status: str
    npk_sample_valid: bool
    npk_error_code: str
    npk_values_valid: bool
    npk_signal_present: bool
    recovered_after_fail: bool
    sht30_status: str
    sht30_sample_valid: bool
    sht30_error_code: str


@dataclass(frozen=True)
class RealEventLabelingResult:
    aligned_csv: Path
    output_csv: Path
    report_path: Path
    row_count: int
    lookup_matched_rows: int
    big_label_counts: dict[str, int]
    event_counts: dict[str, int]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _unwrap_raw_record(payload: Any) -> dict[str, Any]:
    data = _as_dict(payload)
    record = data.get("record")
    return _as_dict(record) if isinstance(record, dict) else data


def _parse_local_datetime(value: str | None) -> pd.Timestamp:
    if not value:
        return pd.NaT
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return pd.NaT
    if getattr(parsed, "tzinfo", None) is None:
        return parsed.tz_localize(LOCAL_TIMEZONE)
    return parsed.tz_convert(LOCAL_TIMEZONE)


def _format_local_datetime(value: pd.Timestamp) -> str:
    if pd.isna(value):
        return ""
    converted = value.tz_convert(LOCAL_TIMEZONE) if value.tzinfo is not None else value
    return converted.strftime("%Y-%m-%d %H:%M:%S")


def _extract_raw_meta(payload: Any) -> RawTelemetryMeta | None:
    raw = _unwrap_raw_record(payload)
    ts_server = raw.get("ts_server")
    if ts_server is None:
        return None

    event_meta = _as_dict(raw.get("event_meta"))
    sensors = _as_dict(raw.get("sensors"))
    packet = _as_dict(raw.get("packet"))
    packet_npk = _as_dict(packet.get("npk_data"))
    packet_sht30 = _as_dict(packet.get("sht30_data"))
    packet_system = _as_dict(packet.get("system_data"))
    sensor_npk = _as_dict(sensors.get("npk"))
    sensor_sht30 = _as_dict(sensors.get("sht30"))

    sample_time_reconstructed = bool(
        raw.get("sample_time_reconstructed")
        or packet_system.get("sample_time_reconstructed")
    )

    return RawTelemetryMeta(
        ts_server=int(ts_server),
        sample_time_local=str(raw.get("sample_time_local") or ""),
        sample_time_reconstructed=sample_time_reconstructed,
        wake_reason=str(event_meta.get("wake_reason") or ""),
        npk_status=str(sensor_npk.get("status") or ""),
        npk_sample_valid=bool(sensor_npk.get("sample_valid", True)),
        npk_error_code=str(sensor_npk.get("error_code") or packet_npk.get("error_code") or ""),
        npk_values_valid=bool(packet_npk.get("npk_values_valid", True)),
        npk_signal_present=bool(packet_npk.get("npk_signal_present", True)),
        recovered_after_fail=bool(packet_npk.get("recovered_after_fail", False)),
        sht30_status=str(sensor_sht30.get("status") or ""),
        sht30_sample_valid=bool(sensor_sht30.get("sample_valid", True)),
        sht30_error_code=str(sensor_sht30.get("error_code") or packet_sht30.get("sht_error") or ""),
    )


def _load_firebase_time_index() -> dict[int, RawTelemetryMeta]:
    firebase_root = BACKEND_PATHS.layer0_dir / "Firebase_data"
    history_root = firebase_root / "history"
    latest_path = firebase_root / "new_raw" / "latest.json"

    index: dict[int, RawTelemetryMeta] = {}
    for json_path in sorted(history_root.rglob("*.json")):
        meta = _extract_raw_meta(read_json(json_path, default={}))
        if meta is not None:
            index[meta.ts_server] = meta

    latest_meta = _extract_raw_meta(read_json(latest_path, default={}))
    if latest_meta is not None:
        index[latest_meta.ts_server] = latest_meta
    return index


def _load_alignment_csv(csv_path: Path) -> pd.DataFrame:
    frame = pd.read_csv(csv_path)
    required_columns = ["timestamp", *ALIGNMENT_SENSOR_COLUMNS]
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Aligned CSV is missing required columns {missing}: {csv_path}")
    return add_datetime_columns(frame)


def _recent_true_within_hours(
    flag_series: pd.Series,
    timestamp_series: pd.Series,
    lookback_hours: float,
) -> pd.Series:
    output: list[int] = []
    last_true_time: pd.Timestamp | None = None
    lookback = pd.Timedelta(hours=float(lookback_hours))

    for is_true, timestamp in zip(flag_series.fillna(0).astype(int), pd.to_datetime(timestamp_series), strict=False):
        recent = 0
        if last_true_time is not None and timestamp - last_true_time <= lookback:
            recent = 1
        output.append(recent)
        if int(is_true) == 1:
            last_true_time = timestamp
    return pd.Series(output, index=flag_series.index, dtype=int)


def _mark_episode(
    condition: pd.Series,
    time_series: pd.Series,
    max_gap_minutes: float = EPISODE_MAX_GAP_MINUTES,
    min_rows: int = EPISODE_MIN_ROWS,
    min_duration_minutes: float = EPISODE_MIN_DURATION_MINUTES,
) -> pd.Series:
    flag = pd.Series(0, index=condition.index, dtype=int)
    active_indices = condition[condition.fillna(False)].index.tolist()
    if not active_indices:
        return flag

    groups: list[list[int]] = []
    current_group = [active_indices[0]]
    for idx in active_indices[1:]:
        previous_idx = current_group[-1]
        gap_minutes = (time_series.iloc[idx] - time_series.iloc[previous_idx]).total_seconds() / 60.0
        if gap_minutes <= max_gap_minutes:
            current_group.append(idx)
        else:
            groups.append(current_group)
            current_group = [idx]
    groups.append(current_group)

    for group in groups:
        duration_minutes = (
            (time_series.iloc[group[-1]] - time_series.iloc[group[0]]).total_seconds() / 60.0
            if len(group) > 1
            else 0.0
        )
        if len(group) >= min_rows or duration_minutes >= min_duration_minutes:
            flag.loc[group] = 1
    return flag


def _build_primary_event(row: pd.Series) -> str:
    priority = [
        "event_system_reset",
        "event_post_reset_warmup",
        "event_telemetry_gap_since_prev",
        "event_telemetry_gap_to_next",
        "event_sensor_missing_row",
        "event_npk_sensor_fault",
        "event_sht30_sensor_fault",
        "event_ec_npk_replug_low_candidate",
        "event_ec_npk_anomaly",
        "event_debug_sensor_pull_candidate",
        "event_post_replug_recovery_candidate",
        "event_morning_irrigation_candidate",
        "event_fertilizer_context_candidate",
        "event_rain_weather_candidate",
        "event_heat_episode",
        "event_dry_soil_episode",
    ]
    for column in priority:
        if int(row.get(column, 0)) == 1:
            return column.removeprefix("event_")
    return "none"


def _build_big_label(row: pd.Series) -> str:
    primary = str(row.get("event_primary") or "none")
    if primary in {
        "system_reset",
        "telemetry_gap_since_prev",
        "telemetry_gap_to_next",
        "post_reset_warmup",
        "debug_sensor_pull_candidate",
    }:
        return "system_timing"
    if primary in {
        "sensor_missing_row",
        "npk_sensor_fault",
        "sht30_sensor_fault",
        "ec_npk_replug_low_candidate",
        "ec_npk_anomaly",
    }:
        return "sensor_fault_anomaly"
    if primary in {
        "morning_irrigation_candidate",
        "fertilizer_context_candidate",
        "post_replug_recovery_candidate",
    }:
        return "intervention_context"
    if primary == "rain_weather_candidate":
        return "weather_context"
    if primary in {"heat_episode", "dry_soil_episode"}:
        return "stress_context"
    return "none"


def build_real_event_labels(
    *,
    aligned_csv: Path | None = None,
    output_csv: Path | None = None,
) -> RealEventLabelingResult:
    source_csv = (aligned_csv or BENCHMARK_DATASETS_ROOT / "benchmark_input_aligned.csv").resolve()
    target_csv = (output_csv or BENCHMARK_DATASETS_ROOT / "benchmark_input_labeled.csv").resolve()
    report_path = target_csv.parent / "benchmark_labeling_report.json"

    aligned = _load_alignment_csv(source_csv)
    firebase_index = _load_firebase_time_index()

    output = aligned.copy()
    output["raw_meta"] = output["timestamp"].map(lambda value: firebase_index.get(int(value)))
    output["sample_time_local"] = output["raw_meta"].map(lambda meta: "" if meta is None else meta.sample_time_local)
    output["sample_time_reconstructed"] = output["raw_meta"].map(
        lambda meta: False if meta is None else meta.sample_time_reconstructed
    )
    output["wake_reason"] = output["raw_meta"].map(lambda meta: "" if meta is None else meta.wake_reason)
    output["npk_status_raw"] = output["raw_meta"].map(lambda meta: "" if meta is None else meta.npk_status)
    output["npk_error_code_raw"] = output["raw_meta"].map(lambda meta: "" if meta is None else meta.npk_error_code)
    output["npk_sample_valid_raw"] = output["raw_meta"].map(lambda meta: True if meta is None else meta.npk_sample_valid)
    output["npk_values_valid_raw"] = output["raw_meta"].map(lambda meta: True if meta is None else meta.npk_values_valid)
    output["npk_signal_present_raw"] = output["raw_meta"].map(lambda meta: True if meta is None else meta.npk_signal_present)
    output["sht30_status_raw"] = output["raw_meta"].map(lambda meta: "" if meta is None else meta.sht30_status)
    output["sht30_error_code_raw"] = output["raw_meta"].map(lambda meta: "" if meta is None else meta.sht30_error_code)
    output["sht30_sample_valid_raw"] = output["raw_meta"].map(lambda meta: True if meta is None else meta.sht30_sample_valid)
    output["recovered_after_fail_raw"] = output["raw_meta"].map(
        lambda meta: False if meta is None else meta.recovered_after_fail
    )

    fallback_local = output["timestamp_dt"].dt.tz_convert(LOCAL_TIMEZONE)
    sample_dt = pd.Series(
        pd.DatetimeIndex(output["sample_time_local"].map(_parse_local_datetime)),
        index=output.index,
    )
    sample_dt = sample_dt.where(sample_dt.notna(), fallback_local)
    output["sample_time_local"] = sample_dt.map(_format_local_datetime)
    output["sample_dt_local"] = sample_dt
    output["sample_local_hour"] = sample_dt.dt.hour + sample_dt.dt.minute.div(60.0)

    output["gap_minutes_since_prev"] = output["sample_dt_local"].diff().dt.total_seconds().div(60.0)
    output["gap_minutes_to_next"] = (
        output["sample_dt_local"].shift(-1).sub(output["sample_dt_local"]).dt.total_seconds().div(60.0)
    )

    for column in ["soil_humidity", "air_humidity", "EC", "pH", "N", "P", "K"]:
        output[f"{column}_delta"] = pd.to_numeric(output[column], errors="coerce").diff()

    output["event_system_reset"] = (
        pd.to_numeric(output["pH"], errors="coerce").fillna(999.0) <= SYSTEM_RESET_PH_THRESHOLD
    ).astype(int)
    output["event_telemetry_gap_since_prev"] = (
        output["gap_minutes_since_prev"].fillna(0.0) > TELEMETRY_GAP_MINUTES
    ).astype(int)
    output["event_telemetry_gap_to_next"] = (
        output["gap_minutes_to_next"].fillna(0.0) > TELEMETRY_GAP_MINUTES
    ).astype(int)

    output["recent_reset_within_6h"] = _recent_true_within_hours(
        output["event_system_reset"],
        output["sample_dt_local"],
        POST_RESET_WARMUP_HOURS,
    )
    output["event_post_reset_warmup"] = (
        (output["recent_reset_within_6h"] == 1)
        & (pd.to_numeric(output["pH"], errors="coerce").fillna(999.0) <= POST_RESET_WARMUP_PH_MAX)
    ).astype(int)

    output["event_sensor_missing_row"] = output[ALIGNMENT_SENSOR_COLUMNS].isna().any(axis=1).astype(int)
    output["event_npk_sensor_fault"] = (
        (pd.to_numeric(output["N"], errors="coerce").fillna(9999.0) <= 0.0)
        | (pd.to_numeric(output["P"], errors="coerce").fillna(9999.0) <= 0.0)
        | (pd.to_numeric(output["K"], errors="coerce").fillna(9999.0) <= 0.0)
        | (output["npk_sample_valid_raw"].astype(bool) == False)
        | (output["npk_values_valid_raw"].astype(bool) == False)
        | (output["npk_status_raw"] == "error")
    ).astype(int)
    output["event_sht30_sensor_fault"] = (
        output[["air_temp", "air_humidity"]].isna().any(axis=1)
        | (output["sht30_sample_valid_raw"].astype(bool) == False)
        | (output["sht30_status_raw"] == "error")
    ).astype(int)
    output["event_debug_sensor_pull_candidate"] = (
        output["gap_minutes_since_prev"].fillna(999.0).between(0.0, DEBUG_TIGHT_GAP_MINUTES, inclusive="neither")
        | output["gap_minutes_to_next"].fillna(999.0).between(0.0, DEBUG_TIGHT_GAP_MINUTES, inclusive="neither")
    ).astype(int)
    output["event_ec_npk_replug_low_candidate"] = (
        (pd.to_numeric(output["EC"], errors="coerce").fillna(9999.0) <= LOW_EC_THRESHOLD)
        & (pd.to_numeric(output["N"], errors="coerce").fillna(9999.0) <= LOW_N_THRESHOLD)
        & (pd.to_numeric(output["P"], errors="coerce").fillna(9999.0) <= LOW_P_THRESHOLD)
        & (pd.to_numeric(output["K"], errors="coerce").fillna(9999.0) <= LOW_K_THRESHOLD)
    ).astype(int)

    strong_soil_rewet = output["soil_humidity_delta"].fillna(0.0) >= SOIL_HUMIDITY_RISE_THRESHOLD
    air_humidity_spiking = output["air_humidity_delta"].fillna(0.0) >= AIR_HUMIDITY_RAIN_RISE_THRESHOLD
    morning_window = output["sample_local_hour"].between(
        MORNING_IRRIGATION_START_HOUR,
        MORNING_IRRIGATION_END_HOUR,
    )

    output["recent_ec_npk_replug_low_36h"] = _recent_true_within_hours(
        output["event_ec_npk_replug_low_candidate"],
        output["sample_dt_local"],
        POST_REPLUG_RECOVERY_LOOKBACK_HOURS,
    )
    output["event_post_replug_recovery_candidate"] = (
        (output["recent_ec_npk_replug_low_36h"] == 1)
        & strong_soil_rewet
        & (output["EC_delta"].fillna(0.0) >= EC_RECOVERY_RISE_THRESHOLD)
        & (output["event_system_reset"] == 0)
    ).astype(int)
    output["event_morning_irrigation_candidate"] = (
        morning_window
        & strong_soil_rewet
        & (air_humidity_spiking == False)
        & (output["event_system_reset"] == 0)
        & (output["event_ec_npk_replug_low_candidate"] == 0)
    ).astype(int)
    output["event_rain_weather_candidate"] = (
        strong_soil_rewet
        & (air_humidity_spiking | (~morning_window))
        & (output["event_system_reset"] == 0)
        & (output["event_ec_npk_replug_low_candidate"] == 0)
        & (output["event_morning_irrigation_candidate"] == 0)
    ).astype(int)

    nutrient_jump = (
        (output["EC_delta"].fillna(0.0) >= FERTILIZER_EC_DELTA_MIN)
        & (
            (output["N_delta"].fillna(0.0) >= FERTILIZER_N_DELTA_MIN)
            | (output["P_delta"].fillna(0.0) >= FERTILIZER_P_DELTA_MIN)
            | (output["K_delta"].fillna(0.0) >= FERTILIZER_K_DELTA_MIN)
        )
    )
    output["event_fertilizer_context_candidate"] = (
        nutrient_jump
        & (output["event_system_reset"] == 0)
        & (output["event_ec_npk_replug_low_candidate"] == 0)
        & (output["event_npk_sensor_fault"] == 0)
    ).astype(int)

    output["event_ec_npk_anomaly"] = (
        (output["event_ec_npk_replug_low_candidate"] == 1)
        | (output["event_npk_sensor_fault"] == 1)
    ).astype(int)
    output["event_heat_episode"] = _mark_episode(
        pd.to_numeric(output["air_temp"], errors="coerce").fillna(-999.0) >= HEAT_EPISODE_AIR_TEMP_MIN,
        output["sample_dt_local"],
    )
    output["event_dry_soil_episode"] = _mark_episode(
        pd.to_numeric(output["soil_humidity"], errors="coerce").fillna(999.0) <= DRY_SOIL_EPISODE_HUMIDITY_MAX,
        output["sample_dt_local"],
    )

    output["event_primary"] = output.apply(_build_primary_event, axis=1)
    output["big_label"] = output.apply(_build_big_label, axis=1)

    export_frame = output[OUTPUT_COLUMNS].copy()
    write_csv(export_frame, target_csv)

    event_counts = {
        column: int(export_frame[column].fillna(0).astype(int).sum())
        for column in EVENT_FLAG_COLUMNS
    }
    big_label_counts = {
        str(label): int(count)
        for label, count in export_frame["big_label"].fillna("none").astype(str).value_counts(dropna=False).items()
    }
    lookup_matched_rows = int(output["raw_meta"].notna().sum())
    report_payload = {
        "generated_at_utc": _utc_now_iso(),
        "stage_name": "real_event_labeling",
        "aligned_csv": str(source_csv),
        "output_csv": str(target_csv),
        "lookup_root": str(BACKEND_PATHS.layer0_dir / "Firebase_data"),
        "row_count": int(len(export_frame)),
        "lookup_matched_rows": lookup_matched_rows,
        "lookup_missing_rows": int(len(export_frame) - lookup_matched_rows),
        "big_label_counts": big_label_counts,
        "event_counts": event_counts,
        "output_columns": list(export_frame.columns),
        "notes": [
            "benchmark_input_labeled.csv is the real-data label source of truth for downstream benchmarks.",
            "train-facing single-window and multi-window exports only keep big_label in addition to their feature columns.",
        ],
    }
    write_json(report_path, report_payload)

    return RealEventLabelingResult(
        aligned_csv=source_csv,
        output_csv=target_csv,
        report_path=report_path,
        row_count=int(len(export_frame)),
        lookup_matched_rows=lookup_matched_rows,
        big_label_counts=big_label_counts,
        event_counts=event_counts,
    )
