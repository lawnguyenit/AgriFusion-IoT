from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from Backend.Benchmark.dataset_views.continuity import attach_continuity_chunks
from Backend.Benchmark.weak_labels.v6.blocks import build_block_composition, build_block_labels
from Backend.Benchmark.weak_labels.v6.events import build_event_tables


@dataclass(frozen=True)
class V6LabelArtifacts:
    event_labels: pd.DataFrame
    block_composition: pd.DataFrame
    block_labels: pd.DataFrame
    boundary_event_audit: pd.DataFrame


def build_v6_label_artifacts(
    continuity_df: pd.DataFrame,
    *,
    segment_manifest: dict[str, object],
) -> V6LabelArtifacts:
    raw_event_df = attach_continuity_chunks(
        continuity_df,
        segment_manifest=segment_manifest,
        boundary_columns=("record.segment_boundary_before",),
        threshold_multiplier=2.5,
    ).rename(
        columns={
            "record.continuity_chunk_id": "raw_continuity_chunk_id",
            "record.continuity_chunk_index": "raw_continuity_chunk_index",
            "record.continuity_reset_before": "raw_continuity_reset_before",
            "record.continuity_reset_reason": "raw_continuity_reset_reason",
        }
    )

    event_artifacts = build_event_tables(raw_event_df)
    block_composition = build_block_composition(raw_event_df, event_artifacts.membership)
    block_labels = build_block_labels(block_composition)

    return V6LabelArtifacts(
        event_labels=event_artifacts.event_labels,
        block_composition=block_composition.convert_dtypes(),
        block_labels=block_labels.convert_dtypes(),
        boundary_event_audit=event_artifacts.boundary_event_audit,
    )
