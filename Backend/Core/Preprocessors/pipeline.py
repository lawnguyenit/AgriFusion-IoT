from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, cast

try:
    from Services.app_config import SETTINGS as EXPORT_SETTINGS
except ModuleNotFoundError:
    from ....Services.app_config import SETTINGS as EXPORT_SETTINGS

from ..environmental_intelligence.meteo_processor import MeteoProcessor
from ..NPK.NPK_Data import NPKProcessor
from ..SHT30.SHT30_Data import SHT30Processor
from ...Config.common import floor_ts_to_hour, iso_utc_now, safe_int, trim_recent_ids
from ...Config.storage import append_jsonl, read_json, read_jsonl, write_json


@dataclass(frozen=True)
class SourceRecord:
    event_key: str
    date_key: str
    source_kind: str
    source_path: str
    payload: dict[str, Any]
    ts_server: int | None
    ts_device: int | None
    ts_hour_bucket: int | None


@dataclass(frozen=True)
class SourceStore:
    name: str
    history_root: Path
    latest_payload_path: Path
    latest_meta_path: Path


@dataclass(frozen=True)
class Layer2Result:
    status: str
    processed_source_records: int
    filtered_out_records: int
    total_new_snapshots: int
    output_root: Path
    manifest_path: Path
    sensor_counts: dict[str, int]


class PreprocessingPipeline:
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or EXPORT_SETTINGS.base_dir
        self.history_root = self.base_dir / "history"
        self.latest_payload_path = self.base_dir / "new_raw" / "latest.json"
        self.latest_meta_path = self.base_dir / "new_raw" / "latest_meta.json"
        self.meteo_base_dir = EXPORT_SETTINGS.meteo_data_root
        self.output_root = EXPORT_SETTINGS.layer2_root
        self.source_stores = [
            SourceStore(
                name="firebase",
                history_root=self.history_root,
                latest_payload_path=self.latest_payload_path,
                latest_meta_path=self.latest_meta_path,
            ),
            SourceStore(
                name="meteo",
                history_root=self.meteo_base_dir / "history",
                latest_payload_path=self.meteo_base_dir / "new_raw" / "latest.json",
                latest_meta_path=self.meteo_base_dir / "new_raw" / "latest_meta.json",
            ),
        ]
        self.processors: list[Any] = [SHT30Processor(), NPKProcessor(), MeteoProcessor()]

    def run(self) -> Layer2Result:
        source_records = self._load_source_records()
        sensor_histories: dict[str, list[dict[str, Any]]] = {}
        sensor_states: dict[str, dict[str, Any]] = {}
        sensor_pending_rows: dict[str, list[dict[str, Any]]] = {}
        sensor_counts: dict[str, int] = {}
        processed_source_events: set[str] = set()
        filtered_out_records = 0

        for processor in self.processors:
            for source_record in source_records:
                sensor_id = processor.extract_sensor_id(source_record)
                if not sensor_id:
                    continue

                target_key = f"{processor.stream_name}/{sensor_id}"
                target_dir = self.output_root / processor.stream_name / sensor_id
                history_path = target_dir / "history.jsonl"
                state_path = target_dir / "state.json"

                if target_key not in sensor_histories:
                    sensor_histories[target_key] = read_jsonl(history_path)
                if target_key not in sensor_states:
                    sensor_states[target_key] = read_json(
                        state_path,
                        default=self._build_state_from_history(
                            processor=processor,
                            sensor_id=sensor_id,
                            history_rows=sensor_histories[target_key],
                        ),
                    )
                if target_key not in sensor_pending_rows:
                    sensor_pending_rows[target_key] = []
                    sensor_counts[target_key] = 0

                state = sensor_states[target_key]
                if not self._should_process_record(state=state, source_record=source_record):
                    continue

                if not self._source_record_is_accepted(processor=processor, source_record=source_record):
                    self._update_state_from_source_record(state=state, source_record=source_record)
                    processed_source_events.add(source_record.event_key)
                    filtered_out_records += 1
                    continue

                prior_history = sensor_histories[target_key] + sensor_pending_rows[target_key]
                snapshot = processor.build_snapshot(
                    source_record=source_record,
                    history_records=prior_history,
                )
                if not self._snapshot_is_accepted(snapshot):
                    self._update_state_from_source_record(state=state, source_record=source_record)
                    processed_source_events.add(source_record.event_key)
                    filtered_out_records += 1
                    continue

                sensor_pending_rows[target_key].append(snapshot)
                sensor_counts[target_key] += 1
                processed_source_events.add(source_record.event_key)
                self._update_state_from_snapshot(state=state, snapshot=snapshot)

        total_new_snapshots = 0
        for target_key, rows in sensor_pending_rows.items():
            if not rows:
                continue

            stream_name, sensor_id = target_key.split("/", maxsplit=1)
            target_dir = self.output_root / stream_name / sensor_id
            history_path = target_dir / "history.jsonl"
            latest_path = target_dir / "latest.json"
            state_path = target_dir / "state.json"

            total_new_snapshots += append_jsonl(history_path, rows)
            write_json(latest_path, rows[-1])
            write_json(state_path, sensor_states[target_key])

        manifest_payload: dict[str, Any] = {
            "schema_version": 1,
            "pipeline": "layer2_preprocessing",
            "ran_at_utc": iso_utc_now(),
            "source": {
                source_store.name: {
                    "history_root": str(source_store.history_root),
                    "latest_payload_path": str(source_store.latest_payload_path),
                    "latest_meta_path": str(source_store.latest_meta_path),
                }
                for source_store in self.source_stores
            },
            "processed_source_records": len(processed_source_events),
            "filtered_out_records": filtered_out_records,
            "total_new_snapshots": total_new_snapshots,
            "targets": sensor_counts,
        }
        manifest_path = self.output_root / "manifest.json"
        write_json(manifest_path, manifest_payload)

        return Layer2Result(
            status="ok",
            processed_source_records=len(processed_source_events),
            filtered_out_records=filtered_out_records,
            total_new_snapshots=total_new_snapshots,
            output_root=self.output_root,
            manifest_path=manifest_path,
            sensor_counts=sensor_counts,
        )

    def _load_source_records(self) -> list[SourceRecord]:
        records_by_event: dict[str, SourceRecord] = {}

        for source_store in self.source_stores:
            if source_store.history_root.exists():
                for history_file in sorted(source_store.history_root.rglob("*.json")):
                    raw_payload = read_json(history_file, default={})
                    source_record = self._from_history_payload(raw_payload)
                    if source_record is None:
                        continue
                    records_by_event[source_record.event_key] = source_record

            latest_payload = read_json(source_store.latest_payload_path, default=None)
            latest_meta = read_json(source_store.latest_meta_path, default=None)
            latest_record = self._from_latest_payload(
                latest_payload=latest_payload,
                latest_meta=latest_meta,
            )
            if latest_record is not None:
                records_by_event[latest_record.event_key] = latest_record

        return sorted(
            records_by_event.values(),
            key=lambda item: ((item.ts_hour_bucket or item.ts_server or 0), item.event_key),
        )

    def _from_history_payload(self, payload: dict[str, Any] | None) -> SourceRecord | None:
        if not isinstance(payload, dict):
            return None
        record = payload.get("record")
        if not isinstance(record, dict):
            return None
        event_key = str(payload.get("event_key") or "")
        date_key = str(payload.get("date_key") or "")
        source_path = str(payload.get("path") or "")
        if not event_key or not date_key:
            return None
        record_typed: dict[str, Any] = cast(dict[str, Any], record)
        return SourceRecord(
            event_key=event_key,
            date_key=date_key,
            source_kind="history",
            source_path=source_path,
            payload=record_typed,
            ts_server=safe_int(record_typed.get("ts_server")),
            ts_device=safe_int(record_typed.get("ts_device")),
            ts_hour_bucket=safe_int(record_typed.get("ts_hour_bucket"))
            or floor_ts_to_hour(safe_int(record_typed.get("ts_server"))),
        )

    def _from_latest_payload(
        self,
        latest_payload: dict[str, Any] | None,
        latest_meta: dict[str, Any] | None,
    ) -> SourceRecord | None:
        if not isinstance(latest_payload, dict) or not isinstance(latest_meta, dict):
            return None

        event_key = str(latest_meta.get("latest_event_key") or "")
        date_key = str(latest_meta.get("latest_date_key") or "")
        source_path = str(latest_meta.get("latest_path") or "")
        if not event_key or not date_key:
            return None

        return SourceRecord(
            event_key=event_key,
            date_key=date_key,
            source_kind="latest",
            source_path=source_path,
            payload=latest_payload,
            ts_server=safe_int(latest_payload.get("ts_server")),
            ts_device=safe_int(latest_payload.get("ts_device")),
            ts_hour_bucket=safe_int(latest_payload.get("ts_hour_bucket"))
            or floor_ts_to_hour(safe_int(latest_payload.get("ts_server"))),
        )

    def _build_default_state(self, processor: Any, sensor_id: str) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "processor_name": processor.processor_name,
            "sensor_id": sensor_id,
            "last_processed_server_ts": None,
            "last_processed_event_key": None,
            "processed_record_count": 0,
            "recent_record_ids": [],
            "last_updated_utc": None,
        }

    def _build_state_from_history(
        self,
        processor: Any,
        sensor_id: str,
        history_rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        state = self._build_default_state(processor=processor, sensor_id=sensor_id)
        if not history_rows:
            return state

        last_row = history_rows[-1]
        timestamps = last_row.get("timestamps", {})
        source = last_row.get("source", {})
        state["last_processed_server_ts"] = timestamps.get("ts_server")
        state["last_processed_event_key"] = source.get("event_key")
        state["processed_record_count"] = len(history_rows)
        state["recent_record_ids"] = trim_recent_ids(
            [
                str(row.get("source", {}).get("event_key"))
                for row in history_rows
                if row.get("source", {}).get("event_key")
            ]
        )
        state["last_updated_utc"] = iso_utc_now()
        return state

    def _should_process_record(self, state: dict[str, Any], source_record: SourceRecord) -> bool:
        recent_ids = set(state.get("recent_record_ids") or [])
        record_id = source_record.event_key
        current_ts = source_record.ts_server or -1
        last_ts = safe_int(state.get("last_processed_server_ts"))
        last_event_key = str(state.get("last_processed_event_key") or "")

        if record_id in recent_ids:
            return False
        if last_ts is None:
            return True
        if current_ts > last_ts:
            return True
        if current_ts == last_ts and source_record.event_key > last_event_key:
            return True
        return False

    def _source_record_is_accepted(self, processor: Any, source_record: SourceRecord) -> bool:
        predicate = cast(Callable[[SourceRecord], bool] | None, getattr(processor, "should_accept_source_record", None))
        if predicate is None:
            return True
        return bool(predicate(source_record))

    def _snapshot_is_accepted(self, snapshot: dict[str, Any]) -> bool:
        health = snapshot.get("health", {})
        handoff = snapshot.get("handoff", {})
        if health.get("status") == "fault":
            return False
        if handoff.get("ready") is False:
            return False
        return True

    def _update_state_from_snapshot(self, state: dict[str, Any], snapshot: dict[str, Any]) -> None:
        timestamps = snapshot.get("timestamps", {})
        source = snapshot.get("source", {})
        state["last_processed_server_ts"] = timestamps.get("ts_server")
        state["last_processed_event_key"] = source.get("event_key")
        state["processed_record_count"] = int(state.get("processed_record_count", 0)) + 1
        recent_ids = list(state.get("recent_record_ids") or [])
        recent_ids.append(str(source.get("event_key")))
        state["recent_record_ids"] = trim_recent_ids(recent_ids)
        state["last_updated_utc"] = iso_utc_now()

    def _update_state_from_source_record(self, state: dict[str, Any], source_record: SourceRecord) -> None:
        state["last_processed_server_ts"] = source_record.ts_server
        state["last_processed_event_key"] = source_record.event_key
        state["processed_record_count"] = int(state.get("processed_record_count", 0)) + 1
        recent_ids = list(state.get("recent_record_ids") or [])
        recent_ids.append(source_record.event_key)
        state["recent_record_ids"] = trim_recent_ids(recent_ids)
        state["last_updated_utc"] = iso_utc_now()
