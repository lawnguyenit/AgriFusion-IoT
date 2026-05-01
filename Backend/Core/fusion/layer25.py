from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from Services.config.settings import SETTINGS as EXPORT_SETTINGS
except ModuleNotFoundError:
    from ...Services.config.settings import SETTINGS as EXPORT_SETTINGS

from ..utils.common import iso_utc_now, safe_int
from ..utils.storage import read_json, read_jsonl, write_json, write_jsonl
from ..contracts import LAYER25_SCHEMA_VERSION


@dataclass(frozen=True)
class Layer25Result:
    status: str
    layer2_root: Path
    output_root: Path
    manifest_path: Path
    latest_path: Path
    jsonl_path: Path
    csv_path: Path
    ready_jsonl_path: Path
    ready_csv_path: Path
    fused_row_count: int
    ready_row_count: int
    source_snapshot_count: int
    source_targets: list[str]


class Layer25FusionPipeline:
    def __init__(self, layer2_root: Path | None = None, output_root: Path | None = None):
        self.layer2_root = layer2_root or EXPORT_SETTINGS.layer2_root
        self.output_root = output_root or (EXPORT_SETTINGS.layer25_root / "super_table")

    def run(self) -> Layer25Result:
        snapshots, source_targets = self._load_layer2_snapshots()
        fused_rows = self._build_fused_rows(snapshots=snapshots, source_targets=source_targets)
        ready_rows = [row for row in fused_rows if row.get("tabnet_ready")]

        jsonl_path = self.output_root / "super_table.jsonl"
        csv_path = self.output_root / "super_table.csv"
        ready_jsonl_path = self.output_root / "tabnet_ready.jsonl"
        ready_csv_path = self.output_root / "tabnet_ready.csv"
        latest_path = self.output_root / "latest.json"
        manifest_path = self.output_root / "manifest.json"

        write_jsonl(jsonl_path, fused_rows)
        self._write_csv(csv_path, fused_rows)
        write_jsonl(ready_jsonl_path, ready_rows)
        self._write_csv(ready_csv_path, ready_rows)
        write_json(latest_path, fused_rows[-1] if fused_rows else {})

        manifest_payload = {
            "schema_version": LAYER25_SCHEMA_VERSION,
            "pipeline": "layer2_5_fusion",
            "ran_at_utc": iso_utc_now(),
            "layer2_root": str(self.layer2_root),
            "output_root": str(self.output_root),
            "fused_row_count": len(fused_rows),
            "ready_row_count": len(ready_rows),
            "source_snapshot_count": len(snapshots),
            "source_targets": source_targets,
            "artifacts": {
                "jsonl": str(jsonl_path),
                "csv": str(csv_path),
                "ready_jsonl": str(ready_jsonl_path),
                "ready_csv": str(ready_csv_path),
                "latest": str(latest_path),
            },
        }
        write_json(manifest_path, manifest_payload)

        return Layer25Result(
            status="ok",
            layer2_root=self.layer2_root,
            output_root=self.output_root,
            manifest_path=manifest_path,
            latest_path=latest_path,
            jsonl_path=jsonl_path,
            csv_path=csv_path,
            ready_jsonl_path=ready_jsonl_path,
            ready_csv_path=ready_csv_path,
            fused_row_count=len(fused_rows),
            ready_row_count=len(ready_rows),
            source_snapshot_count=len(snapshots),
            source_targets=source_targets,
        )

    def _load_layer2_snapshots(self) -> tuple[list[dict[str, Any]], list[str]]:
        snapshots: list[dict[str, Any]] = []
        source_targets: list[str] = []

        if not self.layer2_root.exists():
            return snapshots, source_targets

        for history_file in sorted(self.layer2_root.rglob("history.jsonl")):
            sensor_id = history_file.parent.name
            stream_name = history_file.parent.parent.name
            target_key = f"{stream_name}/{sensor_id}"
            source_targets.append(target_key)
            target_state = read_json(history_file.parent / "state.json", default={})
            rows = read_jsonl(history_file)
            deduped_rows = self._dedupe_sensor_rows(rows=rows)
            for row in deduped_rows:
                if not self._should_include_snapshot(row):
                    continue
                snapshots.append(
                    {
                        "target_key": target_key,
                        "stream_name": stream_name,
                        "sensor_id": sensor_id,
                        "state": target_state if isinstance(target_state, dict) else {},
                        "snapshot": row,
                    }
                )

        return sorted(
            snapshots,
            key=lambda item: (
                safe_int(item["snapshot"].get("timestamps", {}).get("ts_hour_bucket")) or 0,
                item["target_key"],
            ),
        ), sorted(source_targets)

    def _dedupe_sensor_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows_by_bucket: dict[int, dict[str, Any]] = {}
        for row in rows:
            timestamps = row.get("timestamps", {})
            ts_bucket = safe_int(timestamps.get("ts_hour_bucket")) or safe_int(timestamps.get("ts_server"))
            if ts_bucket is None:
                continue
            rows_by_bucket[ts_bucket] = row
        return [rows_by_bucket[key] for key in sorted(rows_by_bucket)]

    def _should_include_snapshot(self, snapshot: dict[str, Any]) -> bool:
        timestamps = snapshot.get("timestamps", {})
        if safe_int(timestamps.get("ts_hour_bucket")) is None and safe_int(timestamps.get("ts_server")) is None:
            return False
        return True

    def _build_fused_rows(self, snapshots: list[dict[str, Any]], source_targets: list[str]) -> list[dict[str, Any]]:
        rows_by_bucket: dict[int, dict[str, Any]] = {}
        expected_targets = sorted(source_targets)

        for item in snapshots:
            snapshot = item["snapshot"]
            timestamps = snapshot.get("timestamps", {})
            ts_bucket = safe_int(timestamps.get("ts_hour_bucket")) or safe_int(timestamps.get("ts_server"))
            if ts_bucket is None:
                continue

            row = rows_by_bucket.setdefault(
                ts_bucket,
                {
                    "schema_version": LAYER25_SCHEMA_VERSION,
                    "layer": "layer2_5",
                    "ts_hour_bucket": ts_bucket,
                    "observed_at_hour_local": timestamps.get("observed_at_hour_local")
                    or timestamps.get("observed_at_local"),
                    "sources_present": [],
                    "source_targets_expected": expected_targets,
                },
            )

            target_key = item["target_key"]
            if target_key not in row["sources_present"]:
                row["sources_present"].append(target_key)

            prefix = self._column_prefix(
                stream_name=item["stream_name"],
                sensor_id=item["sensor_id"],
            )
            row[f"{prefix}__source_event_key"] = snapshot.get("source", {}).get("event_key")
            row[f"{prefix}__source_path"] = snapshot.get("source", {}).get("path")
            row[f"{prefix}__sensor_type"] = snapshot.get("sensor_type")

            self._flatten_into(
                target=row,
                prefix=f"{prefix}__perception",
                payload=snapshot.get("perception", {}),
            )
            self._flatten_into(
                target=row,
                prefix=f"{prefix}__context",
                payload=snapshot.get("context", {}),
            )
            self._flatten_into(
                target=row,
                prefix=f"{prefix}__quality",
                payload=snapshot.get("quality", {}),
            )
            self._flatten_into(
                target=row,
                prefix=f"{prefix}__derived",
                payload=snapshot.get("derived_signals", {}),
            )

        fused_rows = [rows_by_bucket[key] for key in sorted(rows_by_bucket)]
        expected_count = max(len(expected_targets), 1)
        for row in fused_rows:
            row["sources_present"] = sorted(row["sources_present"])
            row["missing_sources"] = [
                target_key for target_key in expected_targets if target_key not in row["sources_present"]
            ]
            row["source_count"] = len(row["sources_present"])
            row["source_count_expected"] = len(expected_targets)
            row["source_coverage_ratio"] = round(row["source_count"] / expected_count, 4)
            row["tabnet_ready"] = row["source_count"] == len(expected_targets) and len(expected_targets) > 0
            for target_key in expected_targets:
                presence_key = self._presence_prefix(target_key)
                row[presence_key] = target_key in row["sources_present"]
        return fused_rows

    def _column_prefix(self, stream_name: str, sensor_id: str) -> str:
        return f"{stream_name}__{sensor_id}".replace("-", "_").replace(".", "_")

    def _presence_prefix(self, target_key: str) -> str:
        return f"present__{target_key}".replace("/", "__").replace("-", "_").replace(".", "_")

    def _flatten_into(self, target: dict[str, Any], prefix: str, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        for key, value in payload.items():
            normalized_key = str(key).replace("-", "_").replace(".", "_")
            column_name = f"{prefix}__{normalized_key}"
            if isinstance(value, dict):
                self._flatten_into(target=target, prefix=column_name, payload=value)
            elif isinstance(value, list):
                target[column_name] = "|".join(str(item) for item in value)
            else:
                target[column_name] = value

    def _write_csv(self, path: Path, rows: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not rows:
            path.write_text("", encoding="utf-8")
            return

        fieldnames = sorted({key for row in rows for key in row.keys()})
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                csv_row = {
                    key: "|".join(value) if isinstance(value, list) else value
                    for key, value in row.items()
                }
                writer.writerow(csv_row)
