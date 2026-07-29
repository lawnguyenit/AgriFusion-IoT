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
        description="Primary full snapshot row-wise benchmark view with nine measurement features.",
        selection_mode="explicit",
        explicit_features=V2_MEASUREMENT_CHANNELS,
    ),
    "v1_sensor_row": ViewDefinition(
        view_id="v1_sensor_row",
        description="Primary reduced snapshot row-wise benchmark view with five measurement features.",
        selection_mode="explicit",
        explicit_features=V2_MINIMAL_MEASUREMENT_CHANNELS,
    ),
    "v2_minimal_sensor_window_3h": ViewDefinition(
        view_id="v2_minimal_sensor_window_3h",
        description="Reduced snapshot 3h window view using the five-feature sensor subset plus the 3h temporal block.",
        selection_mode="window_engineered",
        explicit_features=V2_MINIMAL_MEASUREMENT_CHANNELS,
        window_horizon_names=("3h",),
    ),
    "v2_minimal_sensor_window_8h": ViewDefinition(
        view_id="v2_minimal_sensor_window_8h",
        description="Reduced snapshot 8h window view using the five-feature sensor subset plus the 8h temporal block.",
        selection_mode="window_engineered",
        explicit_features=V2_MINIMAL_MEASUREMENT_CHANNELS,
        window_horizon_names=("8h",),
    ),
    "v2_sensor_row_window_3h": ViewDefinition(
        view_id="v2_sensor_row_window_3h",
        description="Full snapshot 3h window view using the nine-feature sensor subset plus the 3h temporal block.",
        selection_mode="window_engineered",
        explicit_features=V2_MEASUREMENT_CHANNELS,
        window_horizon_names=("3h",),
    ),
    "v2_sensor_row_window_8h": ViewDefinition(
        view_id="v2_sensor_row_window_8h",
        description="Full snapshot 8h window view using the nine-feature sensor subset plus the 8h temporal block.",
        selection_mode="window_engineered",
        explicit_features=V2_MEASUREMENT_CHANNELS,
        window_horizon_names=("8h",),
    ),
    "v2_sensor_window": ViewDefinition(
        view_id="v2_sensor_window",
        description="Legacy bundled observed-only time-window view combining the full nine-feature snapshot with 3h and 8h temporal blocks.",
        selection_mode="window_engineered",
        explicit_features=V2_MEASUREMENT_CHANNELS,
        window_horizon_names=("3h", "8h"),
    ),
    "v4_hybrid": ViewDefinition(
        view_id="v4_hybrid",
        description="Reserved hybrid sensor-plus-metadata view for a later batch.",
        selection_mode="reserved_not_implemented",
    ),
}


def get_view_definition(view_id: str) -> ViewDefinition:
    try:
        return _VIEW_DEFINITIONS[view_id]
    except KeyError as exc:
        raise KeyError(f"Unsupported dataset view '{view_id}'.") from exc
