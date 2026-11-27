from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .worlds import (
    ACQUISITION_FEATURES,
    CURRENT_FEATURES,
    HISTORY_FEATURES,
    MOISTURE_HISTORY,
    TIMING_FEATURES,
    WorldDataset,
)


@dataclass(frozen=True)
class CalibrationRepresentation:
    representation_id: str
    feature_names: tuple[str, ...]
    frame: pd.DataFrame
    feature_groups: dict[str, list[str]]
    description: str


def build_representations(*, dataset: WorldDataset, disruption_seed: int) -> dict[str, CalibrationRepresentation]:
    """Build a fixed WADE representation ladder and disruption controls."""

    source = dataset.frame
    current = tuple(CURRENT_FEATURES)
    history = (*current, *HISTORY_FEATURES)
    reduced_rule = (*current, *MOISTURE_HISTORY)
    full_rule = (*reduced_rule, *TIMING_FEATURES)
    acquisition = tuple(ACQUISITION_FEATURES)
    representations: dict[str, CalibrationRepresentation] = {
        "S1_snapshot": _select(source, "S1_snapshot", current, {"snapshot": list(current)}, "current row only"),
        "S3_history": _select(source, "S3_history", history, {"snapshot": list(current), "history": list(HISTORY_FEATURES)}, "current row plus causal sensor history"),
        "S3_history_disrupted": _permuted(
            source,
            "S3_history_disrupted",
            history,
            history_columns=HISTORY_FEATURES,
            seed=disruption_seed,
            groups={"snapshot": list(current), "history_disrupted": list(HISTORY_FEATURES)},
            description="current row plus independently permuted history columns",
        ),
        "R_reduced": _select(source, "R_reduced", reduced_rule, {"snapshot": list(current), "rule_history": list(MOISTURE_HISTORY)}, "rule operands with timing operands removed"),
        "R_full": _select(source, "R_full", full_rule, {"snapshot": list(current), "rule_history": list(MOISTURE_HISTORY), "rule_timing": list(TIMING_FEATURES)}, "all operands of the deterministic rule"),
        "A_only": _select(source, "A_only", acquisition, {"acquisition": list(acquisition)}, "acquisition pattern only"),
        "S1_plus_A": _select(source, "S1_plus_A", (*current, *acquisition), {"snapshot": list(current), "acquisition": list(acquisition)}, "current row plus acquisition pattern"),
        "A_disrupted_only": _permuted(
            source,
            "A_disrupted_only",
            acquisition,
            history_columns=acquisition,
            seed=disruption_seed + 17,
            groups={"acquisition_disrupted": list(acquisition)},
            description="independently permuted acquisition pattern only",
        ),
    }
    _validate_representations(representations, sample_ids=source["sample_id"].astype("string"))
    return representations


def _select(
    source: pd.DataFrame,
    representation_id: str,
    feature_names: tuple[str, ...],
    groups: dict[str, list[str]],
    description: str,
) -> CalibrationRepresentation:
    return CalibrationRepresentation(
        representation_id=representation_id,
        feature_names=feature_names,
        frame=source.loc[:, ["sample_id", *feature_names]].copy(),
        feature_groups=groups,
        description=description,
    )


def _permuted(
    source: pd.DataFrame,
    representation_id: str,
    feature_names: tuple[str, ...],
    history_columns: tuple[str, ...],
    seed: int,
    groups: dict[str, list[str]],
    description: str,
) -> CalibrationRepresentation:
    output = source.loc[:, ["sample_id", *feature_names]].copy()
    rng = np.random.default_rng(seed)
    for column in history_columns:
        values = output[column].to_numpy(copy=True)
        output[column] = values[rng.permutation(len(values))]
    return CalibrationRepresentation(
        representation_id=representation_id,
        feature_names=feature_names,
        frame=output.convert_dtypes(),
        feature_groups=groups,
        description=description,
    )


def _validate_representations(representations: dict[str, CalibrationRepresentation], sample_ids: pd.Series) -> None:
    expected_ids = {
        "S1_snapshot",
        "S3_history",
        "S3_history_disrupted",
        "R_reduced",
        "R_full",
        "A_only",
        "S1_plus_A",
        "A_disrupted_only",
    }
    if set(representations) != expected_ids:
        raise ValueError(f"Representation contract drifted: {sorted(representations)}")
    expected_sample_ids = set(sample_ids)
    for representation in representations.values():
        frame_ids = set(representation.frame["sample_id"].astype("string"))
        if frame_ids != expected_sample_ids or representation.frame["sample_id"].duplicated().any():
            raise ValueError(f"Representation sample universe drifted: {representation.representation_id}")
        missing = sorted(set(representation.feature_names).difference(representation.frame.columns))
        if missing:
            raise ValueError(f"Representation {representation.representation_id} is missing fields: {missing}")
