from __future__ import annotations

from .history import FeatureBundle
from .representations import RepresentationBundle


RQ1_MAIN_IDS = (
    "S0_M_t",
    "S1_X_t",
    "S2_X_t_HM",
    "S3_X_t_HX",
    "S4_X_t_HX_C",
)
RQ1_BRANCH_ID = "B_M"


def build_rq1_nested_representations(
    *,
    base_representations: dict[str, RepresentationBundle],
    audit_representations: dict[str, RepresentationBundle],
) -> dict[str, RepresentationBundle]:
    """Build a nested main chain plus the compact moisture-history branch."""

    snapshot = base_representations["R00"].feature_bundle
    window = base_representations["R10"].feature_bundle
    full_history = base_representations["R11"].feature_bundle
    pure_history = audit_representations["R_pure_lag"].feature_bundle
    snapshot_names = list(snapshot.feature_names)
    moisture = "npk.soil_moisture_pct"
    moisture_lags = [f"{moisture}__causal_lag_{lag}" for lag in range(1, 13)]
    sensor_lags = [name for name in pure_history.feature_names if "__causal_lag_" in name]
    context_names = [name for name in window.feature_names if name not in snapshot_names]
    if moisture not in snapshot_names:
        raise ValueError(f"RQ1 requires current moisture feature: {moisture}")
    if len(snapshot_names) != 9 or len(moisture_lags) != 12 or len(sensor_lags) != 108 or len(context_names) != 45:
        raise ValueError(
            "RQ1 nested contract drifted: "
            f"snapshot={len(snapshot_names)}, moisture_lags={len(moisture_lags)}, "
            f"sensor_lags={len(sensor_lags)}, context={len(context_names)}"
        )
    all_history_names = [*snapshot_names, *sensor_lags]
    for name in [*moisture_lags, *all_history_names, *context_names]:
        if name not in full_history.frame.columns and name not in pure_history.frame.columns:
            raise ValueError(f"RQ1 feature is absent from causal source: {name}")

    return {
        "S0_M_t": _select(
            source=snapshot,
            representation_id="S0_M_t",
            display_name="S0 current moisture",
            feature_names=[moisture],
            feature_groups={"M_t": [moisture]},
        ),
        "S1_X_t": _select(
            source=snapshot,
            representation_id="S1_X_t",
            display_name="S1 current sensor snapshot",
            feature_names=snapshot_names,
            feature_groups={"M_t": [moisture], "X_t_minus_M_t": [name for name in snapshot_names if name != moisture]},
        ),
        "S2_X_t_HM": _select(
            source=full_history,
            representation_id="S2_X_t_HM",
            display_name="S2 current sensors plus moisture history",
            feature_names=[*snapshot_names, *moisture_lags],
            feature_groups={"X_t": snapshot_names, "H_M": moisture_lags},
        ),
        "S3_X_t_HX": _select(
            source=pure_history,
            representation_id="S3_X_t_HX",
            display_name="S3 current sensors plus all sensor history",
            feature_names=all_history_names,
            feature_groups={"X_t": snapshot_names, "H_X": sensor_lags},
        ),
        "S4_X_t_HX_C": _select(
            source=full_history,
            representation_id="S4_X_t_HX_C",
            display_name="S4 sensor history plus causal context",
            feature_names=[*all_history_names, *context_names],
            feature_groups={"X_t": snapshot_names, "H_X": sensor_lags, "C": context_names},
        ),
        "B_M": _select(
            source=pure_history,
            representation_id="B_M",
            display_name="diagnostic moisture history branch",
            feature_names=[moisture, *moisture_lags],
            feature_groups={"M_t": [moisture], "H_M": moisture_lags},
        ),
    }


def _select(
    *,
    source: FeatureBundle,
    representation_id: str,
    display_name: str,
    feature_names: list[str],
    feature_groups: dict[str, list[str]],
) -> RepresentationBundle:
    missing = sorted(set(feature_names).difference(source.frame.columns))
    if missing:
        raise ValueError(f"{representation_id} is missing selected features: {missing[:5]}")
    return RepresentationBundle(
        representation_id=representation_id,
        display_name=display_name,
        feature_bundle=FeatureBundle(
            frame=source.frame.loc[:, ["sample_id", *feature_names]].convert_dtypes(),
            feature_names=feature_names,
            metadata={
                **source.metadata,
                "representation_id": representation_id,
                "representation": display_name,
                "feature_count": len(feature_names),
                "feature_groups": feature_groups,
                "future_used": False,
                "target_derived_features": False,
                "acquisition_metadata_included": False,
            },
        ),
    )
