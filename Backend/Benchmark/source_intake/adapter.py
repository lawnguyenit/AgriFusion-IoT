from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[3]
BACKEND_DIR = ROOT_DIR / "Backend"
for import_path in (ROOT_DIR, BACKEND_DIR):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from Navigation.Core.layer1.contracts import TemporalSettings, active_field_names  # noqa: E402
from Navigation.Core.layer1.processors.temporal import apply_temporal_features  # noqa: E402


REQUIRED_SOURCE_COLUMNS: tuple[str, ...] = (
    "node_id",
    "raw_date_key",
    "event_key",
    "ts_sample",
)

def load_flattened_source(path: Path) -> pd.DataFrame:
    """Load and minimally validate the already-flattened Firebase export."""

    dataframe = pd.read_csv(path.resolve(), low_memory=False)
    missing = [column for column in REQUIRED_SOURCE_COLUMNS if column not in dataframe.columns]
    if missing:
        raise ValueError(f"Flattened source is missing required columns: {missing}")
    if dataframe.empty:
        raise ValueError("Flattened source is empty.")
    return dataframe


def build_canonical_candidate(source: pd.DataFrame) -> pd.DataFrame:
    """Map the flat source to the current Layer1 canonical field contract.

    The source export is not a raw Firebase payload, so unavailable packet
    metadata is deliberately left null. Temporal fields are derived by the
    same Layer1 processor used for normal canonical generation.
    """

    dataframe = source.copy()
    result = pd.DataFrame(
        {
            column: pd.Series(pd.NA, index=dataframe.index)
            for column in active_field_names()
        },
        index=dataframe.index,
    )

    node_id = dataframe["node_id"].astype("string")
    date_key = dataframe["raw_date_key"].astype("string")
    event_key = _numeric(dataframe["event_key"])
    ts_sample = _numeric(dataframe["ts_sample"])

    result["record.node_id"] = node_id
    result["record.date_key"] = date_key
    result["record.event_key"] = event_key
    result["record.id"] = node_id + ":" + date_key + ":" + event_key.astype("Int64").astype("string")
    result["record.source_path"] = (
        node_id + "/telemetry/" + date_key + "/" + event_key.astype("Int64").astype("string")
    )
    result["record.source_kind"] = "history"
    result["record.ts_sample"] = ts_sample
    # `event_key` is the stable Firebase identity key, not a guaranteed
    # server-upload timestamp. The flat export has no `ts_server` field, so
    # leave server/upload metadata unknown instead of fabricating it.
    result["record.ts_server"] = pd.NA
    result["record.sample_time_reconstructed"] = _optional_bool(dataframe, "time_reconstructed")
    result["record.sample_time_local"] = _local_sample_time(dataframe)
    result["record.upload_time_local"] = pd.NA
    result["record.is_demo"] = False
    result["record.excluded_reason"] = pd.NA

    # Snapshot sensor values are preserved even when their source validity is
    # false, matching the Layer1 rule that invalid-but-recorded evidence stays
    # traceable. Dataset views mask them through the validity fields below.
    value_map = {
        "sht.temp_c": "air_temp_c",
        "sht.humidity_pct": "air_rh_pct",
        "npk.soil_temp_c": "soil_temp_c",
        "npk.soil_moisture_pct": "soil_moisture_pct",
        "npk.ec": "soil_ec_us_cm",
        "npk.ph": "soil_ph",
        "npk.n_proxy": "soil_n_proxy",
        "npk.p_proxy": "soil_p_proxy",
        "npk.k_proxy": "soil_k_proxy",
    }
    for canonical_column, source_column in value_map.items():
        result[canonical_column] = _numeric(dataframe[source_column])

    air_read_ok = _optional_bool(dataframe, "air_read_ok")
    air_valid = _optional_bool(dataframe, "air_sample_valid")
    soil_read_ok = _optional_bool(dataframe, "soil_read_ok")
    soil_valid = _optional_bool(dataframe, "soil_sample_valid")

    _populate_sensor_branch(
        result,
        prefix="sht",
        read_ok=air_read_ok,
        sample_valid=air_valid,
        error_code=_source_text(dataframe, "air_error_code"),
        retry_count=_numeric(dataframe["air_retry_count"]),
        packet_present=air_valid,
    )
    _populate_sensor_branch(
        result,
        prefix="npk",
        read_ok=soil_read_ok,
        sample_valid=soil_valid,
        error_code=_source_text(dataframe, "soil_error_code"),
        retry_count=_numeric(dataframe["soil_retry_count"]),
        packet_present=soil_valid,
    )

    result["sht.read_elapsed_ms"] = pd.NA
    result["sht.value_valid"] = air_valid
    result["sht.values_available"] = air_valid
    result["sht.values_recorded_with_error"] = pd.NA
    result["npk.error_code_raw"] = pd.to_numeric(
        dataframe["soil_error_code"], errors="coerce"
    ).astype("Int64")
    result["npk.crc_ok"] = pd.NA
    result["npk.frame_ok"] = pd.NA
    result["npk.signal_present"] = soil_valid
    result["npk.values_valid"] = soil_valid
    result["npk.consecutive_fail_count"] = pd.NA
    result["npk.read_duration_ms"] = pd.NA
    result["npk.protocol_fault"] = pd.NA

    # Preserve source-provided provenance and per-field validity where the
    # current canonical contract has room for it.
    result["npk.soil_temp_valid"] = _optional_bool(dataframe, "soil_temp_valid")
    result["npk.soil_temp_source"] = _source_text(dataframe, "soil_temp_source")
    result["npk.soil_moisture_valid"] = _optional_bool(dataframe, "soil_moisture_valid")
    result["npk.soil_moisture_source"] = _source_text(dataframe, "soil_moisture_source")
    result["npk.soil_moisture_calibration_status"] = _source_text(
        dataframe, "soil_moisture_calibration_status"
    )
    result["npk.soil_moisture_calibration_profile"] = pd.NA
    result["npk.soil_moisture_value_semantics"] = _source_text(
        dataframe, "soil_moisture_value_semantics"
    )
    result["npk.soil_moisture_raw_adc"] = pd.NA
    result["npk.soil_moisture_voltage_mv"] = pd.NA
    result["npk.soil_moisture_install_depth_cm_min"] = pd.NA
    result["npk.soil_moisture_install_depth_cm_max"] = pd.NA
    result["npk.ph_protocol_ok"] = pd.NA
    result["npk.ph_valid"] = _optional_bool(dataframe, "soil_ph_valid")
    result["npk.ph_status"] = _source_text(dataframe, "ph_state")
    result["npk.ec_valid"] = _optional_bool(dataframe, "soil_ec_valid")
    result["npk.ec_source"] = _source_text(dataframe, "ec_source")
    result["npk.ec_measurement_kind"] = _source_text(dataframe, "ec_measurement_kind")
    # The export has one aggregate soil packet validity flag but no separate
    # N/P/K validity flags. Use the aggregate packet validity conservatively;
    # do not borrow moisture-specific validity for unrelated channels.
    result["npk.n_proxy_valid"] = soil_valid
    result["npk.p_proxy_valid"] = soil_valid
    result["npk.k_proxy_valid"] = soil_valid

    result["sensor.any_fault"] = _tri_or(
        result["sht.fault"], result["npk.fault"]
    )
    result["sensor.all_packets_missing"] = (
        result["sht.packet_present"].eq(False)
        & result["npk.packet_present"].eq(False)
    ).astype("boolean")

    buffered = _optional_bool(dataframe, "buffered")
    replayed = _optional_bool(dataframe, "replayed")
    result["delivery.replayed_raw"] = replayed
    result["delivery.was_buffered_raw"] = buffered
    result["delivery.is_buffered_replay"] = (buffered | replayed).astype("boolean")
    result["delivery.fallback_used"] = pd.NA
    result["delivery.buffer_reason"] = _source_text(dataframe, "buffer_reason")
    result["delivery.buffered_at_ms"] = pd.NA
    result["delivery.replayed_at_ms"] = pd.NA
    # The new CSV has no buffer/replay timestamps or reason for most rows, so
    # it cannot satisfy the canonical metadata-completeness definition.
    result["delivery.metadata_complete"] = False

    result["network.signal_dbm"] = _numeric(dataframe["signal_dbm"])
    result["network.gprs"] = _optional_bool(dataframe, "pdp_active")
    result["network.device_online"] = pd.NA
    result["device.wake_reason"] = _source_text(dataframe, "wake_reason")
    result["device.cycle_duration_ms"] = _numeric(dataframe["cycle_duration_ms"])
    result["device.heap_free"] = pd.NA
    result["device.reset_or_power_on"] = result["device.wake_reason"].eq("power_on_or_reset").astype("boolean")

    result, _, _ = apply_temporal_features(
        result,
        TemporalSettings(),
    )
    return result


def build_legacy_projection(candidate: pd.DataFrame, old_columns: list[str]) -> pd.DataFrame:
    """Return an exact-column projection compatible with the old CSV shape."""

    projection = pd.DataFrame(index=candidate.index)
    for column in old_columns:
        projection[column] = candidate[column] if column in candidate else pd.NA
    return projection


def build_segment_manifest(candidate: pd.DataFrame) -> dict[str, object]:
    """Build the cadence sidecar required by continuity-aware V2 windows."""

    segments: list[dict[str, object]] = []
    grouped = candidate.groupby(
        ["record.node_id", "record.segment_id", "record.segment_index"],
        dropna=False,
        sort=False,
    )
    for (node_id, segment_id, segment_index), frame in grouped:
        if pd.isna(segment_id):
            continue
        sample = pd.to_numeric(frame["record.ts_sample"], errors="coerce").dropna()
        expected = pd.to_numeric(
            frame["record.segment_expected_interval_sec"], errors="coerce"
        ).dropna()
        segments.append(
            {
                "node_id": str(node_id),
                "segment_id": str(segment_id),
                "segment_index": int(segment_index),
                "row_count": int(len(frame)),
                "start_ts_sample": int(sample.iloc[0]) if not sample.empty else None,
                "end_ts_sample": int(sample.iloc[-1]) if not sample.empty else None,
                "expected_interval_sec": int(expected.iloc[0]) if not expected.empty else 900,
            }
        )
    return {"schema_version": 1, "segments": segments}


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _source_text(dataframe: pd.DataFrame, column: str) -> pd.Series:
    if column not in dataframe.columns:
        return pd.Series(pd.NA, index=dataframe.index, dtype="string")
    return dataframe[column].astype("string").replace({"<NA>": pd.NA, "nan": pd.NA, "": pd.NA})


def _optional_bool(dataframe: pd.DataFrame, column: str) -> pd.Series:
    if column not in dataframe.columns:
        return pd.Series(pd.NA, index=dataframe.index, dtype="boolean")
    series = dataframe[column]
    normalized = series.map(_coerce_optional_bool)
    return normalized.astype("boolean")


def _coerce_optional_bool(value: Any) -> bool | pd._libs.missing.NAType:
    if value is None or pd.isna(value):
        return pd.NA
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return pd.NA


def _local_sample_time(dataframe: pd.DataFrame) -> pd.Series:
    values = pd.to_datetime(dataframe["sample_time_local_iso"], errors="coerce", utc=True)
    return values.dt.tz_convert("Asia/Ho_Chi_Minh").dt.strftime("%Y-%m-%d %H:%M:%S").astype("string")


def _populate_sensor_branch(
    result: pd.DataFrame,
    *,
    prefix: str,
    read_ok: pd.Series,
    sample_valid: pd.Series,
    error_code: pd.Series,
    retry_count: pd.Series,
    packet_present: pd.Series,
) -> None:
    known_error = error_code.notna() & error_code.ne("")
    status = pd.Series(pd.NA, index=result.index, dtype="string")
    status.loc[read_ok.eq(True) & sample_valid.eq(True)] = "ok"
    status.loc[read_ok.eq(False) | sample_valid.eq(False) | known_error] = "error"
    derived_error_code = error_code.copy()
    derived_error_code.loc[derived_error_code.isna() & status.eq("ok")] = "ok"
    derived_error_code.loc[derived_error_code.isna() & status.eq("error")] = "read_fail"

    result[f"{prefix}.packet_present"] = packet_present
    result[f"{prefix}.retry_count"] = retry_count
    result[f"{prefix}.read_ok"] = read_ok
    result[f"{prefix}.sample_valid"] = sample_valid
    result[f"{prefix}.status"] = status
    result[f"{prefix}.error_code"] = derived_error_code
    result[f"{prefix}.valid"] = sample_valid
    result[f"{prefix}.fault"] = sample_valid.map(
        lambda value: pd.NA if pd.isna(value) else not bool(value)
    ).astype("boolean")
    result[f"{prefix}.missing_packet"] = packet_present.map(
        lambda value: pd.NA if pd.isna(value) else not bool(value)
    ).astype("boolean")
    result[f"{prefix}.error_class"] = status.map(
        lambda value: pd.NA if pd.isna(value) else ("ok" if value == "ok" else "read_failure")
    ).astype("string")


def _tri_or(first: pd.Series, second: pd.Series) -> pd.Series:
    output = pd.Series(pd.NA, index=first.index, dtype="boolean")
    output.loc[first.eq(True) | second.eq(True)] = True
    output.loc[first.eq(False) & second.eq(False)] = False
    return output
