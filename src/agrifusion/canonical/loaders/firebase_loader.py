from __future__ import annotations

from pathlib import Path
from typing import Any

from agrifusion.ingest.record_store import RecordStoreReader, read_latest
from agrifusion.io.common import safe_int
from agrifusion.settings.runtime import DEFAULT_TIMEZONE_NAME
from ..adapters import AdapterConfig, FirmwareRecordAdapter
from ..contracts import SourceRecord


def _default_adapter() -> FirmwareRecordAdapter:
    from zoneinfo import ZoneInfo

    return FirmwareRecordAdapter(AdapterConfig(timezone=ZoneInfo(DEFAULT_TIMEZONE_NAME)))


class FirebaseSourceLoader:
    """Load ingest's raw records and adapt them to canonical row inputs.

    Reads ingest's on-disk store only through ``agrifusion.ingest.record_store``
    (``RecordStoreReader`` + ``read_latest``). Every record, from disk or from
    ``from_payloads``, goes through ``FirmwareRecordAdapter`` before it reaches the
    row builder. ``source_kind`` is ``"history"`` for store records and ``"latest"``
    for ``new_raw/latest.json`` (the canonical ``record.source_kind`` values).
    """

    def __init__(
        self,
        base_dir: Path,
        *,
        node_id: str | None = None,
        history_payload: dict[str, Any] | None = None,
        latest_payload: dict[str, Any] | None = None,
        latest_meta: dict[str, Any] | None = None,
        adapter: FirmwareRecordAdapter | None = None,
    ):
        self.base_dir = base_dir.resolve()
        self.node_id = node_id
        self.adapter = adapter or _default_adapter()
        self._history_payload = history_payload
        self._latest_payload = latest_payload
        self._latest_meta = latest_meta

    @classmethod
    def from_payloads(
        cls,
        *,
        base_dir: Path,
        node_id: str,
        history_payload: dict[str, Any] | None,
        latest_payload: dict[str, Any] | None,
        latest_meta: dict[str, Any] | None,
        adapter: FirmwareRecordAdapter | None = None,
    ) -> "FirebaseSourceLoader":
        """In-memory raw records (same shape as the source telemetry), for tests/tools."""
        return cls(
            base_dir=base_dir,
            node_id=node_id,
            history_payload=history_payload,
            latest_payload=latest_payload,
            latest_meta=latest_meta,
            adapter=adapter,
        )

    def load(self) -> list[SourceRecord]:
        records_by_id: dict[str, SourceRecord] = {}

        if isinstance(self._history_payload, dict):
            self._load_history_payload(records_by_id)
        else:
            for stored in RecordStoreReader(self.base_dir).iter_current():
                source_record = SourceRecord(
                    source_name="firebase",
                    event_key=stored.event_key,
                    date_key=stored.date_key,
                    source_kind="history",
                    source_path=stored.source_path,
                    payload=self.adapter.adapt(stored.record),
                )
                records_by_id[self._source_event_id(source_record)] = source_record

        disk_latest, disk_meta = (None, None)
        if self._latest_payload is None or self._latest_meta is None:
            disk_latest, disk_meta = read_latest(self.base_dir)
        latest_payload = self._latest_payload if self._latest_payload is not None else disk_latest
        latest_meta = self._latest_meta if self._latest_meta is not None else disk_meta
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

    def _load_history_payload(self, records_by_id: dict[str, SourceRecord]) -> None:
        assert isinstance(self._history_payload, dict)
        if not self.node_id:
            raise ValueError("node_id is required to load an in-memory history payload")
        for date_key, day_payload in sorted(self._history_payload.items(), key=lambda item: str(item[0])):
            if not isinstance(day_payload, dict):
                continue
            for event_key, record_payload in sorted(day_payload.items(), key=lambda item: str(item[0])):
                if not isinstance(record_payload, dict):
                    continue
                source_record = SourceRecord(
                    source_name="firebase",
                    event_key=str(event_key),
                    date_key=str(date_key),
                    source_kind="history",
                    source_path=f"{self.node_id}/telemetry/{date_key}/{event_key}",
                    payload=self.adapter.adapt(record_payload),
                )
                records_by_id[self._source_event_id(source_record)] = source_record

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
            payload=self.adapter.adapt(latest_payload),
        )

    def _source_event_id(self, source_record: SourceRecord) -> str:
        return (
            f"{source_record.source_name}/"
            f"{source_record.date_key}/"
            f"{source_record.event_key}"
        )
