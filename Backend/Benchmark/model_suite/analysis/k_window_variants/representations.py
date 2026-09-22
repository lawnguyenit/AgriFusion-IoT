from __future__ import annotations

from dataclasses import dataclass

from .history import FeatureBundle


R00_SNAPSHOT = "R00"
R10_WINDOW_SUMMARIES = "R10"
R01_ORDERED_FLATTEN = "R01"
R11_WINDOW_PLUS_FLATTEN = "R11"


@dataclass(frozen=True)
class RepresentationBundle:
    representation_id: str
    display_name: str
    feature_bundle: FeatureBundle


def build_representation_bundles(
    *,
    snapshot_bundle: FeatureBundle,
    window_bundle: FeatureBundle,
    history_bundle: FeatureBundle,
) -> dict[str, RepresentationBundle]:
    """Materialize the four explicit R00/R10/R01/R11 feature contracts.

    R00 is the current-row snapshot. R10 adds the existing causal 3h summary
    statistics. R01 adds ordered causal history and acquisition-quality fields
    without the summary-statistics block. R11 combines R10 and R01's ordered
    additions. All four bundles share the same sample universe.
    """

    snapshot_names = list(snapshot_bundle.feature_names)
    window_names = list(window_bundle.feature_names)
    history_names = list(history_bundle.feature_names)
    summary_names = [name for name in window_names if name not in snapshot_names]
    ordered_additions = [name for name in history_names if name not in window_names]

    if len(snapshot_names) != 9:
        raise ValueError(f"R00 expects nine snapshot features, got {len(snapshot_names)}")
    if len(summary_names) != 45:
        raise ValueError(f"R10 expects 45 window-summary additions, got {len(summary_names)}")
    if len(ordered_additions) != 125:
        raise ValueError(f"Ordered flatten additions must contain 125 fields, got {len(ordered_additions)}")

    _assert_same_sample_universe(snapshot_bundle, window_bundle, history_bundle)

    r00 = _select_bundle(
        representation_id=R00_SNAPSHOT,
        display_name="snapshot",
        source_bundle=snapshot_bundle,
        feature_names=snapshot_names,
        metadata={"base_snapshot_count": len(snapshot_names), "summary_count": 0, "ordered_addition_count": 0},
    )
    r10 = _select_bundle(
        representation_id=R10_WINDOW_SUMMARIES,
        display_name="window_summaries",
        source_bundle=window_bundle,
        feature_names=window_names,
        metadata={"base_snapshot_count": len(snapshot_names), "summary_count": len(summary_names), "ordered_addition_count": 0},
    )
    r01 = _select_bundle(
        representation_id=R01_ORDERED_FLATTEN,
        display_name="ordered_flatten",
        source_bundle=history_bundle,
        feature_names=[*snapshot_names, *ordered_additions],
        metadata={"base_snapshot_count": len(snapshot_names), "summary_count": 0, "ordered_addition_count": len(ordered_additions)},
    )
    r11 = _select_bundle(
        representation_id=R11_WINDOW_PLUS_FLATTEN,
        display_name="window_plus_ordered_flatten",
        source_bundle=history_bundle,
        feature_names=[*window_names, *ordered_additions],
        metadata={"base_snapshot_count": len(snapshot_names), "summary_count": len(summary_names), "ordered_addition_count": len(ordered_additions)},
    )
    bundles = {bundle.representation_id: bundle for bundle in (r00, r10, r01, r11)}
    expected_counts = {R00_SNAPSHOT: 9, R10_WINDOW_SUMMARIES: 54, R01_ORDERED_FLATTEN: 134, R11_WINDOW_PLUS_FLATTEN: 179}
    for representation_id, expected_count in expected_counts.items():
        actual_count = len(bundles[representation_id].feature_bundle.feature_names)
        if actual_count != expected_count:
            raise ValueError(f"{representation_id} feature contract drifted: expected {expected_count}, got {actual_count}")
    return bundles


def _select_bundle(
    *,
    representation_id: str,
    display_name: str,
    source_bundle: FeatureBundle,
    feature_names: list[str],
    metadata: dict[str, object],
) -> RepresentationBundle:
    missing = sorted(set(feature_names).difference(source_bundle.frame.columns))
    if missing:
        raise ValueError(f"{representation_id} is missing selected features: {missing[:5]}")
    frame = source_bundle.frame.loc[:, ["sample_id", *feature_names]].copy()
    bundle_metadata = {
        **source_bundle.metadata,
        **metadata,
        "representation_id": representation_id,
        "representation": display_name,
        "feature_count": len(feature_names),
        "future_used": False,
        "target_derived_features": False,
    }
    return RepresentationBundle(
        representation_id=representation_id,
        display_name=display_name,
        feature_bundle=FeatureBundle(
            frame=frame,
            feature_names=feature_names,
            metadata=bundle_metadata,
        ),
    )


def _assert_same_sample_universe(*bundles: FeatureBundle) -> None:
    universes = [set(bundle.frame["sample_id"].astype("string")) for bundle in bundles]
    if any(universe != universes[0] for universe in universes[1:]):
        raise ValueError("R00/R10/R01/R11 source bundles must share the same sample universe.")
