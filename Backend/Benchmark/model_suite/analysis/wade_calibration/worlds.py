from __future__ import annotations

from dataclasses import dataclass
from math import ceil

import numpy as np
import pandas as pd


WORLD_IDS = ("W_S", "W_H", "W_R", "W_A")
CLASS_NAMES = ("LOW", "UNRES", "REF")
CURRENT_FEATURES = ("M_t", *[f"S{i}_t" for i in range(1, 9)])
HISTORY_FEATURES = tuple(
    f"{feature}_lag{lag}"
    for lag in (1, 2)
    for feature in CURRENT_FEATURES
)
TIMING_FEATURES = ("delta_lag1_hours", "delta_lag2_hours")
ACQUISITION_FEATURES = ("acq_gap_flag", "missing_lag_count", "coverage_ratio")
MOISTURE_HISTORY = ("M_t_lag1", "M_t_lag2")


@dataclass(frozen=True)
class WorldDataset:
    world_id: str
    frame: pd.DataFrame
    metadata: dict[str, object]


def generate_world(*, world_id: str, n_samples: int = 8_000, data_seed: int = 20260923) -> WorldDataset:
    """Generate one mechanism-controlled world with a shared row contract."""

    if world_id not in WORLD_IDS:
        raise ValueError(f"Unknown controlled world: {world_id}")
    if n_samples < 600:
        raise ValueError("Controlled worlds need at least 600 rows for disjoint splits.")

    rng = np.random.default_rng(data_seed)
    sequence_ids, time_indices = _sequence_layout(n_samples=n_samples, rng=rng)
    if world_id == "W_S":
        moisture = _smooth_moisture(n_samples=n_samples, sequence_ids=sequence_ids, rng=rng)
        deltas = rng.uniform(0.85, 1.15, size=(n_samples, 2))
        mechanism = "snapshot_sufficient_high_autocorrelation"
    elif world_id == "W_H":
        moisture = _independent_moisture(n_samples=n_samples, rng=rng)
        deltas = rng.uniform(0.85, 1.15, size=(n_samples, 2))
        mechanism = "history_required_snapshot_aliasing"
    elif world_id == "W_R":
        moisture = _independent_moisture(n_samples=n_samples, rng=rng)
        deltas = rng.uniform(0.25, 2.50, size=(n_samples, 2))
        mechanism = "deterministic_rule_reconstruction"
    else:
        moisture = _independent_moisture(n_samples=n_samples, rng=rng)
        deltas = rng.uniform(0.85, 1.15, size=(n_samples, 2))
        mechanism = "acquisition_shortcut"

    current_m, lag1, lag2 = moisture.T
    support_current = rng.normal(loc=0.0, scale=1.0, size=(n_samples, 8))
    support_lag1 = support_current + rng.normal(loc=0.0, scale=0.20, size=(n_samples, 8))
    support_lag2 = support_lag1 + rng.normal(loc=0.0, scale=0.20, size=(n_samples, 8))

    if world_id == "W_A":
        labels = rng.choice(CLASS_NAMES, size=n_samples, p=(1 / 3, 1 / 3, 1 / 3))
    else:
        labels = _persistence_labels(
            current=current_m,
            lag1=lag1,
            lag2=lag2,
            deltas=deltas,
            use_gap_rule=world_id == "W_R",
        )

    acquisition = _acquisition_features(labels=labels, rng=rng, correlated=world_id == "W_A")
    label_series = pd.Series(labels, dtype="string")
    frame = pd.DataFrame(
        {
            "sample_id": [f"{world_id}_{index:06d}" for index in range(n_samples)],
            "sequence_id": sequence_ids,
            "time_index": time_indices,
            "M_t": current_m,
            "M_t_lag1": lag1,
            "M_t_lag2": lag2,
            **{f"S{i}_t": support_current[:, i - 1] for i in range(1, 9)},
            **{f"S{i}_t_lag1": support_lag1[:, i - 1] for i in range(1, 9)},
            **{f"S{i}_t_lag2": support_lag2[:, i - 1] for i in range(1, 9)},
            "delta_lag1_hours": deltas[:, 0],
            "delta_lag2_hours": deltas[:, 1],
            **acquisition,
            "label": label_series,
            "oracle_label": label_series.copy(),
        }
    )
    frame["partition"] = _assign_partitions(sequence_ids=sequence_ids, rng=rng)
    frame = frame.convert_dtypes()
    metadata = {
        "world_id": world_id,
        "mechanism": mechanism,
        "data_seed": data_seed,
        "row_count": int(len(frame)),
        "class_counts": {str(key): int(value) for key, value in frame["label"].value_counts().items()},
        "feature_contract": {
            "snapshot": list(CURRENT_FEATURES),
            "history": list((*CURRENT_FEATURES, *HISTORY_FEATURES)),
            "timing": list(TIMING_FEATURES),
            "acquisition": list(ACQUISITION_FEATURES),
            "rule_operands": list(("M_t", "M_t_lag1", "M_t_lag2", *TIMING_FEATURES)),
        },
        "oracle": _oracle_description(world_id),
        "split_policy": "sequence_disjoint train=60%, validation=20%, test=20%",
    }
    return WorldDataset(world_id=world_id, frame=frame, metadata=metadata)


def _sequence_layout(*, n_samples: int, rng: np.random.Generator, sequence_length: int = 20) -> tuple[np.ndarray, np.ndarray]:
    sequence_count = ceil(n_samples / sequence_length)
    sequence_ids = np.repeat(np.arange(sequence_count, dtype=np.int64), sequence_length)[:n_samples]
    time_indices = np.tile(np.arange(sequence_length, dtype=np.int64), sequence_count)[:n_samples]
    return sequence_ids, time_indices


def _smooth_moisture(*, n_samples: int, sequence_ids: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    values = np.empty((n_samples, 3), dtype=float)
    for sequence_id in np.unique(sequence_ids):
        indices = np.flatnonzero(sequence_ids == sequence_id)
        series = np.empty(len(indices) + 2, dtype=float)
        series[0] = rng.uniform(30.0, 70.0)
        series[1] = series[0] + rng.normal(0.0, 0.15)
        for index in range(2, len(series)):
            series[index] = 0.995 * series[index - 1] + 0.005 * 50.0 + rng.normal(0.0, 0.15)
        values[indices, 0] = series[2:]
        values[indices, 1] = series[1:-1]
        values[indices, 2] = series[:-2]
    return values


def _independent_moisture(*, n_samples: int, rng: np.random.Generator) -> np.ndarray:
    return rng.uniform(25.0, 75.0, size=(n_samples, 3))


def _persistence_labels(
    *,
    current: np.ndarray,
    lag1: np.ndarray,
    lag2: np.ndarray,
    deltas: np.ndarray,
    use_gap_rule: bool,
) -> np.ndarray:
    low = (current < 45.0) & (lag1 < 45.0) & (lag2 < 45.0)
    if use_gap_rule:
        low &= (deltas[:, 0] < 1.50) & (deltas[:, 1] < 1.50)
    reference = current >= 60.0
    return np.select((low, reference), ("LOW", "REF"), default="UNRES").astype(object)


def _acquisition_features(*, labels: np.ndarray, rng: np.random.Generator, correlated: bool) -> dict[str, np.ndarray]:
    if correlated:
        gap_probability = np.select(
            [labels == "LOW", labels == "UNRES", labels == "REF"],
            [0.995, 0.15, 0.005],
            default=0.50,
        )
        gap = (rng.random(len(labels)) < gap_probability).astype(int)
    else:
        gap = (rng.random(len(labels)) < 0.20).astype(int)
    missing = gap * 2 + rng.binomial(1, 0.08, size=len(labels))
    coverage = np.clip(1.0 - missing / 3.0, 0.0, 1.0)
    return {
        "acq_gap_flag": gap,
        "missing_lag_count": missing,
        "coverage_ratio": coverage,
    }


def _assign_partitions(*, sequence_ids: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    unique_sequences = np.unique(sequence_ids)
    shuffled = rng.permutation(unique_sequences)
    train_end = int(len(shuffled) * 0.60)
    validation_end = int(len(shuffled) * 0.80)
    mapping = {
        int(sequence): partition
        for sequence, partition in zip(
            shuffled,
            ("train",) * train_end
            + ("validation",) * (validation_end - train_end)
            + ("test",) * (len(shuffled) - validation_end),
            strict=True,
        )
    }
    return np.array([mapping[int(sequence)] for sequence in sequence_ids], dtype=object)


def _oracle_description(world_id: str) -> dict[str, object]:
    if world_id == "W_S":
        return {"type": "persistence_rule", "claim": "current snapshot is nearly sufficient because moisture is highly autocorrelated"}
    if world_id == "W_H":
        return {"type": "persistence_rule", "claim": "current moisture aliases histories with different persistence states"}
    if world_id == "W_R":
        return {"type": "deterministic_rule", "claim": "LOW requires current/lag moisture below threshold and both timing operands below 1.5 hours"}
    return {"type": "latent_class_with_acquisition_correlation", "claim": "sensor state is independent; acquisition features are correlated with the latent class"}
