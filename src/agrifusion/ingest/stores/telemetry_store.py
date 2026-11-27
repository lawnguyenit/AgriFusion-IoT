"""Write source records into the raw record store (see ``agrifusion.ingest.record_store``)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from agrifusion.settings.runtime import BackendSettings

from ..record_store import SOURCE_KIND_TELEMETRY, PutResult, RecordStoreWriter


@dataclass
class StoreCounts:
    eligible_record_count: int = 0
    new_file_count: int = 0
    new_version_count: int = 0

    def add(self, result: PutResult) -> None:
        self.eligible_record_count += 1
        self.new_file_count += int(result.new_file)
        self.new_version_count += int(result.new_version)


def open_record_store(settings: BackendSettings) -> RecordStoreWriter:
    return RecordStoreWriter(settings.firebase_layer0_root, node_slug=settings.node_slug)


def store_telemetry_records(
    *,
    store: RecordStoreWriter,
    settings: BackendSettings,
    telemetry_payload: dict[str, Any],
    start_date: date | None = None,
    end_date: date | None = None,
) -> StoreCounts:
    """Store every ``telemetry/<date>/<event>`` record verbatim (date window inclusive)."""
    counts = StoreCounts()
    for date_key, day_payload in telemetry_payload.items():
        if not isinstance(day_payload, dict):
            continue
        try:
            current_date = date.fromisoformat(str(date_key))
        except ValueError:
            continue
        if start_date is not None and current_date < start_date:
            continue
        if end_date is not None and current_date > end_date:
            continue
        for event_key, record_payload in day_payload.items():
            if not isinstance(record_payload, dict):
                continue
            counts.add(
                store.put(
                    date_key=str(date_key),
                    event_key=str(event_key),
                    source_kind=SOURCE_KIND_TELEMETRY,
                    source_path=f"{settings.telemetry_root_path}/{date_key}/{event_key}",
                    record=record_payload,
                )
            )
    return counts
