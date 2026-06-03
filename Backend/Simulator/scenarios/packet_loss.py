from __future__ import annotations

from .base import Scenario, ScenarioContext


class PacketLossScenario(Scenario):
    name = "packet_loss"

    def mutate(self, row: dict, context: ScenarioContext) -> dict:
        return row
