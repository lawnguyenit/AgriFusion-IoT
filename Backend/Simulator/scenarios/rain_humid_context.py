from __future__ import annotations

from .base import Scenario, ScenarioContext


class RainHumidContextScenario(Scenario):
    name = "rain_humid_context"

    def applies_to_hour(self, local_hour: int) -> bool:
        return local_hour >= 18 or local_hour <= 9

    def mutate(self, row: dict, context: ScenarioContext) -> dict:
        strength = context.effect_strength
        cool_down = (0.6 + 2.8 * context.intensity) * strength
        humidity_lift = (6.0 + 18.0 * context.intensity) * strength
        soil_lift = (0.5 + 4.0 * context.intensity) * strength

        row["air_temp"] = round(max(18.0, float(row["air_temp"]) - cool_down), 2)
        row["air_humidity"] = round(min(99.99, float(row["air_humidity"]) + humidity_lift), 2)
        row["soil_humidity"] = round(min(99.99, float(row["soil_humidity"]) + soil_lift), 2)
        row["soil_temp"] = round(max(16.0, float(row["soil_temp"]) - 0.2 - 0.5 * strength), 2)
        return row
