from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from Config.runtime import BACKEND_SETTINGS
except ModuleNotFoundError:
    from ....Config.runtime import BACKEND_SETTINGS

from ...utils.common import safe_int
from ...utils.storage import read_json
from ..contracts import SourceRecord


class FirebaseSourceLoader:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir.resolve()
        self.history_root = self.base_dir / "history"
        self.latest_payload_path = self.base_dir / "new_raw" / "latest.json"
        self.latest_meta_path = self.base_dir / "new_raw" / "latest_meta.json"

    def load(self) -> list[SourceRecord]:
        records_by_id: dict[str, SourceRecord] = {}

        if self.history_root.exists():
            for history_file in sorted(self.history_root.rglob("*.json")):
                payload = read_json(history_file, default={})
                source_record = self._from_history_payload(payload)
                if source_record is None:
                    continue
                records_by_id[self._source_event_id(source_record)] = source_record

        latest_payload = read_json(self.latest_payload_path, default=None)
        latest_meta = read_json(self.latest_meta_path, default=None)
        latest_record = self._from_latest_payload(latest_payload, latest_meta)
        if latest_record is not None:
            records_by_id[self._source_event_id(latest_record)] = latest_record

        return sorted(
            records_by_id.values(),
            key=lambda item: (
                safe_int(item.payload.get("ts_sample")) or safe_int(item.payload.get("ts_server")) or -1,
                item.event_key,
            ),
        )

    def _from_history_payload(self, payload: dict[str, Any] | None) -> SourceRecord | None:
        if not isinstance(payload, dict):
            return None
        record_payload = payload.get("record")
        event_key = payload.get("event_key")
        date_key = payload.get("date_key")
        source_path = payload.get("path")
        if not isinstance(record_payload, dict) or not event_key or not date_key:
            return None
        return SourceRecord(
            source_name="firebase",
            event_key=str(event_key),
            date_key=str(date_key),
            source_kind="history",
            source_path=str(source_path or ""),
            payload=record_payload,
        )

    def _from_latest_payload(
        self,
        latest_payload: dict[str, Any] | None,
        latest_meta: dict[str, Any] | None,
    ) -> SourceRecord | None:
        if not isinstance(latest_payload, dict) or not isinstance(latest_meta, dict):
            return None
        event_key = latest_meta.get("latest_event_key")
        date_key = latest_meta.get("latest_date_key")
        source_path = latest_meta.get("latest_path")
        if not event_key or not date_key:
            return None
        return SourceRecord(
            source_name="firebase",
            event_key=str(event_key),
            date_key=str(date_key),
            source_kind="latest",
            source_path=str(source_path or ""),
            payload=latest_payload,
        )

    def _source_event_id(self, source_record: SourceRecord) -> str:
        return (
            f"{source_record.source_name}/"
            f"{source_record.date_key}/"
            f"{source_record.event_key}"
        )
