from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from Config.runtime import BACKEND_SETTINGS
except ModuleNotFoundError:
    from ..Config.runtime import BACKEND_SETTINGS

from .contracts import SUPER_TABLE_SCHEMA_VERSION
from .utils.common import iso_utc_now, safe_int
from .utils.storage import read_jsonl, write_json, write_jsonl


@dataclass(frozen=True)
class SuperTableFusionResult:
    status: str
    layer1_root: Path
    output_root: Path
    manifest_path: Path
    latest_path: Path
    jsonl_path: Path
    csv_path: Path
    fused_row_count: int
    source_snapshot_count: int


class SuperTableFusionPipeline:
    def __init__(self, layer1_root: Path | None = None, output_root: Path | None = None):
        self.layer1_root = (layer1_root or BACKEND_SETTINGS.layer1_root).resolve()
        self.output_root = (output_root or BACKEND_SETTINGS.super_table_root).resolve()

    def run(self) -> SuperTableFusionResult:
        snapshots = self._load_layer1_snapshots()
        fused_rows = self._build_fused_rows(snapshots)

        jsonl_path = self.output_root / "super_table.jsonl"
        csv_path = self.output_root / "super_table.csv"
        latest_path = self.output_root / "latest.json"
        manifest_path = self.output_root / "manifest.json"

        write_jsonl(jsonl_path, fused_rows)
        self._write_csv(csv_path, fused_rows)
        write_json(latest_path, fused_rows[-1] if fused_rows else {})
        write_json(
            manifest_path,
            {
                "schema_version": SUPER_TABLE_SCHEMA_VERSION,
                "pipeline": "super_table_fusion",
                "ran_at_utc": iso_utc_now(),
                "layer1_root": str(self.layer1_root),
                "output_root": str(self.output_root),
                "fused_row_count": len(fused_rows),
                "source_snapshot_count": len(snapshots),
                "artifacts": {
                    "jsonl": str(jsonl_path),
                    "csv": str(csv_path),
                    "latest": str(latest_path),
                },
            },
        )

        return SuperTableFusionResult(
            status="ok",
            layer1_root=self.layer1_root,
            output_root=self.output_root,
            manifest_path=manifest_path,
            latest_path=latest_path,
            jsonl_path=jsonl_path,
            csv_path=csv_path,
            fused_row_count=len(fused_rows),
            source_snapshot_count=len(snapshots),
        )

    def _load_layer1_snapshots(self) -> list[dict[str, Any]]:
        snapshots: list[dict[str, Any]] = []
        if not self.layer1_root.exists():
            return snapshots

        for history_file in sorted(self.layer1_root.rglob("history.jsonl")):
            stream_name = history_file.parent.name
            rows = read_jsonl(history_file)
            deduped = self._dedupe_rows(rows)
            for row in deduped:
                ts_server = safe_int(row.get("timestamps", {}).get("ts_server"))
                if ts_server is None:
                    continue
                snapshots.append(
                    {
                        "stream_name": stream_name,
                        "sensor_id": str(row.get("sensor_id") or stream_name),
                        "snapshot": row,
                    }
                )

        return sorted(
            snapshots,
            key=lambda item: (
                safe_int(item["snapshot"].get("timestamps", {}).get("ts_server")) or 0,
                item["stream_name"],
            ),
        )

    def _dedupe_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows_by_ts: dict[int, dict[str, Any]] = {}
        for row in rows:
            ts_server = safe_int(row.get("timestamps", {}).get("ts_server"))
            if ts_server is None:
                continue
            rows_by_ts[ts_server] = row
        return [rows_by_ts[key] for key in sorted(rows_by_ts)]

    def _build_fused_rows(self, snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows_by_ts: dict[int, dict[str, Any]] = {}
        for item in snapshots:
            snapshot = item["snapshot"]
            ts_server = safe_int(snapshot.get("timestamps", {}).get("ts_server"))
            if ts_server is None:
                continue
            row = rows_by_ts.setdefault(
                ts_server,
                {
                    "schema_version": SUPER_TABLE_SCHEMA_VERSION,
                    "layer": "super_table",
                    "ts_server": ts_server,
                    "observed_at_local": snapshot.get("timestamps", {}).get("observed_at_local"),
                },
            )
            prefix = f"{item['stream_name']}__{item['sensor_id']}".replace("-", "_").replace(".", "_")
            row[f"{prefix}__source_event_key"] = snapshot.get("source", {}).get("event_key")
            row[f"{prefix}__source_path"] = snapshot.get("source", {}).get("path")
            self._flatten_into(row, f"{prefix}__perception", snapshot.get("perception", {}))
            self._flatten_into(row, f"{prefix}__status", snapshot.get("status", {}))
        return [rows_by_ts[key] for key in sorted(rows_by_ts)]

    def _flatten_into(self, target: dict[str, Any], prefix: str, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        for key, value in payload.items():
            normalized_key = str(key).replace("-", "_").replace(".", "_")
            field_name = f"{prefix}__{normalized_key}"
            if isinstance(value, dict):
                self._flatten_into(target, field_name, value)
            else:
                target[field_name] = value

    def _write_csv(self, path: Path, rows: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        fieldnames = sorted({key for row in rows for key in row})
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
