from __future__ import annotations

import json
from pathlib import Path

from ..contracts.telemetry_record import TelemetrySeedRecord


def load_layer0_seed_records(layer0_history_root: Path, *, limit: int | None = None) -> list[TelemetrySeedRecord]:
    files = sorted(layer0_history_root.rglob("*.json"))
    if limit is not None and limit > 0:
        files = files[-limit:]

    records: list[TelemetrySeedRecord] = []
    for path in files:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        record_payload = payload.get("record")
        if not isinstance(record_payload, dict):
            continue
        records.append(
            TelemetrySeedRecord(
                event_key=str(payload.get("event_key") or ""),
                date_key=str(payload.get("date_key") or ""),
                path=str(payload.get("path") or ""),
                synced_at_utc=str(payload.get("synced_at_utc") or ""),
                record=record_payload,
            )
        )

    records.sort(key=lambda item: int(item.record.get("ts_server") or 0))
    return records
