from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TargetSpec:
    target_id: str
    measurement_column: str
    tail_direction: str
    positive_label: str
    evidence_kind: str = "SENSOR_MEASUREMENT_WEAK_LABEL"
    input_feature_candidates: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExternalLabelProfile:
    dataset_id: str
    timestamp_column: str
    group_columns: tuple[str, ...]
    targets: tuple[TargetSpec, ...]
    scope_end_exclusive: str | None = None
    default_tau_minutes: tuple[int, ...] = ()
    tau_basis: str = "No domain-specific duration basis registered."
    tau_sources: tuple[str, ...] = ()


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
                input_feature_candidates=("soil_moisture_pct",),
            ),
        ),
        default_tau_minutes=(1440, 2880, 8640),
        tau_basis=(
            "Tomato field studies report soil-water-stress onset indications 1, 2, "
            "and 6 days after stress onset across drying cycles. These are exploratory "
            "persistence candidates, not a cultivar- or site-specific biological cutoff."
        ),
        tau_sources=("https://doi.org/10.1016/j.agwat.2007.04.009",),
    ),
    "uci_air_quality_360": ExternalLabelProfile(
        dataset_id="uci_air_quality_360",
        timestamp_column="timestamp",
        group_columns=(),
        targets=(
            TargetSpec(
                "co",
                "criterion.co_gt_mg_m3",
                "upper",
                "CO",
                evidence_kind="CERTIFIED_REFERENCE_CRITERION",
                input_feature_candidates=("sensor.co",),
            ),
            TargetSpec(
                "nox",
                "criterion.nox_gt_ppb",
                "upper",
                "NOX",
                evidence_kind="CERTIFIED_REFERENCE_CRITERION",
                input_feature_candidates=("sensor.nox",),
            ),
        ),
        scope_end_exclusive="2005-03-01T00:00:00",
        default_tau_minutes=(60, 120, 240),
        tau_basis=(
            "The data are hourly. An urban CO/NO2 episode study analyzes continuous "
            "threshold-exceedance durations from hourly measurements; it supports treating "
            "duration as part of an event, but does not establish a universal cutoff for this "
            "site or total NOx. Retain 1/2/4-hour horizons as sensitivity candidates (K=1/2/4 "
            "at this cadence), not as biological or regulatory thresholds."
        ),
        tau_sources=(
            "https://archive.ics.uci.edu/dataset/360/air",
            "https://doi.org/10.1016/S1352-2310(98)00019-3",
        ),
    ),
}


def resolve_profile(dataset_id: str) -> ExternalLabelProfile:
    try:
        return PROFILES[dataset_id]
    except KeyError as exc:
        raise ValueError(f"No external label profile is registered for {dataset_id!r}.") from exc
