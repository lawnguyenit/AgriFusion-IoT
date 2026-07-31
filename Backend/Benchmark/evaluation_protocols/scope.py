from __future__ import annotations


PRIMARY_FEATURE_VIEW_IDS: tuple[str, ...] = (
    "v0_point",
    "v1_point",
    "v2_same_y_mini_3h",
    "v2_same_y_full_3h",
)

PRIMARY_FEATURE_SOURCE_VIEW_IDS: tuple[str, ...] = (
    "v0_minimal_sensor",
    "v1_sensor_row",
    "v2_minimal_sensor_window_3h",
    "v2_sensor_row_window_3h",
)

PRIMARY_LABEL_TASK_IDS: tuple[str, ...] = (
    "v0_point_train",
    "v1_point_train",
    "v2_same_y_3h",
)

PRIMARY_PROTOCOL_VIEW_IDS: tuple[str, ...] = PRIMARY_LABEL_TASK_IDS

PRIMARY_COMPARISON_IDS: tuple[str, ...] = (
    "v0_vs_v2_mini_3h",
    "v1_vs_v2_full_3h",
)

PRIMARY_FOLD_IDS: tuple[str, ...] = ("fold_01",)
PRIMARY_EVAL_PARTITIONS: tuple[str, ...] = ("validation", "test")
FINAL_TARGET_FOLD_ID = "source_final_fit__p2_target_holdout"
FINAL_TARGET_STAGE_ID = "frozen_target_holdout"
