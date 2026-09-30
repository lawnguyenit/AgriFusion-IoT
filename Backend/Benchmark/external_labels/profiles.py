from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TargetSpec:
    target_id: str
    measurement_column: str
    tail_direction: str
    positive_label: str


@dataclass(frozen=True)
class ExternalLabelProfile:
    dataset_id: str
    timestamp_column: str
    group_columns: tuple[str, ...]
    targets: tuple[TargetSpec, ...]


PROFILES = {
    "stuard_tomato_irrigation_2023": ExternalLabelProfile(
        dataset_id="stuard_tomato_irrigation_2023",
        timestamp_column="timestamp",
        group_columns=("entity_id",),
        targets=(
            TargetSpec(
                target_id="soil_moisture_low",
                measurement_column="soil_moisture_pct",
                tail_direction="lower",
                positive_label="LOW_MOISTURE",
            ),
        ),
    ),
    "uci_air_quality_360": ExternalLabelProfile(
        dataset_id="uci_air_quality_360",
        timestamp_column="timestamp",
        group_columns=(),
        targets=(
            TargetSpec("co", "sensor.co", "upper", "CO"),
            TargetSpec("nox", "sensor.nox", "upper", "NOX"),
        ),
    ),
}


def resolve_profile(dataset_id: str) -> ExternalLabelProfile:
    try:
        return PROFILES[dataset_id]
    except KeyError as exc:
        raise ValueError(f"No external label profile is registered for {dataset_id!r}.") from exc
