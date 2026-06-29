from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

FOUR_CLASS_REAL_LABEL_MAP = {
    "none": "normal_context",
    "weather_context": "rain_or_fertigation_context",
    "intervention_context": "rain_or_fertigation_context",
    "stress_context": "water_deficit",
    "system_timing": "packet_loss_outage",
    "sensor_fault_anomaly": "packet_loss_outage",
}

if __package__ and __package__.startswith("Backend."):
    from Backend.Config.paths import BACKEND_PATHS
else:
    from Config.paths import BACKEND_PATHS


ACTIVE_EVENT_CSV_NAMES = ("flb_input_with_events.csv", "benchmark_input_labeled.csv")
ACTIVE_ALIGNED_CSV_NAMES = ("flb_input_aligned.csv", "benchmark_input_aligned.csv")
EXP2_CSV_NAMES = {"flb_l2_exp2.csv", "single_window_exp2.csv"}


@dataclass(frozen=True)
class OutputCutoffMaintenanceResult:
    cutoff_local_date: str
    cutoff_local_iso: str
    cutoff_ts_utc: int
    layer1_row_counts: dict[str, int]
    layer1_removed_counts: dict[str, int]
    benchmark_row_counts: dict[str, int]
    benchmark_removed_counts: dict[str, int]
    four_class_counts: dict[str, int]
    updated_files: list[str] = field(default_factory=list)


def prune_outputs_after_local_date(*, cutoff_local_date: str, timezone_name: str) -> OutputCutoffMaintenanceResult:
    cutoff_day = date.fromisoformat(str(cutoff_local_date))
    local_zone = ZoneInfo(str(timezone_name))
    cutoff_local_dt = datetime.combine(cutoff_day, time(23, 59, 59), tzinfo=local_zone)
    cutoff_ts_utc = int(cutoff_local_dt.astimezone(timezone.utc).timestamp())

    updated_files: list[str] = []
    layer1_counts: dict[str, int] = {}
    layer1_removed: dict[str, int] = {}

    for sensor_name in ("sht30", "npk", "meteo"):
        sensor_result = _prune_layer1_sensor(
            sensor_dir=BACKEND_PATHS.layer1_dir / sensor_name,
            cutoff_ts_utc=cutoff_ts_utc,
        )
        layer1_counts[sensor_name] = sensor_result["kept_rows"]
        layer1_removed[sensor_name] = sensor_result["removed_rows"]
        updated_files.extend(sensor_result["updated_files"])

    benchmark_counts, benchmark_removed, benchmark_updates = _prune_benchmark_dataset(
        dataset_dir=BACKEND_PATHS.benchmark_dir / "benchmark_dataset" / "dataset",
        cutoff_ts_utc=cutoff_ts_utc,
    )
    updated_files.extend(benchmark_updates)

    four_class_counts = _build_four_class_counts(BACKEND_PATHS.benchmark_dir / "benchmark_dataset" / "dataset")

    return OutputCutoffMaintenanceResult(
        cutoff_local_date=cutoff_day.isoformat(),
        cutoff_local_iso=cutoff_local_dt.isoformat(),
        cutoff_ts_utc=cutoff_ts_utc,
        layer1_row_counts=layer1_counts,
        layer1_removed_counts=layer1_removed,
        benchmark_row_counts=benchmark_counts,
        benchmark_removed_counts=benchmark_removed,
        four_class_counts=four_class_counts,
        updated_files=sorted(dict.fromkeys(updated_files)),
    )


def _prune_layer1_sensor(*, sensor_dir: Path, cutoff_ts_utc: int) -> dict[str, object]:
    history_path = sensor_dir / "history.jsonl"
    latest_path = sensor_dir / "latest.json"
    state_path = sensor_dir / "state.json"

    updated_files: list[str] = []
    rows = _load_jsonl(history_path)
    kept_rows = [row for row in rows if _extract_history_ts(row) <= cutoff_ts_utc]
    removed_rows = len(rows) - len(kept_rows)

    if removed_rows > 0:
        _write_jsonl(history_path, kept_rows)
        updated_files.append(str(history_path))

    last_row = kept_rows[-1] if kept_rows else None
    if last_row is not None and latest_path.exists():
        _write_json(latest_path, last_row)
        updated_files.append(str(latest_path))

    if state_path.exists():
        state = _load_json(state_path)
        recent_ids = [_extract_record_id(row) for row in kept_rows[-128:]]
        recent_ids = [record_id for record_id in recent_ids if record_id]
        if last_row is not None:
            last_ts = _extract_history_ts(last_row)
            state["last_processed_server_ts"] = last_ts
            state["last_processed_event_key"] = _extract_record_id(last_row)
        state["processed_record_count"] = len(kept_rows)
        state["recent_record_ids"] = recent_ids
        _write_json(state_path, state)
        updated_files.append(str(state_path))

    return {
        "kept_rows": len(kept_rows),
        "removed_rows": removed_rows,
        "updated_files": updated_files,
    }


def _prune_benchmark_dataset(*, dataset_dir: Path, cutoff_ts_utc: int) -> tuple[dict[str, int], dict[str, int], list[str]]:
    row_counts: dict[str, int] = {}
    removed_counts: dict[str, int] = {}
    updated_files: list[str] = []

    dataset_dir.mkdir(parents=True, exist_ok=True)
    for csv_path in sorted(dataset_dir.glob("*.csv")):
        frame = pd.read_csv(csv_path)
        if "timestamp" not in frame.columns:
            continue
        filtered = _filter_timestamp_frame(frame, cutoff_ts_utc=cutoff_ts_utc)
        if csv_path.name in EXP2_CSV_NAMES:
            filtered = filtered.dropna().reset_index(drop=True)
        removed_count = int(len(frame) - len(filtered))
        row_counts[csv_path.name] = int(len(filtered))
        removed_counts[csv_path.name] = removed_count
        if removed_count > 0 or csv_path.name in EXP2_CSV_NAMES:
            filtered.to_csv(csv_path, index=False)
            updated_files.append(str(csv_path))

    updated_files.extend(_refresh_dataset_reports(dataset_dir=dataset_dir, row_counts=row_counts))
    return row_counts, removed_counts, updated_files


def _filter_timestamp_frame(frame: pd.DataFrame, *, cutoff_ts_utc: int) -> pd.DataFrame:
    filtered = frame.copy()
    filtered["timestamp"] = pd.to_numeric(filtered["timestamp"], errors="coerce")
    filtered = filtered.dropna(subset=["timestamp"]).copy()
    filtered["timestamp"] = filtered["timestamp"].astype("int64")
    filtered = filtered.loc[filtered["timestamp"] <= int(cutoff_ts_utc)].copy()
    filtered = filtered.sort_values("timestamp", kind="stable").drop_duplicates(subset=["timestamp"], keep="last")
    return filtered.reset_index(drop=True)


def _refresh_dataset_reports(*, dataset_dir: Path, row_counts: dict[str, int]) -> list[str]:
    updated_files: list[str] = []

    manifest_path = dataset_dir / "manifest.json"
    aligned_csv = _resolve_first_existing(dataset_dir, ACTIVE_ALIGNED_CSV_NAMES)
    if manifest_path.exists() and aligned_csv is not None:
        manifest = _load_json(manifest_path)
        manifest["row_count"] = int(row_counts.get(aligned_csv.name, manifest.get("row_count", 0)))
        input_counts = manifest.get("input_counts")
        if isinstance(input_counts, dict):
            input_counts["npk_records"] = _jsonl_row_count(BACKEND_PATHS.layer1_dir / "npk" / "history.jsonl")
            input_counts["sht30_records"] = _jsonl_row_count(BACKEND_PATHS.layer1_dir / "sht30" / "history.jsonl")
            input_counts["meteo_records"] = _jsonl_row_count(BACKEND_PATHS.layer1_dir / "meteo" / "history.jsonl")
            input_counts["anchor_count"] = manifest["row_count"]
        _write_json(manifest_path, manifest)
        updated_files.append(str(manifest_path))

    event_csv = _resolve_first_existing(dataset_dir, ACTIVE_EVENT_CSV_NAMES)
    event_frame = pd.read_csv(event_csv) if event_csv is not None and event_csv.exists() else None
    if event_frame is not None and "timestamp" in event_frame.columns:
        event_frame = _filter_timestamp_frame(event_frame, cutoff_ts_utc=2**63 - 1)

    labeling_report_path = dataset_dir / "flb_real_event_labeling_report.json"
    if labeling_report_path.exists() and event_frame is not None:
        report = _load_json(labeling_report_path)
        report["row_count"] = int(len(event_frame))
        report["lookup_matched_rows"] = int(len(event_frame))
        report["lookup_missing_rows"] = 0
        report["big_label_counts"] = (
            event_frame["big_label"].fillna("none").astype(str).value_counts(dropna=False).sort_index().astype(int).to_dict()
            if "big_label" in event_frame.columns
            else {}
        )
        event_columns = [column for column in event_frame.columns if column.startswith("event_")]
        report["event_counts"] = {
            column: int(pd.to_numeric(event_frame[column], errors="coerce").fillna(0).sum())
            for column in event_columns
        }
        _write_json(labeling_report_path, report)
        updated_files.append(str(labeling_report_path))

    stage_report_names = (
        "flb_layer2_build_report.json",
        "flb_layer3_combo_build_report.json",
        "single_window_feature_build_report.json",
    )
    for report_name in stage_report_names:
        report_path = dataset_dir / report_name
        if not report_path.exists():
            continue
        report = _load_json(report_path)
        generated_files = report.get("generated_files")
        if isinstance(generated_files, list):
            for item in generated_files:
                if not isinstance(item, dict):
                    continue
                output_csv = Path(str(item.get("output_csv", "")))
                if output_csv.name in row_counts:
                    item["row_count"] = int(row_counts[output_csv.name])
            _write_json(report_path, report)
            updated_files.append(str(report_path))

    root_report_path = dataset_dir / "flb_dataset_build_report.json"
    if root_report_path.exists():
        report = _load_json(root_report_path)
        stages = report.get("stages")
        if isinstance(stages, dict):
            layer1_stage = stages.get("layer1")
            if isinstance(layer1_stage, dict) and aligned_csv is not None:
                layer1_stage["row_count"] = int(row_counts.get(aligned_csv.name, layer1_stage.get("row_count", 0)))
            label_stage = stages.get("real_event_labeling")
            if isinstance(label_stage, dict) and event_frame is not None:
                label_stage["row_count"] = int(len(event_frame))
                label_stage["lookup_matched_rows"] = int(len(event_frame))
                label_stage["big_label_counts"] = (
                    event_frame["big_label"].fillna("none").astype(str).value_counts(dropna=False).sort_index().astype(int).to_dict()
                    if "big_label" in event_frame.columns
                    else {}
                )
                label_stage["event_counts"] = {
                    column: int(pd.to_numeric(event_frame[column], errors="coerce").fillna(0).sum())
                    for column in event_frame.columns
                    if column.startswith("event_")
                }
            for stage_key in ("layer2", "layer3_combo"):
                stage_payload = stages.get(stage_key)
                if not isinstance(stage_payload, dict):
                    continue
                generated_files = stage_payload.get("generated_files")
                if isinstance(generated_files, list):
                    for item in generated_files:
                        if not isinstance(item, dict):
                            continue
                        output_csv = Path(str(item.get("output_csv", "")))
                        if output_csv.name in row_counts:
                            item["row_count"] = int(row_counts[output_csv.name])
        _write_json(root_report_path, report)
        updated_files.append(str(root_report_path))

    return updated_files


def _build_four_class_counts(dataset_dir: Path) -> dict[str, int]:
    event_csv = _resolve_first_existing(dataset_dir, ACTIVE_EVENT_CSV_NAMES)
    if event_csv is None or not event_csv.exists():
        return {}
    frame = pd.read_csv(event_csv)
    if "timestamp" not in frame.columns:
        return {}
    source = frame.get("big_label")
    if source is None:
        return {}
    counts = source.fillna("none").astype(str).map(FOUR_CLASS_REAL_LABEL_MAP).fillna("normal_context").value_counts(dropna=False)
    return {str(name): int(counts.get(name, 0)) for name in sorted(counts.index.astype(str).tolist())}


def _resolve_first_existing(dataset_dir: Path, candidate_names: tuple[str, ...]) -> Path | None:
    for name in candidate_names:
        candidate = dataset_dir / name
        if candidate.exists():
            return candidate
    return None


def _jsonl_row_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")


def _extract_history_ts(row: dict[str, object]) -> int:
    timestamps = row.get("timestamps")
    if isinstance(timestamps, dict):
        ts_value = timestamps.get("ts_server")
        if ts_value is not None:
            return int(ts_value)
    ts_value = row.get("timestamp")
    if ts_value is not None:
        return int(ts_value)
    return 0


def _extract_record_id(row: dict[str, object]) -> str:
    source = row.get("source")
    if isinstance(source, dict):
        event_key = source.get("event_key")
        if event_key:
            return str(event_key)
    timestamps = row.get("timestamps")
    if isinstance(timestamps, dict):
        ts_server = timestamps.get("ts_server")
        if ts_server is not None:
            return str(int(ts_server))
    return ""
