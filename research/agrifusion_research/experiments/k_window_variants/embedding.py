from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


HISTORY_HORIZON_SECONDS = 3 * 60 * 60
DEFAULT_SEQUENCE_LENGTH = 12


@dataclass(frozen=True)
class SequenceBundle:
    sample_ids: list[str]
    values: np.ndarray
    row_mask: np.ndarray
    ages_hours: np.ndarray
    feature_names: list[str]
    sequence_length: int
    horizon_seconds: int


@dataclass(frozen=True)
class SequencePreprocessor:
    medians: np.ndarray
    scales: np.ndarray

    @classmethod
    def fit(cls, bundle: SequenceBundle, train_indices: np.ndarray) -> "SequencePreprocessor":
        train_values = bundle.values[train_indices]
        valid = np.isfinite(train_values)
        medians = np.nanmedian(np.where(valid, train_values, np.nan), axis=(0, 1))
        medians = np.where(np.isfinite(medians), medians, 0.0).astype(np.float32)
        centered = np.where(valid, train_values - medians.reshape(1, 1, -1), np.nan)
        scales = np.nanstd(centered, axis=(0, 1))
        scales = np.where(np.isfinite(scales) & (scales > 1e-6), scales, 1.0).astype(np.float32)
        return cls(medians=medians, scales=scales)

    def transform(self, bundle: SequenceBundle) -> np.ndarray:
        values = bundle.values.astype(np.float32, copy=True)
        valid = np.isfinite(values)
        normalized = np.where(
            valid,
            (values - self.medians.reshape(1, 1, -1)) / self.scales.reshape(1, 1, -1),
            0.0,
        ).astype(np.float32)
        missing = ((~valid) & bundle.row_mask[:, :, None]).astype(np.float32)
        ages = np.clip(bundle.ages_hours / 3.0, 0.0, 1.0).astype(np.float32)[:, :, None]
        observed_row = bundle.row_mask.astype(np.float32)[:, :, None]
        return np.concatenate([normalized, missing, ages, observed_row], axis=2).astype(np.float32)

    def to_json(self) -> dict[str, object]:
        return {"medians": self.medians.tolist(), "scales": self.scales.tolist()}


def build_causal_sequence_bundle(
    *,
    snapshot_frame: pd.DataFrame,
    feature_names: list[str],
    row_index: pd.DataFrame,
    sequence_length: int = DEFAULT_SEQUENCE_LENGTH,
) -> SequenceBundle:
    """Build fixed-length sequences ending at each anchor using only X_<=t."""

    if sequence_length < 2:
        raise ValueError("sequence_length must be at least two")
    required = {"record.id", "record.node_id", "record.segment_id", "record.ts_sample", "source_row_position"}
    missing = sorted(required.difference(row_index.columns))
    if missing:
        raise ValueError(f"Row index is missing sequence columns: {missing}")
    if snapshot_frame["sample_id"].duplicated().any():
        raise ValueError("Snapshot feature frame must be unique by sample_id.")
    ordered = row_index.loc[:, [
        "record.id", "record.node_id", "record.segment_id", "record.ts_sample", "source_row_position"
    ]].rename(columns={"record.id": "sample_id"}).copy()
    ordered["sample_id"] = ordered["sample_id"].astype("string")
    ordered["record.node_id"] = ordered["record.node_id"].astype("string")
    ordered["record.segment_id"] = ordered["record.segment_id"].astype("string")
    ordered["record.ts_sample"] = pd.to_numeric(ordered["record.ts_sample"], errors="coerce")
    if ordered["record.ts_sample"].isna().any():
        raise ValueError("All sequence timestamps must be numeric.")
    ordered = ordered.sort_values(
        ["record.node_id", "record.segment_id", "record.ts_sample", "source_row_position"],
        kind="stable",
    ).reset_index(drop=True)
    if ordered["sample_id"].duplicated().any():
        raise ValueError("Sequence row index must be unique by sample_id.")
    feature_values = snapshot_frame.set_index("sample_id").loc[ordered["sample_id"].tolist(), feature_names].apply(
        pd.to_numeric, errors="coerce"
    )
    value_array = feature_values.to_numpy(dtype=np.float32)
    sample_count = len(ordered)
    channel_count = len(feature_names)
    sequences = np.full((sample_count, sequence_length, channel_count), np.nan, dtype=np.float32)
    row_mask = np.zeros((sample_count, sequence_length), dtype=bool)
    ages_hours = np.zeros((sample_count, sequence_length), dtype=np.float32)

    for _, group in ordered.groupby(["record.node_id", "record.segment_id"], sort=False, dropna=False):
        positions = group.index.to_numpy(dtype=int)
        timestamps = ordered.loc[positions, "record.ts_sample"].to_numpy(dtype=np.int64)
        for local_position, output_position in enumerate(positions):
            current_ts = int(timestamps[local_position])
            prior_or_current = positions[: local_position + 1]
            prior_timestamps = timestamps[: local_position + 1]
            eligible = prior_timestamps >= current_ts - HISTORY_HORIZON_SECONDS
            selected_positions = prior_or_current[eligible][-sequence_length:]
            selected_timestamps = prior_timestamps[eligible][-sequence_length:]
            start = sequence_length - len(selected_positions)
            if len(selected_positions):
                sequences[output_position, start:, :] = value_array[selected_positions]
                row_mask[output_position, start:] = True
                ages_hours[output_position, start:] = (
                    (current_ts - selected_timestamps) / 3600.0
                ).astype(np.float32)

    return SequenceBundle(
        sample_ids=ordered["sample_id"].astype(str).tolist(),
        values=sequences,
        row_mask=row_mask,
        ages_hours=ages_hours,
        feature_names=list(feature_names),
        sequence_length=sequence_length,
        horizon_seconds=HISTORY_HORIZON_SECONDS,
    )
