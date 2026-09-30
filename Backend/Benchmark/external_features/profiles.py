from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExternalFeatureProfile:
    dataset_id: str
    timestamp_column: str
    group_columns: tuple[str, ...]
    value_columns: tuple[str, ...]
    scope_end_exclusive: str | None = None


def resolve_profile(dataset_id: str, run_manifest: dict[str, object]) -> ExternalFeatureProfile:
    if dataset_id == "stuard_tomato_irrigation_2023":
        return ExternalFeatureProfile(
            dataset_id=dataset_id,
            timestamp_column="timestamp",
            group_columns=("entity_id",),
            value_columns=(
                "soil_moisture_pct", "soil_temperature_c", "soil_ec_us_cm",
                "air_temperature_c", "air_humidity_pct", "air_co2_ppm", "air_pressure_hpa",
            ),
        )
    if dataset_id == "uci_air_quality_360":
        return ExternalFeatureProfile(
            dataset_id=dataset_id,
            timestamp_column="timestamp",
            group_columns=(),
            value_columns=(
                "sensor.co", "sensor.nmhc", "sensor.nox", "sensor.no2", "sensor.o3",
                "context.temperature_c", "context.relative_humidity_pct", "context.absolute_humidity",
            ),
            scope_end_exclusive="2005-03-01T00:00:00",
        )
    raise ValueError(f"No external feature profile is registered for {dataset_id!r}.")
