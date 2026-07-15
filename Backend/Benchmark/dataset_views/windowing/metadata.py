from __future__ import annotations

from Backend.Benchmark.dataset_views.configs import V2_WINDOW_HORIZONS


def build_feature_metadata(measurement_columns: tuple[str, ...]) -> dict[str, dict[str, object]]:
    return build_feature_metadata_for_horizons(
        measurement_columns=measurement_columns,
        horizons=V2_WINDOW_HORIZONS,
    )


def build_feature_metadata_for_horizons(
    *,
    measurement_columns: tuple[str, ...],
    horizons,
) -> dict[str, dict[str, object]]:
    metadata: dict[str, dict[str, object]] = {}
    for measurement_column in measurement_columns:
        metadata[measurement_column] = {
            "feature_role": "measurement",
            "rule_proxy_level": "none",
            "derivation": "canonical_current_value_masked_by_sensor_validity",
        }
        for horizon in horizons:
            metadata[f"{measurement_column}__{horizon.name}_median"] = {
                "feature_role": "temporal_window_feature",
                "rule_proxy_level": "none",
                "statistic": "median",
                "window_hours": horizon.hours,
            }
            metadata[f"{measurement_column}__{horizon.name}_iqr"] = {
                "feature_role": "temporal_window_feature",
                "rule_proxy_level": "none",
                "statistic": "iqr",
                "window_hours": horizon.hours,
            }
            metadata[f"{measurement_column}__{horizon.name}_range"] = {
                "feature_role": "temporal_window_feature",
                "rule_proxy_level": "none",
                "statistic": "range",
                "window_hours": horizon.hours,
            }
            metadata[f"{measurement_column}__{horizon.name}_delta"] = {
                "feature_role": "temporal_window_feature",
                "rule_proxy_level": "none",
                "statistic": "delta",
                "window_hours": horizon.hours,
            }
            metadata[f"{measurement_column}__{horizon.name}_slope_per_hour"] = {
                "feature_role": "temporal_window_feature",
                "rule_proxy_level": "none",
                "statistic": "slope_per_hour",
                "window_hours": horizon.hours,
            }
    return metadata
