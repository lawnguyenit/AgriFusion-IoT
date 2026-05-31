from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TelemetrySeedRecord:
    event_key: str
    date_key: str
    path: str
    synced_at_utc: str
    record: dict[str, Any]
