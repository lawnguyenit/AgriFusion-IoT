from __future__ import annotations

from Backend.Benchmark.dataset_views.contracts import ViewDefinition
from Backend.Benchmark.dataset_views.configs.windowing import (
    V2_MEASUREMENT_CHANNELS,
    V2_MINIMAL_MEASUREMENT_CHANNELS,
)


DEFAULT_VIEW_IDS: tuple[str, ...] = (
    "v0_minimal_sensor",
    "v1_sensor_row",
)

_VIEW_DEFINITIONS: dict[str, ViewDefinition] = {
    "v0_minimal_sensor": ViewDefinition(
        view_id="v0_minimal_sensor",
        description="Minimal sensor-only row-wise benchmark view.",
        selection_mode="explicit",
        explicit_features=(
            "sht.temp_c",
            "sht.humidity_pct",
            "npk.soil_temp_c",
            "npk.soil_moisture_pct",
            "npk.ec",
        ),
    ),
    "v1_sensor_row": ViewDefinition(
        view_id="v1_sensor_row",
        description="Approved sensor-row view with nine measurement features only.",
        selection_mode="explicit",
        explicit_features=V2_MEASUREMENT_CHANNELS,
    ),
    "v2_minimal_sensor_window_3h": ViewDefinition(
        view_id="v2_minimal_sensor_window_3h",
        description="Minimal sensor window view using v0 measurements plus current-row ISR and only the 3h temporal block.",
        selection_mode="window_engineered",
        explicit_features=V2_MINIMAL_MEASUREMENT_CHANNELS,
        window_horizon_names=("3h",),
    ),
    "v2_minimal_sensor_window_8h": ViewDefinition(
        view_id="v2_minimal_sensor_window_8h",
        description="Minimal sensor window view using v0 measurements plus current-row ISR and only the 8h temporal block.",
        selection_mode="window_engineered",
        explicit_features=V2_MINIMAL_MEASUREMENT_CHANNELS,
        window_horizon_names=("8h",),
    ),
    "v2_sensor_row_window_3h": ViewDefinition(
        view_id="v2_sensor_row_window_3h",
        description="Sensor-row window view using v1 measurements plus current-row ISR and only the 3h temporal block.",
        selection_mode="window_engineered",
        explicit_features=V2_MEASUREMENT_CHANNELS,
        window_horizon_names=("3h",),
    ),
    "v2_sensor_row_window_8h": ViewDefinition(
        view_id="v2_sensor_row_window_8h",
        description="Sensor-row window view using v1 measurements plus current-row ISR and only the 8h temporal block.",
        selection_mode="window_engineered",
        explicit_features=V2_MEASUREMENT_CHANNELS,
        window_horizon_names=("8h",),
    ),
    "v2_sensor_window": ViewDefinition(
        view_id="v2_sensor_window",
        description="Legacy bundled observed-only time-window sensor view with continuity-aware 3h and 8h temporal features.",
        selection_mode="window_engineered",
        explicit_features=V2_MEASUREMENT_CHANNELS,
        window_horizon_names=("3h", "8h"),
    ),
    "v3_direct": ViewDefinition(
        view_id="v3_direct",
        description="Operational-lineage direct-rule evidence view.",
        selection_mode="operational_lineage_direct",
    ),
    "v3_derived": ViewDefinition(
        view_id="v3_derived",
        description="Operational-lineage derived-rule descendants view.",
        selection_mode="operational_lineage_derived",
    ),
    "v3_independent": ViewDefinition(
        view_id="v3_independent",
        description="Operational-lineage independent-process evidence view.",
        selection_mode="operational_lineage_independent",
    ),
    "v3_pre_onset": ViewDefinition(
        view_id="v3_pre_onset",
        description="Operational-lineage pre-onset benchmark view using only independent-process evidence.",
        selection_mode="operational_lineage_pre_onset",
    ),
    "v4_hybrid": ViewDefinition(
        view_id="v4_hybrid",
        description="Reserved hybrid sensor-plus-metadata view for a later batch.",
        selection_mode="reserved_not_implemented",
    ),
    "v5_proxy_reduced": ViewDefinition(
        view_id="v5_proxy_reduced",
        description="Reserved final proxy-reduced view pending validated dependency registry coverage.",
        selection_mode="reserved_blocked_prerequisite",
    ),
    "v5_proxy_reduced_draft": ViewDefinition(
        view_id="v5_proxy_reduced_draft",
        description="Internal proxy-reduced draft reclassified from the historical drifted v6 output.",
        selection_mode="proxy_reduced_draft",
        candidate_prefixes=("sht.", "npk."),
    ),
    "v6_sequence_8h": ViewDefinition(
        view_id="v6_sequence_8h",
        description="Environmental V6 sequence-labeling dataset using fixed independent 8-hour day chunks.",
        selection_mode="environmental_sequence_8h",
    ),
}


def get_view_definition(view_id: str) -> ViewDefinition:
    try:
        return _VIEW_DEFINITIONS[view_id]
    except KeyError as exc:
        raise KeyError(f"Unsupported dataset view '{view_id}'.") from exc
