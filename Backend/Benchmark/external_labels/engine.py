from __future__ import annotations

import pandas as pd

from .candidates import add_joint_labels, build_target_candidates
from .contracts import ExternalLabelConfig
from .profiles import ExternalLabelProfile
from .temporal import build_cadence_registry
from .validation import prepare_source


def build_candidate_labels(
    source: pd.DataFrame,
    profile: ExternalLabelProfile,
    config: ExternalLabelConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Coordinate calibration, candidate generation, and audit artifacts."""
    frame, entity_key, in_calibration, first_time, calibration_end = prepare_source(
        source, profile, config
    )
    cadence_registry = build_cadence_registry(frame, profile, entity_key, config)
    cadence_by_entity = {
        str(row.entity_id): float(row.median_cadence_minutes)
        for row in cadence_registry.itertuples(index=False)
    }
    labels = pd.DataFrame({"sample_id": frame["sample_id"]})
    registry_rows: list[dict[str, object]] = []
    support_rows: list[dict[str, object]] = []
    for target in profile.targets:
        target_labels, target_registry, target_support = build_target_candidates(
            frame=frame,
            in_calibration=in_calibration,
            entity_key=entity_key,
            profile=profile,
            target=target,
            config=config,
            cadence_by_entity=cadence_by_entity,
        )
        labels = labels.merge(target_labels, on="sample_id", how="left", validate="one_to_one")
        registry_rows.extend(target_registry)
        support_rows.extend(target_support)
    add_joint_labels(labels, profile, config)
    labels = frame[["sample_id", profile.timestamp_column, *profile.group_columns]].merge(
        labels, on="sample_id", how="left", validate="one_to_one"
    ).sort_values(profile.timestamp_column, kind="stable").reset_index(drop=True)
    calibration = _calibration_policy(
        config,
        first_time,
        calibration_end,
        frame[profile.timestamp_column].max(),
    )
    return (
        labels.convert_dtypes(),
        pd.DataFrame(registry_rows).convert_dtypes(),
        cadence_registry.convert_dtypes(),
        pd.DataFrame(support_rows).convert_dtypes(),
        calibration,
    )


def _calibration_policy(
    config: ExternalLabelConfig,
    first_time: pd.Timestamp,
    calibration_end: pd.Timestamp,
    observed_end: pd.Timestamp,
) -> dict[str, object]:
    return {
        "policy_id": "EXTERNAL_QTAU_21D_Q05_Q20_TAU30_90_V1",
        "calibration_start": first_time.isoformat(),
        "calibration_end_exclusive": calibration_end.isoformat(),
        "observed_data_end": observed_end.isoformat(),
        "calibration_days": int(config.calibration_days),
        "threshold_fit_pooling": "all known target measurements across registered source entities",
        "quantile_interpolation": "linear",
        "tail_shares": list(config.tail_shares),
        "tau_minutes": list(config.tau_minutes),
        "persistence_mapping": "K_e(tau)=ceil(tau_minutes/median_cadence_minutes_e)",
        "strict_continuity_bounds_fraction_of_median_cadence": [
            config.min_gap_cadence_fraction,
            config.max_gap_cadence_fraction,
        ],
        "strict_continuity_basis": "in-house 13-17 minute bounds normalized by its nominal 15-minute cadence",
        "primary_candidate_selected": False,
    }
