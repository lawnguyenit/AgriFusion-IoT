from __future__ import annotations

import pandas as pd

from .profiles import ExternalLabelProfile, TargetSpec


def build_support_rows(
    *,
    frame: pd.DataFrame,
    in_calibration: pd.Series,
    entity_key: str,
    profile: ExternalLabelProfile,
    target: TargetSpec,
    q_id: str,
    tail_share: float,
    tau_minutes: int,
    labels: pd.Series,
    statuses: pd.Series,
    tail_mask: pd.Series,
    run_lengths: pd.Series,
    required_by_entity: dict[str, int],
    cadence_by_entity: dict[str, float],
    timestamp_column: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for entity, positions in frame.groupby(entity_key, sort=False).groups.items():
        selected = pd.Index(positions)
        scopes = {
            "ALL": pd.Series(True, index=selected),
            "CALIBRATION": in_calibration.loc[selected],
            "POST_CALIBRATION": ~in_calibration.loc[selected],
        }
        for scope, scope_mask in scopes.items():
            scoped = selected[scope_mask.to_numpy(dtype=bool)]
            scoped_labels = labels.loc[scoped]
            known_count = int(scoped_labels.notna().sum())
            positive_count = int(scoped_labels.eq(1).fillna(False).sum())
            negative_count = int(scoped_labels.eq(0).fillna(False).sum())
            unknown_count = int(scoped_labels.isna().sum())
            rows.append(
                {
                    "dataset_id": profile.dataset_id,
                    "target_id": target.target_id,
                    "q_id": q_id,
                    "tail_share": float(tail_share),
                    "tau_minutes": int(tau_minutes),
                    "entity_id": str(entity),
                    "scope": scope,
                    "row_count": int(len(scoped)),
                    "known_label_count": known_count,
                    "positive_count": positive_count,
                    "negative_count": negative_count,
                    "unknown_count": unknown_count,
                    "unknown_missing_count": int(statuses.loc[scoped].eq("MISSING_VALUE").sum()),
                    "unknown_persistence_count": int(statuses.loc[scoped].isin([
                        "PERSISTENCE_HISTORY_INSUFFICIENT",
                        "TAIL_PERSISTENCE_NOT_MET_UNRESOLVED",
                    ]).sum()),
                    "nonpersistent_unresolved_count": int(
                        statuses.loc[scoped].eq("TAIL_PERSISTENCE_NOT_MET_UNRESOLVED").sum()
                    ),
                    # Retain the legacy column while making its former semantic count explicit as zero.
                    "nonpersistent_negative_count": 0,
                    "positive_event_count": _positive_event_count(scoped_labels),
                    "positive_prevalence_among_known": (positive_count / known_count) if known_count else pd.NA,
                    "median_cadence_minutes": cadence_by_entity[str(entity)],
                    "persistence_k": required_by_entity[str(entity)],
                    "scope_start": frame.loc[scoped, timestamp_column].min().isoformat() if len(scoped) else pd.NA,
                    "scope_end": frame.loc[scoped, timestamp_column].max().isoformat() if len(scoped) else pd.NA,
                }
            )
    return rows


def _positive_event_count(labels: pd.Series) -> int:
    positive = labels.eq(1).fillna(False)
    return int((positive & ~positive.shift(fill_value=False)).sum())
