from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from Backend.Config.IO.io_json import read_json, read_jsonl
    from Backend.Config.data_utils import safe_float, safe_int
except ImportError:
    from ...Config.IO.io_json import read_json, read_jsonl
    from ...Config.data_utils import safe_float, safe_int

from .config import AlignmentConfig
from .ec_npk_consistency import ECConsistencyModel, check_ec_npk_consistency, fit_ec_model


@dataclass(frozen=True)
class SourceRecord:
    family: str
    ts_server: int
    source_event_key: str
    source_name: str
    observed_at_local: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class AlignmentResult:
    input_root: Path
    output_root: Path
    row_count: int
    input_counts: dict[str, int]
    missing_counts: dict[str, int]
    flag_distribution: dict[str, int]
    csv_path: Path
    manifest_path: Path
    ec_model: ECConsistencyModel
    rows: list[dict[str, Any]]


def _extract_timestamps(row: dict[str, Any]) -> dict[str, Any]:
    timestamps = row.get("timestamps")
    return timestamps if isinstance(timestamps, dict) else {}


def _extract_source(row: dict[str, Any]) -> dict[str, Any]:
    source = row.get("source")
    return source if isinstance(source, dict) else {}


def _extract_perception(row: dict[str, Any]) -> dict[str, Any]:
    perception = row.get("perception")
    return perception if isinstance(perception, dict) else {}


def _load_source_records(layer1_root: Path) -> dict[str, list[SourceRecord]]:
    records: dict[str, list[SourceRecord]] = {"npk": [], "sht30": [], "meteo": []}
    seen_by_family: dict[str, set[str]] = {family: set() for family in records}
    for history_file in sorted(layer1_root.rglob("history.jsonl")):
        family = history_file.parent.name.lower()
        if family not in records:
            continue

        raw_rows = read_jsonl(history_file)
        latest_path = history_file.parent / "latest.json"
        if latest_path.exists():
            latest_payload = read_json(latest_path)
            if isinstance(latest_payload, dict):
                raw_rows.append(latest_payload)

        for row in raw_rows:
            timestamps = _extract_timestamps(row)
            ts_server = safe_int(timestamps.get("ts_server"))
            if ts_server is None:
                continue
            source = _extract_source(row)
            source_event_key = str(source.get("event_key") or ts_server)
            dedupe_key = f"{ts_server}:{source_event_key}"
            if dedupe_key in seen_by_family[family]:
                continue
            seen_by_family[family].add(dedupe_key)

            records[family].append(
                SourceRecord(
                    family=family,
                    ts_server=ts_server,
                    source_event_key=source_event_key,
                    source_name=str(source.get("source_name") or history_file.parent.name),
                    observed_at_local=str(timestamps.get("observed_at_local") or ""),
                    payload=row,
                )
            )

    for family in records:
        records[family].sort(key=lambda item: (item.ts_server, item.source_event_key))
    return records


def _cluster_anchors(npk_ts: list[int], sht_ts: list[int], gap_sec: int) -> list[int]:
    if not npk_ts and not sht_ts:
        return []

    npk_set = set(npk_ts)
    all_points = sorted(set(npk_ts) | set(sht_ts))
    clusters: list[list[int]] = []
    current_cluster = [all_points[0]]
    for ts in all_points[1:]:
        if ts - current_cluster[-1] <= gap_sec:
            current_cluster.append(ts)
        else:
            clusters.append(current_cluster)
            current_cluster = [ts]
    clusters.append(current_cluster)

    anchors: list[int] = []
    for cluster in clusters:
        npk_candidates = [ts for ts in cluster if ts in npk_set]
        if npk_candidates:
            anchors.append(max(npk_candidates))
        else:
            anchors.append(max(cluster))
    return anchors


def _nearest_record(records: list[SourceRecord], anchor_ts: int, max_age_sec: int) -> SourceRecord | None:
    if not records:
        return None
    ts_values = [record.ts_server for record in records]
    pos = bisect_right(ts_values, anchor_ts)
    candidates: list[SourceRecord] = []
    if pos > 0:
        candidates.append(records[pos - 1])
    if pos < len(records):
        candidates.append(records[pos])
    if not candidates:
        return None
    nearest = min(candidates, key=lambda item: abs(item.ts_server - anchor_ts))
    if abs(nearest.ts_server - anchor_ts) > max_age_sec:
        return None
    return nearest


def _coerce_float(row: dict[str, Any], key: str) -> float | None:
    return safe_float(row.get(key))


def _build_base_row(anchor_ts: int, npk_record: SourceRecord | None, sht_record: SourceRecord | None) -> tuple[dict[str, Any], list[str], int | None]:
    npk_perception = _extract_perception(npk_record.payload) if npk_record else {}
    sht_perception = _extract_perception(sht_record.payload) if sht_record else {}

    soil_temp = _coerce_float(npk_perception, "soil_temp_c")
    soil_humidity = _coerce_float(npk_perception, "soil_humidity_pct")
    air_temp = _coerce_float(sht_perception, "temp_air_c")
    air_humidity = _coerce_float(sht_perception, "humidity_air_pct")
    ec_value = _coerce_float(npk_perception, "soil_ec_us_cm")
    ph_value = _coerce_float(npk_perception, "soil_ph")
    n_value = _coerce_float(npk_perception, "n_ppm")
    p_value = _coerce_float(npk_perception, "p_ppm")
    k_value = _coerce_float(npk_perception, "k_ppm")

    row = {
        "timestamp": anchor_ts,
        "soil_temp": soil_temp,
        "soil_humidity": soil_humidity,
        "air_temp": air_temp,
        "air_humidity": air_humidity,
        "EC": ec_value,
        "pH": ph_value,
        "N": n_value,
        "P": p_value,
        "K": k_value,
    }

    missing_fields = [key for key, value in row.items() if key != "timestamp" and value is None]
    source_gap_sec: int | None = None
    if npk_record is not None and sht_record is not None:
        source_gap_sec = abs(npk_record.ts_server - sht_record.ts_server)

    return row, missing_fields, source_gap_sec


def align_layer1_records(
    config: AlignmentConfig,
) -> tuple[list[dict[str, Any]], dict[str, int], dict[str, int], ECConsistencyModel, dict[str, int]]:
    
    source_records = _load_source_records(config.input_root)
    npk_records = source_records.get("npk", [])
    sht_records = source_records.get("sht30", [])

    if not npk_records and not sht_records:
        raise FileNotFoundError(f"No Layer1 npk/sht30 history.jsonl files found under {config.input_root}")

    if not npk_records:
        print(f"Warning: no npk history found under {config.input_root / 'npk'}")
    if not sht_records:
        print(f"Warning: no sht30 history found under {config.input_root / 'sht30'}")

    anchors = _cluster_anchors(
        [item.ts_server for item in npk_records],
        [item.ts_server for item in sht_records],
        config.anchor_cluster_gap_sec,
    )

    rows: list[dict[str, Any]] = []
    flag_distribution: dict[str, int] = {}

    for anchor_ts in anchors:
        npk_record = _nearest_record(npk_records, anchor_ts, config.family_match_tolerance_sec)
        sht_record = _nearest_record(sht_records, anchor_ts, config.family_match_tolerance_sec)
        base_row, missing_fields, source_gap_sec = _build_base_row(anchor_ts, npk_record, sht_record)

        rows.append(
            {
                **base_row,
                "_npk_ts": None if npk_record is None else npk_record.ts_server,
                "_sht_ts": None if sht_record is None else sht_record.ts_server,
                "_npk_present": npk_record is not None,
                "_sht_present": sht_record is not None,
                "_missing_fields": missing_fields,
                "_source_gap_sec": source_gap_sec,
                "_npk_source_name": None if npk_record is None else npk_record.source_name,
                "_sht_source_name": None if sht_record is None else sht_record.source_name,
                "_anchor_source": "npk" if npk_record is not None else "sht30",
            }
        )

    ec_model = fit_ec_model(
        rows,
        default_slope=config.ec_default_slope,
        default_intercept=config.ec_default_intercept,
        min_samples=config.ec_model_min_samples,
    )

    for row in rows:
        ec_score, ec_flag, ec_reason = check_ec_npk_consistency(
            row.get("EC"),
            row.get("N"),
            row.get("P"),
            row.get("K"),
            model=ec_model,
            warn_ratio=config.ec_residual_warn_ratio,
            critical_ratio=config.ec_residual_critical_ratio,
        )
        row["ec_npk_consistency_score"] = ec_score
        row["ec_npk_consistency_flag"] = int(ec_score >= config.ec_consistency_binary_threshold)
        row["_ec_npk_reason"] = ec_reason

        flag_key = str(row["ec_npk_consistency_flag"])
        flag_distribution[flag_key] = flag_distribution.get(flag_key, 0) + 1

    output_rows = [
        {
            "timestamp": row["timestamp"],
            "soil_temp": row["soil_temp"],
            "soil_humidity": row["soil_humidity"],
            "air_temp": row["air_temp"],
            "air_humidity": row["air_humidity"],
            "EC": row["EC"],
            "pH": row["pH"],
            "N": row["N"],
            "P": row["P"],
            "K": row["K"],
            "ec_npk_consistency_score": row["ec_npk_consistency_score"],
            "ec_npk_consistency_flag": row["ec_npk_consistency_flag"],
        }
        for row in rows
    ]

    input_counts = {
        "npk_records": len(npk_records),
        "sht30_records": len(sht_records),
        "meteo_records": len(source_records.get("meteo", [])),
        "anchor_count": len(anchors),
    }
    missing_counts = {
        "soil_temp": sum(1 for row in output_rows if row["soil_temp"] is None),
        "soil_humidity": sum(1 for row in output_rows if row["soil_humidity"] is None),
        "air_temp": sum(1 for row in output_rows if row["air_temp"] is None),
        "air_humidity": sum(1 for row in output_rows if row["air_humidity"] is None),
        "EC": sum(1 for row in output_rows if row["EC"] is None),
        "pH": sum(1 for row in output_rows if row["pH"] is None),
        "N": sum(1 for row in output_rows if row["N"] is None),
        "P": sum(1 for row in output_rows if row["P"] is None),
        "K": sum(1 for row in output_rows if row["K"] is None),
        "ec_npk_consistency_score": sum(1 for row in output_rows if row["ec_npk_consistency_score"] is None),
        "ec_npk_consistency_flag": sum(1 for row in output_rows if row["ec_npk_consistency_flag"] is None),
    }

    return output_rows, input_counts, missing_counts, ec_model, flag_distribution
