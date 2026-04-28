from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, cast

try:
    from Services.config.settings import SETTINGS as EXPORT_SETTINGS
except ModuleNotFoundError:
    from ...Services.config.settings import SETTINGS as EXPORT_SETTINGS

from ..processors.meteo import MeteoProcessor
from ..processors.npk import NPKProcessor
from ..processors.sht30 import SHT30Processor
from ..contracts import LAYER2_SCHEMA_VERSION
from ..utils.common import floor_ts_to_hour, iso_utc_now, safe_int, trim_recent_ids
from ..utils.storage import append_jsonl, read_json, read_jsonl, write_json


@dataclass(frozen=True)
class SourceRecord:
    source_name: str
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


@dataclass(frozen=True)
class Layer2Target:
    key: str
    stream_name: str
    sensor_id: str
    history_path: Path
    latest_path: Path
    state_path: Path


@dataclass
class Layer2RunState:
    sensor_histories: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    sensor_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    sensor_pending_rows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    sensor_counts: dict[str, int] = field(default_factory=dict)
    touched_targets: set[str] = field(default_factory=set)
    processed_source_events: set[str] = field(default_factory=set)
    filtered_out_records: int = 0


class PreprocessingPipeline:
    def __init__(
        self,
        base_dir: Path | None = None,
        meteo_base_dir: Path | None = None,
        output_root: Path | None = None,
    ):
        self.base_dir = base_dir or EXPORT_SETTINGS.base_dir
        self.history_root = self.base_dir / "history"
        self.latest_payload_path = self.base_dir / "new_raw" / "latest.json"
        self.latest_meta_path = self.base_dir / "new_raw" / "latest_meta.json"
        self.meteo_base_dir = meteo_base_dir or EXPORT_SETTINGS.meteo_data_root
        self.output_root = output_root or EXPORT_SETTINGS.layer2_root
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
        # 1. Tải tất cả bản ghi mới nhất và lịch sử và hợp nhất lại
        source_records = self._load_source_records()
        run_state = Layer2RunState()

        # 2. Lặp qua từng bộ và xử lý chính 
        for processor in self.processors:
            for source_record in source_records:
                self._process_source_record(
                    processor=processor,
                    source_record=source_record,
                    run_state=run_state,
                )

        # 3. Ghi lại tất cả trạng thái mục tiêu đã xử lí
        total_new_snapshots = self._persist_targets(run_state)

        # 4. Ghi manifest cuối cùng với tất cả thông tin meta về lần chạy này
        manifest_path = self._write_manifest(
            run_state=run_state,
            total_new_snapshots=total_new_snapshots,
        )

        return Layer2Result(
            status="ok",
            processed_source_records=len(run_state.processed_source_events),
            filtered_out_records=run_state.filtered_out_records,
            total_new_snapshots=total_new_snapshots,
            output_root=self.output_root,
            manifest_path=manifest_path,
            sensor_counts=run_state.sensor_counts,
        )

    def _process_source_record(
        self,
        processor: Any,
        source_record: SourceRecord,
        run_state: Layer2RunState,
    ) -> None:
        
        """
            processor là một bộ xử lí cụ thể (ví dụ: SHT30Processor).
            source_record là một bản ghi nguồn duy nhất được trích xuất từ các nguồn dữ liệu (có thể là từ Firebase hoặc dữ liệu thời tiết).
            run_state là trạng thái hiện tại của lần chạy, bao gồm lịch sử đã tải, trạng thái đã tải, các bản ghi đang chờ xử lý, và thống kê về số lượng

            Luồng chính là build_snapshot
            return của build_snapshot sẽ được đánh giá qua _snapshot_is_accepted để quyết định có nên lưu lại hay không, nếu không sẽ bị đánh dấu là đã lọc ra và cập nhật trạng thái tương ứng.
        """
        sensor_id = processor.extract_sensor_id(source_record)
        if not sensor_id:
            return

        # Xây dựng mục tiêu tương ứng cho bộ xử lý và cảm biến này, 
        # đảm bảo trạng thái đã được tải nếu chưa có, và lấy trạng thái đó ra để sử dụng.

        target = self._build_target(processor=processor, sensor_id=sensor_id)
        self._ensure_target_loaded(processor=processor, target=target, run_state=run_state)
        state = run_state.sensor_states[target.key]

        if not self._should_process_record(state=state, source_record=source_record):
            return

        if not self._source_record_is_accepted(processor=processor, source_record=source_record):
            self._mark_filtered_record(
                state=state,
                source_record=source_record,
                target_key=target.key,
                run_state=run_state,
            )
            return
        
        prior_history = run_state.sensor_histories[target.key] + run_state.sensor_pending_rows[target.key]
        
        #Luồng hoạt động chính
        snapshot = processor.build_snapshot(
            source_record=source_record,
            history_records=prior_history,
        )
        if not self._snapshot_is_accepted(snapshot):
            self._mark_filtered_record(
                state=state,
                source_record=source_record,
                target_key=target.key,
                run_state=run_state,
            )
            return

        run_state.sensor_pending_rows[target.key].append(snapshot)
        run_state.sensor_counts[target.key] += 1
        run_state.processed_source_events.add(self._source_event_id(source_record))
        run_state.touched_targets.add(target.key)
        self._update_state_from_snapshot(state=state, snapshot=snapshot)

    def _build_target(self, processor: Any, sensor_id: str) -> Layer2Target:
        stream_name = processor.stream_name
        target_dir = self.output_root / stream_name / sensor_id
        key = f"{stream_name}/{sensor_id}"
        return Layer2Target(
            key=key,
            stream_name=stream_name,
            sensor_id=sensor_id,
            history_path=target_dir / "history.jsonl",
            latest_path=target_dir / "latest.json",
            state_path=target_dir / "state.json",
        )

    def _ensure_target_loaded(
        self,
        processor: Any,
        target: Layer2Target,
        run_state: Layer2RunState,
    ) -> None:
        if target.key not in run_state.sensor_histories:
            run_state.sensor_histories[target.key] = read_jsonl(target.history_path)
        if target.key not in run_state.sensor_states:
            run_state.sensor_states[target.key] = read_json(
                target.state_path,
                default=self._build_state_from_history(
                    processor=processor,
                    sensor_id=target.sensor_id,
                    history_rows=run_state.sensor_histories[target.key],
                ),
            )
        if target.key not in run_state.sensor_pending_rows:
            run_state.sensor_pending_rows[target.key] = []
            run_state.sensor_counts[target.key] = 0

    def _mark_filtered_record(
        self,
        state: dict[str, Any],
        source_record: SourceRecord,
        target_key: str,
        run_state: Layer2RunState,
    ) -> None:
        
        """
        hàm này được gọi khi một bản ghi nguồn không vượt qua được các tiêu chí chấp nhận, 
        để cập nhật trạng thái mục tiêu tương ứng và thống kê số lượng bản ghi bị lọc ra.
        """
        self._update_state_from_source_record(state=state, source_record=source_record)
        run_state.processed_source_events.add(self._source_event_id(source_record))
        run_state.touched_targets.add(target_key)
        run_state.filtered_out_records += 1

    def _persist_targets(self, run_state: Layer2RunState) -> int:
        
        """Ghi lại tất cả trạng thái mục tiêu đã chạm và bất kỳ snapshot mới nào được xây dựng."""

        total_new_snapshots = 0

        for target_key in sorted(run_state.touched_targets):
            stream_name, sensor_id = target_key.split("/", maxsplit=1)
            target_dir = self.output_root / stream_name / sensor_id
            rows = run_state.sensor_pending_rows.get(target_key, [])

            if rows:
                total_new_snapshots += append_jsonl(target_dir / "history.jsonl", rows)
                write_json(target_dir / "latest.json", rows[-1])

            write_json(target_dir / "state.json", run_state.sensor_states[target_key])

        return total_new_snapshots

    def _write_manifest(self, run_state: Layer2RunState, total_new_snapshots: int) -> Path:
        manifest_payload: dict[str, Any] = {
            "schema_version": LAYER2_SCHEMA_VERSION,
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
            "processed_source_records": len(run_state.processed_source_events),
            "filtered_out_records": run_state.filtered_out_records,
            "total_new_snapshots": total_new_snapshots,
            "targets": run_state.sensor_counts,
        }
        manifest_path = self.output_root / "manifest.json"
        write_json(manifest_path, manifest_payload)
        return manifest_path

    def _load_source_records(self) -> list[SourceRecord]:
        """
        Trả về danh sách được sắp xếp ở dạng SourceRecord, 
        được tổng hợp từ cả payload mới nhất và lịch sử của tất cả các nguồn đã cấu hình.
        """

        records_by_event: dict[str, SourceRecord] = {}

        for source_store in self.source_stores:
            if source_store.history_root.exists():
                for history_file in sorted(source_store.history_root.rglob("*.json")):
                    raw_payload = read_json(history_file, default={})
                    source_record = self._from_history_payload(
                        payload=raw_payload,
                        source_name=source_store.name,
                    )
                    if source_record is None:
                        continue
                    records_by_event[self._source_event_id(source_record)] = source_record

            latest_payload = read_json(source_store.latest_payload_path, default=None)
            latest_meta = read_json(source_store.latest_meta_path, default=None)
            latest_record = self._from_latest_payload(
                latest_payload=latest_payload,
                latest_meta=latest_meta,
                source_name=source_store.name,
            )
            if latest_record is not None:
                records_by_event[self._source_event_id(latest_record)] = latest_record

        return sorted(
            records_by_event.values(),
            key=lambda item: ((item.ts_hour_bucket or item.ts_server or 0), item.event_key),
        )

    def _from_history_payload(
        self,
        payload: dict[str, Any] | None,
        source_name: str,
    ) -> SourceRecord | None:
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
            source_name=source_name,
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
        source_name: str,
    ) -> SourceRecord | None:
        if not isinstance(latest_payload, dict) or not isinstance(latest_meta, dict):
            return None

        event_key = str(latest_meta.get("latest_event_key") or "")
        date_key = str(latest_meta.get("latest_date_key") or "")
        source_path = str(latest_meta.get("latest_path") or "")
        if not event_key or not date_key:
            return None

        return SourceRecord(
            source_name=source_name,
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
        """
        Xây dựng trạng thái mục tiêu ban đầu từ lịch sử đã có, để lần chạy này có thể tiếp tục từ trạng thái đó.
        """

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

    def _source_event_id(self, source_record: SourceRecord) -> str:
        return f"{source_record.source_name}/{source_record.date_key}/{source_record.event_key}"

    def _source_record_is_accepted(self, processor: Any, source_record: SourceRecord) -> bool:
        predicate = cast(
            Callable[[SourceRecord], bool] | None,
            getattr(processor, "should_accept_source_record", None),
        )
        if predicate is None:
            return True
        return bool(predicate(source_record))

    def _snapshot_is_accepted(self, snapshot: dict[str, Any]) -> bool:
        timestamps = snapshot.get("timestamps", {})
        perception = snapshot.get("perception", {})
        if safe_int(timestamps.get("ts_hour_bucket")) is None and safe_int(timestamps.get("ts_server")) is None:
            return False
        if not isinstance(perception, dict) or not perception:
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
