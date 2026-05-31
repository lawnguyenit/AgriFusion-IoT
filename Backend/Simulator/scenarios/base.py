from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


@dataclass(frozen=True)
class ScenarioSpec:
    name: str
    count: int
    intensity: float = 1.0


@dataclass(frozen=True)
class ScenarioContext:
    row_index: int
    row_count: int
    scenario_progress: float
    effect_strength: float
    phase_name: str
    intensity: float
    interval_seconds: int
    timestamp: int

    @property
    def local_datetime(self) -> datetime:
        return datetime.utcfromtimestamp(self.timestamp) + timedelta(hours=7)

    @property
    def local_hour(self) -> int:
        return self.local_datetime.hour


class Scenario:
    name = "base"

    def applies_to_hour(self, local_hour: int) -> bool:
        return True

    def mutate(self, row: dict[str, Any], context: ScenarioContext) -> dict[str, Any]:
        return row
