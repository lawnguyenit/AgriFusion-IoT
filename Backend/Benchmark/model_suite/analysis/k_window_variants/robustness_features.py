from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .history import FeatureBundle
from .representations import RepresentationBundle


LAG_PATTERN = re.compile(r"^(?P<sensor>.+)__causal_lag_(?P<lag>\d+)$")
LAG_AGE_PATTERN = re.compile(r"^causal_history__lag_(?P<lag>\d+)_age_hours$")


def build_history_audit_representations(
    *,
    representations: dict[str, RepresentationBundle],
    disruption_seed: int,
) -> dict[str, RepresentationBundle]:
    """Build isolated sensor-history, metadata, and order-disrupted contracts.

    `R_pure_lag` contains the current nine sensor values and only the 108
    strictly-past sensor lag values. `R_meta` contains only lag-age and
    history-quality fields. The disrupted controls preserve the feature count,
    per-row lag value multiset, and nine-channel alignment while changing the
    lag ordering within each row.
    """

    r01 = representations["R01"]
    source = r01.feature_bundle
    snapshot_names = [name for name in r01.feature_bundle.feature_names if "__causal_lag_" not in name and not name.startswith("causal_history__")]
    lag_names = [name for name in source.feature_names if LAG_PATTERN.match(name)]
    age_names = [name for name in source.feature_names if LAG_AGE_PATTERN.match(name)]
    quality_names = [
        name
        for name in source.feature_names
        if name.startswith("causal_history__3h_")
    ]
    if len(snapshot_names) != 9:
        raise ValueError(f"R_pure_lag expects nine current sensor fields, got {len(snapshot_names)}")
    if len(lag_names) != 108:
        raise ValueError(f"R_pure_lag expects 108 sensor lag fields, got {len(lag_names)}")
    if len(age_names) != 12 or len(quality_names) != 5:
        raise ValueError(
            f"R_meta expects 12 lag-age and 5 quality fields, got {len(age_names)} and {len(quality_names)}"
        )

    lag_names = _ordered_lag_names(lag_names, snapshot_names)
    age_names = sorted(age_names, key=lambda name: int(LAG_AGE_PATTERN.match(name).group("lag")))
    pure_names = [*snapshot_names, *lag_names]
    meta_names = [*age_names, *quality_names]
    pure = _select(
        source,
        representation_id="R_pure_lag",
        display_name="pure_sensor_history",
        feature_names=pure_names,
        metadata={
            "base_snapshot_count": len(snapshot_names),
            "sensor_lag_count": len(lag_names),
            "metadata_count": 0,
            "summary_count": 0,
            "ordered_addition_count": len(lag_names),
            "future_used": False,
            "target_derived_features": False,
        },
    )
    metadata = _select(
        source,
        representation_id="R_meta",
        display_name="history_metadata_only",
        feature_names=meta_names,
        metadata={
            "base_snapshot_count": 0,
            "sensor_lag_count": 0,
            "metadata_count": len(meta_names),
            "summary_count": 0,
            "ordered_addition_count": 0,
            "future_used": False,
            "target_derived_features": False,
        },
    )
    pure_disrupted = _disrupt(
        pure,
        snapshot_names=snapshot_names,
        lag_names=lag_names,
        representation_id="R_pure_lag_disrupted",
        display_name="pure_sensor_history_temporal_order_disrupted",
        seed=disruption_seed,
    )
    r01_disrupted = _disrupt(
        r01,
        snapshot_names=snapshot_names,
        lag_names=lag_names,
        representation_id="R01_disrupted",
        display_name="ordered_flatten_temporal_order_disrupted",
        seed=disruption_seed,
    )
    return {
        "R01": r01,
        "R_pure_lag": pure,
        "R_meta": metadata,
        "R_pure_lag_disrupted": pure_disrupted,
        "R01_disrupted": r01_disrupted,
    }


def _ordered_lag_names(lag_names: list[str], snapshot_names: list[str]) -> list[str]:
    by_sensor_lag = {name: LAG_PATTERN.match(name).groupdict() for name in lag_names}
    missing = sorted(set(snapshot_names).difference({item["sensor"] for item in by_sensor_lag.values()}))
    if missing:
        raise ValueError(f"Lag fields do not cover all snapshot sensors: {missing}")
    return [
        f"{sensor}__causal_lag_{lag}"
        for lag in range(1, 13)
        for sensor in snapshot_names
    ]


def _select(
    source: FeatureBundle,
    *,
    representation_id: str,
    display_name: str,
    feature_names: list[str],
    metadata: dict[str, object],
) -> RepresentationBundle:
    missing = sorted(set(feature_names).difference(source.frame.columns))
    if missing:
        raise ValueError(f"{representation_id} is missing fields: {missing[:5]}")
    frame = source.frame.loc[:, ["sample_id", *feature_names]].copy()
    return RepresentationBundle(
        representation_id=representation_id,
        display_name=display_name,
        feature_bundle=FeatureBundle(
            frame=frame.convert_dtypes(),
            feature_names=feature_names,
            metadata={**source.metadata, **metadata, "representation_id": representation_id, "representation": display_name},
        ),
    )


def _disrupt(
    source: RepresentationBundle,
    *,
    snapshot_names: list[str],
    lag_names: list[str],
    representation_id: str,
    display_name: str,
    seed: int,
) -> RepresentationBundle:
    frame = source.feature_bundle.frame.copy()
    rng = np.random.default_rng(seed)
    lag_count = len(lag_names) // len(snapshot_names)
    values = frame.loc[:, lag_names].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    original_values = values.copy()
    lag_index = {name: index for index, name in enumerate(lag_names)}
    for row_index in range(len(frame)):
        permutation = rng.permutation(lag_count)
        for new_lag, old_position in enumerate(permutation, start=1):
            old_lag = int(old_position) + 1
            for sensor_index, sensor in enumerate(snapshot_names):
                new_column = f"{sensor}__causal_lag_{new_lag}"
                old_column = f"{sensor}__causal_lag_{old_lag}"
                values[row_index, lag_index[new_column]] = original_values[row_index, lag_index[old_column]]
    frame.loc[:, lag_names] = values
    bundle = FeatureBundle(
        frame=frame.convert_dtypes(),
        feature_names=list(source.feature_bundle.feature_names),
        metadata={
            **source.feature_bundle.metadata,
            "representation_id": representation_id,
            "representation": display_name,
            "temporal_order_disrupted": True,
            "disruption_seed": seed,
            "disruption_unit": "per-row lag-position permutation with nine-channel blocks",
        },
    )
    return RepresentationBundle(representation_id=representation_id, display_name=display_name, feature_bundle=bundle)
