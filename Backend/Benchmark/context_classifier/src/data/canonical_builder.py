from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from Backend.Benchmark.context_classifier.src.data.contracts import BASE_SENSOR_COLUMNS, CANONICAL_COLUMNS
from Backend.Benchmark.context_classifier.src.data.label_schemes import get_label_scheme


def _json_safe_scalar(value: object) -> object:
    if pd.isna(value):
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _json_safe_key(value: object) -> str:
    normalized = _json_safe_scalar(value)
    return "null" if normalized is None else str(normalized)


def _value_counts_to_json_dict(series: pd.Series) -> dict[str, int]:
    counts = series.value_counts(dropna=False)
    return {
        _json_safe_key(label): int(count)
        for label, count in counts.items()
    }


def _records_to_json_safe(records: list[dict[str, object]]) -> list[dict[str, object]]:
    safe_records: list[dict[str, object]] = []
    for record in records:
        safe_records.append(
            {
                str(key): _json_safe_scalar(value)
                for key, value in record.items()
            }
        )
    return safe_records


def _estimate_loss_steps_from_minutes(value: object, fallback_minutes: float = 16.0) -> int:
    if pd.isna(value):
        return 0
    try:
        minutes = float(value)
    except (TypeError, ValueError):
        return 0
    if minutes <= fallback_minutes * 1.5:
        return 0
    return max(int(round(minutes / fallback_minutes)) - 1, 1)


def _local_dt_from_epoch(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, unit="s", utc=True).dt.tz_convert("Asia/Ho_Chi_Minh")


def _night_overlap(start_ts: int, end_ts: int) -> bool:
    if pd.isna(start_ts) or pd.isna(end_ts):
        return False
    start = pd.Timestamp(start_ts, unit="s", tz="UTC").tz_convert("Asia/Ho_Chi_Minh")
    end = pd.Timestamp(end_ts, unit="s", tz="UTC").tz_convert("Asia/Ho_Chi_Minh")
    if end < start:
        start, end = end, start
    probe = start.floor("h")
    while probe <= end.ceil("h"):
        if probe.hour >= 18 or probe.hour <= 5:
            return True
        probe += pd.Timedelta(hours=1)
    return False


def build_real_canonical(real_event_csv: Path, label_scheme_name: str) -> pd.DataFrame:
    label_scheme = get_label_scheme(label_scheme_name)
    df = pd.read_csv(real_event_csv)
    result = pd.DataFrame()
    result["timestamp"] = df["timestamp"]
    for column in BASE_SENSOR_COLUMNS:
        result[column] = df[column]
    result["context_label_raw"] = df["big_label"].fillna("none").astype(str)
    result["context_label"] = result["context_label_raw"].map(label_scheme.real_label_map).fillna("normal_context")
    result["split_name"] = pd.NA
    result["data_origin"] = "real"
    result["is_synthetic"] = 0
    result["record_present"] = 1
    result["timeline_state"] = "observed"
    result["episode_id"] = pd.NA
    result["phase_name"] = "observed"
    result["scenario_intensity"] = 0.0
    result["scenario_progress"] = 0.0
    result["effect_strength"] = 0.0
    result["source_reference"] = "flb_input_with_events.csv"
    result["event_primary"] = df.get("event_primary", pd.Series(["none"] * len(df)))
    result["event_labels"] = df.get("event_labels", pd.Series([pd.NA] * len(df)))

    loss_steps_prev = df.get("gap_minutes_since_prev", pd.Series([0.0] * len(df))).apply(_estimate_loss_steps_from_minutes)
    loss_steps_next = df.get("gap_minutes_to_next", pd.Series([0.0] * len(df))).apply(_estimate_loss_steps_from_minutes)
    telemetry_gap_prev = df.get("event_telemetry_gap_since_prev", pd.Series([0] * len(df))).fillna(0).astype(int)
    telemetry_gap_next = df.get("event_telemetry_gap_to_next", pd.Series([0] * len(df))).fillna(0).astype(int)
    packet_like = ((telemetry_gap_prev > 0) | (telemetry_gap_next > 0) | (result["context_label"] == "packet_loss_outage")).astype(int)
    local_dt = pd.to_datetime(df.get("sample_time_local"), errors="coerce")
    prev_dt = local_dt - pd.to_timedelta(df.get("gap_minutes_since_prev", pd.Series([0.0] * len(df))).fillna(0.0), unit="m")
    current_hour = local_dt.dt.hour.fillna(-1).astype(int)
    prev_hour = prev_dt.dt.hour.fillna(-1).astype(int)
    sunrise_recovery = (
        (packet_like > 0)
        & (loss_steps_prev > 0)
        & current_hour.between(6, 9)
        & ((prev_hour <= 5) | (prev_hour >= 18))
    ).astype(int)
    nighttime_outage = []
    timestamps = pd.to_numeric(df["timestamp"], errors="coerce")
    for current_ts, gap_minutes, packet_flag in zip(timestamps, df.get("gap_minutes_since_prev", pd.Series([0.0] * len(df))).fillna(0.0), packet_like):
        if not packet_flag or pd.isna(current_ts):
            nighttime_outage.append(0)
            continue
        prev_ts = int(float(current_ts) - float(gap_minutes) * 60.0)
        nighttime_outage.append(int(_night_overlap(prev_ts, int(float(current_ts)))))

    result["packet_loss_flag"] = packet_like
    result["loss_packet_count"] = (loss_steps_prev + loss_steps_next).where(packet_like > 0, 0)
    result.loc[(packet_like > 0) & (result["loss_packet_count"] <= 0), "loss_packet_count"] = 1
    result["outage_duration_steps"] = result["loss_packet_count"].where(result["loss_packet_count"] > 0, 0)
    result["time_since_last_valid_step"] = loss_steps_prev.where(packet_like > 0, 0)
    result["recovery_step_index"] = (loss_steps_prev > 0).astype(int)
    result["nighttime_outage_flag"] = nighttime_outage
    result["sunrise_recovery_flag"] = sunrise_recovery
    result["suspected_cause"] = "none"
    result["cause_confidence"] = 0.0
    power_mask = (packet_like > 0) & ((result["sunrise_recovery_flag"] > 0) | ((result["nighttime_outage_flag"] > 0) & (result["loss_packet_count"] >= 3)))
    network_mask = (packet_like > 0) & (~power_mask) & (result["loss_packet_count"] > 0) & (result["nighttime_outage_flag"] == 0)
    unknown_mask = (packet_like > 0) & (~power_mask) & (~network_mask)
    result.loc[power_mask, "suspected_cause"] = "possible_power_loss"
    result.loc[power_mask, "cause_confidence"] = 0.85
    result.loc[network_mask, "suspected_cause"] = "possible_network_issue"
    result.loc[network_mask, "cause_confidence"] = 0.55
    result.loc[unknown_mask, "suspected_cause"] = "unknown"
    result.loc[unknown_mask, "cause_confidence"] = 0.35
    return result[CANONICAL_COLUMNS].sort_values("timestamp").reset_index(drop=True)


def build_synthetic_canonical(synthetic_gap_aware_csv: Path, label_scheme_name: str) -> pd.DataFrame:
    label_scheme = get_label_scheme(label_scheme_name)
    df = pd.read_csv(synthetic_gap_aware_csv)
    result = pd.DataFrame()
    result["timestamp"] = df["timestamp"]
    for column in BASE_SENSOR_COLUMNS:
        result[column] = df[column]
    result["context_label_raw"] = df["scenario_label"].fillna("normal_context").astype(str)
    result["context_label"] = result["context_label_raw"].map(label_scheme.synthetic_label_map).fillna(result["context_label_raw"])
    result["split_name"] = "train"
    result["data_origin"] = "synthetic"
    result["is_synthetic"] = 1
    result["record_present"] = df.get("record_present", pd.Series([1] * len(df))).fillna(1).astype(int)
    result["timeline_state"] = df.get("timeline_state", pd.Series(["synthetic"] * len(df))).fillna("synthetic")
    result["episode_id"] = df.get("episode_id", pd.Series([pd.NA] * len(df)))
    result["phase_name"] = df.get("phase_name", pd.Series([pd.NA] * len(df)))
    result["scenario_intensity"] = df.get("scenario_intensity", pd.Series([0.0] * len(df))).fillna(0.0)
    result["scenario_progress"] = df.get("scenario_progress", pd.Series([0.0] * len(df))).fillna(0.0)
    result["effect_strength"] = df.get("effect_strength", pd.Series([0.0] * len(df))).fillna(0.0)
    result["source_reference"] = "simulator_gap_aware"
    result["event_primary"] = df.get("system_context", pd.Series([pd.NA] * len(df)))
    result["event_labels"] = df.get("recovery_hint", pd.Series([pd.NA] * len(df)))

    result["packet_loss_flag"] = ((result["context_label"] == "packet_loss_outage") | (result["record_present"] == 0)).astype(int)
    result["loss_packet_count"] = 0
    result["outage_duration_steps"] = 0
    result["time_since_last_valid_step"] = 0
    result["recovery_step_index"] = 0
    result["nighttime_outage_flag"] = 0
    result["sunrise_recovery_flag"] = 0
    result["suspected_cause"] = "none"
    result["cause_confidence"] = 0.0

    for _, group in result.groupby("episode_id", dropna=True):
        episode_index = group.index.to_list()
        label = str(group["context_label"].iloc[0])
        if label != "packet_loss_outage":
            continue
        duration = len(episode_index)
        step_since_last = 0
        missing_rows = group[group["record_present"].astype(int) == 0]
        recovery_rows = group[group["record_present"].astype(int) == 1]
        start_ts = int(missing_rows["timestamp"].iloc[0]) if not missing_rows.empty else int(group["timestamp"].iloc[0])
        end_ts = int(group["timestamp"].iloc[-1])
        nighttime_flag = int(_night_overlap(start_ts, end_ts))
        sunrise_flag = 0
        if not recovery_rows.empty:
            recovery_hours = _local_dt_from_epoch(recovery_rows["timestamp"]).dt.hour
            sunrise_flag = int(((recovery_hours >= 6) & (recovery_hours <= 9)).any())
        suspected_cause = "unknown"
        cause_confidence = 0.35
        if nighttime_flag and sunrise_flag:
            suspected_cause = "possible_power_loss"
            cause_confidence = 0.90
        elif not nighttime_flag and duration <= 6:
            suspected_cause = "possible_network_issue"
            cause_confidence = 0.60
        for row_index in episode_index:
            result.at[row_index, "loss_packet_count"] = duration
            result.at[row_index, "outage_duration_steps"] = duration
            result.at[row_index, "nighttime_outage_flag"] = nighttime_flag
            result.at[row_index, "sunrise_recovery_flag"] = sunrise_flag
            result.at[row_index, "suspected_cause"] = suspected_cause
            result.at[row_index, "cause_confidence"] = cause_confidence
            if int(result.at[row_index, "record_present"]) == 0:
                step_since_last += 1
                result.at[row_index, "time_since_last_valid_step"] = step_since_last
                result.at[row_index, "recovery_step_index"] = 0
            else:
                result.at[row_index, "time_since_last_valid_step"] = duration
                result.at[row_index, "recovery_step_index"] = 1
    return result[CANONICAL_COLUMNS].sort_values("timestamp").reset_index(drop=True)


def build_canonical_dataset(real_event_csv: Path, synthetic_gap_aware_csv: Path, label_scheme_name: str) -> pd.DataFrame:
    real_df = build_real_canonical(real_event_csv, label_scheme_name)
    synthetic_df = build_synthetic_canonical(synthetic_gap_aware_csv, label_scheme_name)
    merged = pd.concat([real_df, synthetic_df], ignore_index=True)
    merged = merged.sort_values(["timestamp", "is_synthetic"]).reset_index(drop=True)
    return merged


def write_label_summary(canonical_df: pd.DataFrame, output_path: Path, label_scheme_name: str) -> None:
    label_scheme = get_label_scheme(label_scheme_name)
    payload = {
        "label_scheme": label_scheme.name,
        "class_names": list(label_scheme.class_names),
        "row_count": int(len(canonical_df)),
        "data_origin_counts": _value_counts_to_json_dict(canonical_df["data_origin"]),
        "context_label_counts": _value_counts_to_json_dict(canonical_df["context_label"]),
        "packet_loss_flag_count": int(canonical_df["packet_loss_flag"].fillna(0).astype(int).sum()),
        "split_counts": _value_counts_to_json_dict(canonical_df["split_name"]),
        "split_origin_counts": _records_to_json_safe(
            canonical_df.groupby(["split_name", "data_origin"]).size().rename("row_count").reset_index().to_dict(orient="records")
        ),
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
