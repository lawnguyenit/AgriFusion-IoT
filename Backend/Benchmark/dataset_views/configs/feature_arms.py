"""Canonical semantic feature-arm definitions for benchmark experiments.

The materialized dataset may contain the full nine-channel sensor snapshot.
Evaluation selects an arm through an explicit allowlist before model fitting;
the legacy ``v0``/``v1`` identifiers remain compatibility aliases only.
"""

from __future__ import annotations

from dataclasses import dataclass


BASE_5_FEATURES: tuple[str, ...] = (
    "sht.temp_c",
    "sht.humidity_pct",
    "npk.soil_temp_c",
    "npk.soil_moisture_pct",
    "npk.ec",
)
PH_FEATURE = "npk.ph"
NPK_FEATURES: tuple[str, ...] = (
    "npk.n_proxy",
    "npk.p_proxy",
    "npk.k_proxy",
)
FULL_9_FEATURES: tuple[str, ...] = BASE_5_FEATURES + (PH_FEATURE,) + NPK_FEATURES


@dataclass(frozen=True)
class FeatureArm:
    arm_id: str
    feature_names: tuple[str, ...]
    legacy_view_id: str | None = None
    history_horizon_hours: int = 0


FEATURE_ARMS: dict[str, FeatureArm] = {
    "base_5": FeatureArm("base_5", BASE_5_FEATURES, legacy_view_id="v1_point"),
    "plus_ph": FeatureArm("plus_ph", BASE_5_FEATURES + (PH_FEATURE,)),
    "plus_npk": FeatureArm("plus_npk", BASE_5_FEATURES + NPK_FEATURES),
    "full_9": FeatureArm("full_9", FULL_9_FEATURES, legacy_view_id="v0_point"),
    "base_5_history_3h": FeatureArm(
        "base_5_history_3h",
        BASE_5_FEATURES,
        history_horizon_hours=3,
    ),
    "full_9_history_3h": FeatureArm(
        "full_9_history_3h",
        FULL_9_FEATURES,
        history_horizon_hours=3,
    ),
    "base_5_history_8h": FeatureArm(
        "base_5_history_8h",
        BASE_5_FEATURES,
        history_horizon_hours=8,
    ),
    "full_9_history_8h": FeatureArm(
        "full_9_history_8h",
        FULL_9_FEATURES,
        history_horizon_hours=8,
    ),
}


LEGACY_VIEW_TO_ARM: dict[str, str] = {
    "v0_point": "full_9",
    "v1_point": "base_5",
    "v2_same_y_mini_3h": "base_5_history_3h",
    "v2_same_y_full_3h": "full_9_history_3h",
    "v2_same_y_mini_8h": "base_5_history_8h",
    "v2_same_y_full_8h": "full_9_history_8h",
}


def get_feature_arm(arm_id: str) -> FeatureArm:
    try:
        return FEATURE_ARMS[arm_id]
    except KeyError as exc:
        raise KeyError(f"Unknown semantic feature arm: {arm_id!r}") from exc


def semantic_arm_for_view(view_id: str) -> str:
    try:
        return LEGACY_VIEW_TO_ARM[view_id]
    except KeyError as exc:
        raise KeyError(f"No semantic feature arm is registered for view {view_id!r}") from exc


def validate_allowlist(*, arm_id: str, available_columns: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    arm = get_feature_arm(arm_id)
    available = tuple(str(column) for column in available_columns)
    missing = [column for column in arm.feature_names if column not in available]
    if missing:
        raise ValueError(f"Feature arm {arm_id!r} is missing columns: {missing}")
    return arm.feature_names


def feature_family_for_arm(arm_id: str) -> str:
    if arm_id in {"base_5", "base_5_history_3h", "base_5_history_8h"}:
        return "base_5"
    if arm_id == "plus_ph":
        return "plus_ph"
    if arm_id == "plus_npk":
        return "plus_npk"
    if arm_id in {"full_9", "full_9_history_3h", "full_9_history_8h"}:
        return "full_9"
    raise KeyError(f"Unknown semantic feature arm: {arm_id!r}")
