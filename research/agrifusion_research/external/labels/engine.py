from __future__ import annotations

from dataclasses import replace

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
    if config.tau_minutes is None:
        if not profile.default_tau_minutes:
            raise ValueError(f"No evidence-based tau candidates are registered for {profile.dataset_id!r}.")
        config = replace(config, tau_minutes=profile.default_tau_minutes)
    config = replace(
        config,
        persistence_basis=profile.persistence_basis,
        min_gap_cadence_fraction=(
            profile.min_gap_cadence_fraction
            if config.min_gap_cadence_fraction is None else config.min_gap_cadence_fraction
        ),
        max_gap_cadence_fraction=(
            profile.max_gap_cadence_fraction
            if config.max_gap_cadence_fraction is None
            else config.max_gap_cadence_fraction
        ),
    )
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
        frame.attrs.get("source_scope", {}),
        profile,
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
    source_scope: dict[str, object],
    profile: ExternalLabelProfile,
) -> dict[str, object]:
    q_token = "_".join(f"{round(q * 100):02d}" for q in config.tail_shares)
    tau_token = "_".join(str(int(tau)) for tau in config.tau_minutes)
    return {
        "policy_id": f"EXTERNAL_QTAU_{config.calibration_days}D_Q{q_token}_TAU{tau_token}M_V3",
        "calibration_start": first_time.isoformat(),
        "calibration_end_exclusive": calibration_end.isoformat(),
        "observed_data_end": observed_end.isoformat(),
        "source_scope": source_scope,
        "calibration_days": int(config.calibration_days),
        "threshold_fit_pooling": (
            "per-entity calibration ECDF primary with pooled sensitivity"
            if profile.dataset_id == "stuard_tomato_irrigation_2023"
            else "one calibration ECDF per registered target"
        ),
        "quantile_interpolation": "linear",
        "tail_shares": list(config.tail_shares),
        "tau_minutes": list(config.tau_minutes),
        "tau_selection_basis": profile.tau_basis,
        "tau_evidence_sources": list(profile.tau_sources),
        "declared_review_anchor": (
            {
                "tail_share": 0.10,
                "tau_minutes": 1440,
                "threshold_scope": "per_entity",
                "status": "CONDITIONAL_ON_EXTERNAL_SUPPORT_GATE",
                "selection_must_precede_model_scores": True,
            }
            if profile.dataset_id == "stuard_tomato_irrigation_2023" else None
        ),
        "persistence_mapping": (
            "elapsed minutes since the first observation in the current tail run >= tau_minutes"
            if profile.persistence_basis == "elapsed_time"
            else "K_e(tau)=ceil(tau_minutes/median_cadence_minutes_e)"
        ),
        "persistence_basis": profile.persistence_basis,
        "strict_continuity_bounds_fraction_of_median_cadence": [
            config.min_gap_cadence_fraction,
            config.max_gap_cadence_fraction,
        ],
        "continuity_policy": (
            f"maximum gap only; no lower-gap bound; g_max={config.max_gap_cadence_fraction:g}x entity median cadence"
            if profile.dataset_id == "stuard_tomato_irrigation_2023"
            else "legacy 13/15 to 17/15 median cadence bounds retained for UCI"
        ),
        "primary_candidate_selected": False,
    }
