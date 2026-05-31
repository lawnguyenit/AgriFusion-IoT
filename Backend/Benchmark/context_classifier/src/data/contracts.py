from __future__ import annotations


RAW_FULL_SENSOR_COLUMNS = [
    "soil_temp",
    "soil_humidity",
    "air_temp",
    "air_humidity",
    "EC",
    "pH",
    "N",
    "P",
    "K",
]

RAW_CORE_SENSOR_COLUMNS = [
    "soil_temp",
    "soil_humidity",
    "air_temp",
    "air_humidity",
    "EC",
]

DIAGNOSTIC_SENSOR_COLUMNS = [
    "ec_npk_consistency_score",
    "ec_npk_consistency_flag",
]

# Backward-compatible full sensor set used by canonical and sequence builders.
BASE_SENSOR_COLUMNS = RAW_FULL_SENSOR_COLUMNS + DIAGNOSTIC_SENSOR_COLUMNS

PACKET_LOSS_FEATURE_COLUMNS = [
    "loss_packet_count",
    "outage_duration_steps",
    "time_since_last_valid_step",
    "recovery_step_index",
    "nighttime_outage_flag",
    "sunrise_recovery_flag",
]

CONTEXT_METADATA_COLUMNS = [
    "timestamp",
    "split_name",
    "context_label",
    "context_label_raw",
    "data_origin",
    "is_synthetic",
    "record_present",
    "timeline_state",
    "episode_id",
    "phase_name",
    "scenario_intensity",
    "scenario_progress",
    "effect_strength",
    "source_reference",
    "event_primary",
    "event_labels",
]

CANONICAL_COLUMNS = (
    ["timestamp"]
    + RAW_FULL_SENSOR_COLUMNS
    + DIAGNOSTIC_SENSOR_COLUMNS
    + [
        "split_name",
        "context_label",
        "context_label_raw",
        "data_origin",
        "is_synthetic",
        "record_present",
        "timeline_state",
        "episode_id",
        "phase_name",
        "scenario_intensity",
        "scenario_progress",
        "effect_strength",
        "source_reference",
        "event_primary",
        "event_labels",
        "packet_loss_flag",
        "suspected_cause",
        "cause_confidence",
    ]
    + PACKET_LOSS_FEATURE_COLUMNS
)

TREND_SENSOR_COLUMNS = [
    "soil_temp",
    "soil_humidity",
    "air_temp",
    "air_humidity",
    "EC",
]

V2_DELTA_COLUMNS = [
    "air_temp_delta_1step",
    "soil_temp_delta_1step",
    "soil_humidity_delta_1step",
    "EC_delta_1step",
]

V2_WINDOW_SHORT_COLUMNS = [
    "air_temp_slope_3h",
    "air_temp_range_3h",
    "air_temp_mean_3h",
    "soil_temp_slope_3h",
    "soil_humidity_slope_3h",
    "soil_humidity_range_3h",
    "EC_slope_3h",
    "EC_range_3h",
]

V3_WINDOW_MEDIUM_COLUMNS = [
    "air_temp_slope_8h",
    "air_temp_range_8h",
    "soil_temp_slope_8h",
    "soil_temp_mean_8h",
    "soil_humidity_slope_8h",
    "soil_humidity_range_8h",
    "EC_slope_8h",
    "EC_range_8h",
]
