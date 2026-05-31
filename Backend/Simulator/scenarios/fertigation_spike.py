from __future__ import annotations

from .base import Scenario, ScenarioContext


class FertigationSpikeScenario(Scenario):
    name = "fertigation_spike"

    def applies_to_hour(self, local_hour: int) -> bool:
        return 5 <= local_hour < 8

    def mutate(self, row: dict, context: ScenarioContext) -> dict:
        strength = context.effect_strength
        base_bump = (12.0 + 30.0 * context.intensity) * strength

        row["air_humidity"] = round(min(99.99, float(row["air_humidity"]) + (8.0 + 18.0 * context.intensity) * strength), 2)
        row["air_temp"] = round(max(18.0, float(row["air_temp"]) - (0.2 + 0.8 * strength)), 2)
        row["soil_humidity"] = round(min(99.99, float(row["soil_humidity"]) + (1.5 + 8.0 * context.intensity) * strength), 2)
        row["N"] = round(float(row["N"]) + base_bump, 1)
        row["P"] = round(float(row["P"]) + base_bump * 2.1, 1)
        row["K"] = round(float(row["K"]) + base_bump * 1.8, 1)
        row["EC"] = round(float(row["EC"]) + (18.0 + 72.0 * context.intensity) * strength, 1)
        row["pH"] = round(max(3.5, min(9.0, float(row["pH"]) - 0.12 * context.intensity * strength)), 2)
        return row
