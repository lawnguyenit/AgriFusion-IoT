from __future__ import annotations

import math

import pandas as pd

from .contracts import ExternalLabelConfig
from .profiles import ExternalLabelProfile


def build_cadence_registry(
    frame: pd.DataFrame,
    profile: ExternalLabelProfile,
    entity_key: str,
    config: ExternalLabelConfig,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for entity, group in frame.groupby(entity_key, sort=True):
        differences = group[profile.timestamp_column].sort_values().diff().dt.total_seconds().div(60).dropna()
        differences = differences.loc[differences.gt(0)]
        if differences.empty:
            raise ValueError(f"Cannot estimate cadence for entity {entity!r}.")
        median_cadence = float(differences.median())
        for tau in config.tau_minutes:
            rows.append(
                {
                    "dataset_id": profile.dataset_id,
                    "entity_id": str(entity),
                    "median_cadence_minutes": median_cadence,
                    "tau_minutes": int(tau),
                    "persistence_k": max(1, int(math.ceil(int(tau) / median_cadence))),
                    "strict_min_gap_minutes": median_cadence * config.min_gap_cadence_fraction,
                    "strict_max_gap_minutes": median_cadence * config.max_gap_cadence_fraction,
                }
            )
    return pd.DataFrame(rows)


def continuous_tail_run_lengths(
    frame: pd.DataFrame,
    tail_mask: pd.Series,
    timestamp_column: str,
    entity_key: str,
    cadence_by_entity: dict[str, float],
    config: ExternalLabelConfig,
) -> pd.Series:
    run_lengths = pd.Series(0, index=frame.index, dtype="int64")
    for entity, positions in frame.groupby(entity_key, sort=False).groups.items():
        previous_time = None
        previous_tail = False
        length = 0
        cadence = cadence_by_entity[str(entity)]
        min_gap = cadence * config.min_gap_cadence_fraction
        max_gap = cadence * config.max_gap_cadence_fraction
        for position in positions:
            now = frame.at[position, timestamp_column]
            is_tail = bool(tail_mask.at[position])
            delta = (now - previous_time).total_seconds() / 60 if previous_time is not None else None
            connected = delta is not None and min_gap <= delta <= max_gap
            length = (length + 1) if is_tail and connected and previous_tail else (1 if is_tail else 0)
            run_lengths.at[position] = length
            previous_time = now
            previous_tail = is_tail
    return run_lengths


def assign_binary_candidate(
    frame: pd.DataFrame,
    target_values: pd.Series,
    tail_mask: pd.Series,
    run_lengths: pd.Series,
    entity_key: str,
    cadence_by_entity: dict[str, float],
    tau_minutes: int,
) -> tuple[pd.Series, pd.Series, dict[str, int]]:
    labels = pd.Series(pd.NA, index=frame.index, dtype="Int8")
    statuses = pd.Series("MISSING_VALUE", index=frame.index, dtype="string")
    valid = target_values.notna()
    outside_tail = valid & ~tail_mask
    labels.loc[outside_tail] = 0
    statuses.loc[outside_tail] = "CURRENT_NOT_IN_TAIL"
    required_by_entity: dict[str, int] = {}
    for entity, positions in frame.groupby(entity_key, sort=False).groups.items():
        selected = pd.Index(positions)
        required_k = max(1, int(math.ceil(tau_minutes / cadence_by_entity[str(entity)])))
        required_by_entity[str(entity)] = required_k
        persistent = tail_mask.loc[selected] & run_lengths.loc[selected].ge(required_k)
        persistent_positions = selected[persistent.to_numpy(dtype=bool)]
        labels.loc[persistent_positions] = 1
        statuses.loc[persistent_positions] = "PERSISTENT_TAIL"
    statuses.loc[tail_mask & labels.isna()] = "TAIL_PERSISTENCE_NOT_MET"
    return labels, statuses, required_by_entity


def persistent_event_count(tail: pd.Series, run_lengths: pd.Series, required_k: int) -> int:
    return int((tail & run_lengths.eq(required_k)).sum())
