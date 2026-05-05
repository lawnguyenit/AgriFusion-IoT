from __future__ import annotations

import json
from bisect import bisect_right
from typing import Any, Iterable

try:
    from Backend.Config.IO.io_json import read_jsonl
    from Backend.Config.data_utils import safe_int
except ImportError:
    from ...Config.IO.io_json import read_jsonl
    from ...Config.data_utils import safe_int

from .model import Layer1Record, StreamIndex


def detect_family(row: dict[str, Any], source_path: Path) -> str:
    processor_name = str(row.get("processor_name") or "").lower()
    sensor_type = str(row.get("sensor_type") or "").lower()
    folder_name = source_path.parent.name.lower()

    if "sht30" in processor_name or "sht30" in sensor_type or folder_name == "sht30":
        return "sht30"
    if "npk" in processor_name or "npk" in sensor_type or folder_name == "npk":
        return "npk"
    if "meteo" in processor_name or "open_meteo" in sensor_type or "weather" in processor_name:
        return "meteo"
    return folder_name or "unknown"


def extract_perception(row: dict[str, Any]) -> dict[str, Any]:
    perception = row.get("perception")
    if isinstance(perception, dict):
        return perception
    return {}


def extract_timestamps(row: dict[str, Any]) -> dict[str, Any]:
    timestamps = row.get("timestamps")
    if isinstance(timestamps, dict):
        return timestamps
    return {}


def extract_source(row: dict[str, Any]) -> dict[str, Any]:
    source = row.get("source")
    if isinstance(source, dict):
        return source
    return {}


def build_stream_index(records: Iterable[Layer1Record]) -> StreamIndex:
    ordered = sorted(records, key=lambda item: (item.ts_server, item.source_event_key))
    return StreamIndex(
        ts_values=[item.ts_server for item in ordered],
        records=ordered,
    )


def latest_in_window(index: StreamIndex, anchor_ts: int, max_age_sec: int) -> Layer1Record | None:
    if not index.records:
        return None
    pos = bisect_right(index.ts_values, anchor_ts) - 1
    if pos < 0:
        return None
    record = index.records[pos]
    if anchor_ts - record.ts_server > max_age_sec:
        return None
    return record


def load_layer1_records(layer1_root: Path) -> dict[str, StreamIndex]:
    family_rows: dict[str, dict[str, Layer1Record]] = {"sht30": {}, "npk": {}, "meteo": {}, "unknown": {}}

    for history_file in sorted(layer1_root.rglob("history.jsonl")):
        raw_rows = read_jsonl(history_file)
        latest_path = history_file.parent / "latest.json"
        if latest_path.exists():
            loaded = json.loads(latest_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                raw_rows.append(loaded)

        for row in raw_rows:
            timestamps = extract_timestamps(row)
            ts_server = safe_int(timestamps.get("ts_server"))
            if ts_server is None:
                continue
            source = extract_source(row)
            source_event_key = str(source.get("event_key") or ts_server)
            family = detect_family(row=row, source_path=history_file)
            record = Layer1Record(
                family=family,
                ts_server=ts_server,
                observed_at_local=str(timestamps.get("observed_at_local") or ""),
                source_name=str(source.get("source_name") or history_file.parent.name),
                source_event_key=source_event_key,
                payload=row,
            )
            family_rows.setdefault(family, {})[f"{ts_server}:{source_event_key}"] = record

    return {
        family: build_stream_index(records=family_map.values())
        for family, family_map in family_rows.items()
        if family_map
    }
