from __future__ import annotations

from .representations import RepresentationBundle
from .history import FeatureBundle


ORDERED_REPRESENTATION_IDS = (
    "M_t",
    "X_t",
    "M_history",
    "X_history",
    "X_history_context",
)


def build_ordered_representation_bundles(
    *,
    base_representations: dict[str, RepresentationBundle],
    audit_representations: dict[str, RepresentationBundle],
) -> dict[str, RepresentationBundle]:
    """Build the requested monotonic representation progression.

    The progression deliberately keeps acquisition/history-quality metadata
    out of ``X_history_context``. This makes the last step a sensor-history
    plus causal-context comparison rather than a shortcut-control mixture.
    """

    snapshot = base_representations["R00"].feature_bundle
    full_history = base_representations["R11"].feature_bundle
    pure_history = audit_representations["R_pure_lag"].feature_bundle
    moisture = "npk.soil_moisture_pct"
    snapshot_names = list(base_representations["R00"].feature_bundle.feature_names)
    pure_names = list(pure_history.feature_names)
    context_names = [
        name
        for name in base_representations["R10"].feature_bundle.feature_names
        if name not in snapshot_names
    ]
    moisture_lags = [
        f"{moisture}__causal_lag_{lag}"
        for lag in range(1, 13)
    ]
    if moisture not in snapshot_names:
        raise ValueError(f"Ordered progression requires current moisture feature: {moisture}")
    if any(name not in pure_names for name in [*moisture_lags]):
        raise ValueError("Ordered progression requires all 12 causal moisture lag fields.")
    if len(snapshot_names) != 9 or len(pure_names) != 117 or len(context_names) != 45:
        raise ValueError(
            "Ordered feature contract drifted: "
            f"snapshot={len(snapshot_names)}, pure_history={len(pure_names)}, context={len(context_names)}"
        )

    bundles = {
        "M_t": _select(
            source=snapshot,
            representation_id="M_t",
            display_name="current_moisture_only",
            feature_names=[moisture],
            feature_groups={"M_t": [moisture]},
        ),
        "X_t": _select(
            source=snapshot,
            representation_id="X_t",
            display_name="current_sensor_snapshot",
            feature_names=snapshot_names,
            feature_groups={"X_t": snapshot_names},
        ),
        "M_history": _select(
            source=pure_history,
            representation_id="M_history",
            display_name="moisture_history",
            feature_names=[moisture, *moisture_lags],
            feature_groups={"M_t": [moisture], "M_history": moisture_lags},
        ),
        "X_history": _select(
            source=pure_history,
            representation_id="X_history",
            display_name="sensor_history",
            feature_names=pure_names,
            feature_groups={"X_t": snapshot_names, "X_history": [name for name in pure_names if name not in snapshot_names]},
        ),
        "X_history_context": _select(
            source=full_history,
            representation_id="X_history_context",
            display_name="sensor_history_plus_context",
            feature_names=[*pure_names, *context_names],
            feature_groups={
                "X_t": snapshot_names,
                "X_history": [name for name in pure_names if name not in snapshot_names],
                "context": context_names,
            },
        ),
    }
    return bundles


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
        raise ValueError(f"{representation_id} is missing selected fields: {missing[:5]}")
    frame = source.frame.loc[:, ["sample_id", *feature_names]].copy()
    return RepresentationBundle(
        representation_id=representation_id,
        display_name=display_name,
        feature_bundle=FeatureBundle(
            frame=frame.convert_dtypes(),
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
