from __future__ import annotations

from .base import Scenario, ScenarioContext


class WaterDeficitScenario(Scenario):
    name = "water_deficit"

    def applies_to_hour(self, local_hour: int) -> bool:
        return 9 <= local_hour < 17

    def mutate(self, row: dict, context: ScenarioContext) -> dict:
        strength = context.effect_strength
        dry_drop = (1.2 + 11.0 * context.intensity) * strength
        ec_rise = (4.0 + 38.0 * context.intensity) * strength
        air_temp_rise = (0.2 + 2.0 * context.intensity) * strength
        air_humidity_drop = (0.8 + 6.5 * context.intensity) * strength

        row["soil_humidity"] = round(max(8.0, float(row["soil_humidity"]) - dry_drop), 2)
        row["EC"] = round(float(row["EC"]) + ec_rise, 1)
        row["air_temp"] = round(float(row["air_temp"]) + air_temp_rise, 2)
        row["air_humidity"] = round(max(20.0, float(row["air_humidity"]) - air_humidity_drop), 2)
        return row
