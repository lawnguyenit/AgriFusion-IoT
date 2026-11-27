"""Registry of external datasets: one DatasetProfile per dataset_id.

Every per-dataset choice of the external lanes (sources, metadata, intake adapter, feature
columns, label targets and the policy text written into manifests) is declared here, so lane
code never branches on a dataset_id literal. Adding a dataset = adding one DatasetProfile and,
if its raw format is new, one adapter in external/intake/adapters/.

Run-id prefixes (external_intake_<dataset_id>_..., external_features_..., external_labels_...)
are unchanged, so artifacts written before GD5 keep their lineage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .profile_types import ExternalFeatureProfile, ExternalLabelProfile, SourceFileSpec, TargetSpec


@dataclass(frozen=True)
class DatasetProfile:
    dataset_id: str
    intake_adapter: str  # key in external.intake.adapters.ADAPTERS
    source_files: tuple[SourceFileSpec, ...]
    metadata: Mapping[str, str] = field(compare=False)
    features: ExternalFeatureProfile
    labels: ExternalLabelProfile
    intake_report_notes: tuple[str, ...] = ()


REGISTRY: dict[str, DatasetProfile] = {
    "stuard_tomato_irrigation_2023": DatasetProfile(
        dataset_id="stuard_tomato_irrigation_2023",
        intake_adapter="stuard",
        source_files=(
            SourceFileSpec(
                "stuard_environmental_data.csv",
                "https://data.mendeley.com/public-files/datasets/35wh56287y/files/a7e4beec-ca68-459b-8574-dc1bf99214dd/file_downloaded",
            ),
            SourceFileSpec(
                "stuard_soil_data.csv",
                "https://data.mendeley.com/public-files/datasets/35wh56287y/files/9cc5e9d8-a54a-488b-80db-35896156e56e/file_downloaded",
            ),
            SourceFileSpec(
                "stuard_water_meter_data.csv",
                "https://data.mendeley.com/public-files/datasets/35wh56287y/files/bd227cef-4611-47c6-9dcd-ca693be36594/file_downloaded",
            ),
        ),
        metadata={
            "title": "IoT-based Dataset of a Tomato Cultivation Under Different Irrigation Regimes",
            "version": "2",
            "doi": "10.17632/35wh56287y.2",
            "article_doi": "10.1016/j.dib.2025.111521",
            "official_landing_page": "https://data.mendeley.com/datasets/35wh56287y/2",
            "license": "CC BY 4.0",
            "citation": "Belli, L., Davoli, L., Oddi, G., Preite, L., Galaverni, M., Ganino, T., & Ferrari, G. (2024). IoT-based Dataset of a Tomato Cultivation Under Different Irrigation Regimes (Version 2) [Data set]. Mendeley Data. https://doi.org/10.17632/35wh56287y.2",
            "source_copy_url": "https://data.mendeley.com/datasets/35wh56287y/2",
        },
        features=ExternalFeatureProfile(
            dataset_id="stuard_tomato_irrigation_2023",
            timestamp_column="timestamp",
            group_columns=("entity_id",),
            value_columns=(
                "soil_temperature_c", "soil_ec_us_cm",
                "air_temperature_c", "air_humidity_pct", "air_co2_ppm", "air_pressure_hpa",
            ),
            context_columns=("water_volume_m3", "water_alignment_age_sec"),
            excluded_target_source_columns=("soil_moisture_pct",),
            excluded_columns_rule="non_measurement_role_groups",
        ),
        labels=ExternalLabelProfile(
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
                    threshold_scopes=("per_entity", "pooled"),
                ),
            ),
            default_tau_minutes=(1440, 2880, 8640),
            tau_basis=(
                "Operational persistence sensitivities selected for the external sensor-state task. "
                "They are not biologically validated stress durations. The cited controlled-drying "
                "study reports detection delays using soil-water indices and leaf-water-potential "
                "criteria; it does not validate these persistence thresholds for this dataset."
            ),
            tau_sources=("https://doi.org/10.1016/j.agwat.2007.04.009",),
            persistence_basis="elapsed_time",
            min_gap_cadence_fraction=0.0,
            max_gap_cadence_fraction=2.0,
            threshold_fit_pooling="per-entity calibration ECDF primary with pooled sensitivity",
            declared_review_anchor={
                "tail_share": 0.10,
                "tau_minutes": 1440,
                "threshold_scope": "per_entity",
                "status": "CONDITIONAL_ON_EXTERNAL_SUPPORT_GATE",
                "selection_must_precede_model_scores": True,
            },
            continuity_policy="maximum gap only; no lower-gap bound; g_max={g_max:g}x entity median cadence",
        ),
    ),
    "uci_air_quality_360": DatasetProfile(
        dataset_id="uci_air_quality_360",
        intake_adapter="uci",
        source_files=(
            SourceFileSpec(
                "air+quality.zip",
                "https://archive.ics.uci.edu/static/public/360/air+quality.zip",
            ),
        ),
        metadata={
            "title": "Air Quality",
            "doi": "10.24432/C59K5F",
            "official_landing_page": "https://archive.ics.uci.edu/dataset/360/air+quality",
            "license": "CC BY 4.0",
            "citation": "Vito, S. (2008). Air Quality [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C59K5F.",
            "use_limit": "UCI states research use only; commercial purposes excluded.",
            "source_copy_url": "https://archive.ics.uci.edu/static/public/360/air+quality.zip",
        },
        features=ExternalFeatureProfile(
            dataset_id="uci_air_quality_360",
            timestamp_column="timestamp",
            group_columns=(),
            value_columns=(
                "sensor.co", "sensor.nmhc", "sensor.nox", "sensor.no2", "sensor.o3",
                "context.temperature_c", "context.relative_humidity_pct", "context.absolute_humidity",
            ),
            scope_end_exclusive="2005-03-01T00:00:00",
            excluded_columns_rule="criterion_only_roles",
            feature_policy_note="the criterion.* namespace is retained for compatibility",
        ),
        labels=ExternalLabelProfile(
            dataset_id="uci_air_quality_360",
            timestamp_column="timestamp",
            group_columns=(),
            targets=(
                TargetSpec(
                    "co",
                    "criterion.co_gt_mg_m3",
                    "upper",
                    "CO",
                    evidence_kind="TARGET_DEFINING_REFERENCE_MEASUREMENT",
                    input_feature_candidates=("sensor.co",),
                    threshold_scopes=("per_entity",),
                ),
                TargetSpec(
                    "nox",
                    "criterion.nox_gt_ppb",
                    "upper",
                    "NOX",
                    evidence_kind="TARGET_DEFINING_REFERENCE_MEASUREMENT",
                    input_feature_candidates=("sensor.nox",),
                    threshold_scopes=("per_entity",),
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
            continuity_policy="legacy 13/15 to 17/15 median cadence bounds retained for UCI",
        ),
        intake_report_notes=(
            "UCI `(GT)` columns are reference-analyzer measurements; the CO and NOx references define their respective targets. `criterion.*` is a legacy namespace and exclusion-role label, not an independent criterion claim.",
        ),
    ),
}


def dataset_ids() -> tuple[str, ...]:
    return tuple(REGISTRY)


def get_dataset_profile(dataset_id: str) -> DatasetProfile:
    try:
        return REGISTRY[dataset_id]
    except KeyError as exc:
        raise ValueError(f"Unsupported external dataset_id: {dataset_id!r}") from exc
