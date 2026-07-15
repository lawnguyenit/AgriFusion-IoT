from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class V6Artifacts:
    sequence_rows_df: pd.DataFrame
    kept_sequence_rows_df: pd.DataFrame
    chunk_manifest_df: pd.DataFrame
    discarded_chunks_df: pd.DataFrame
    event_fragment_registry_df: pd.DataFrame
    original_event_distribution_df: pd.DataFrame
    day_distribution_df: pd.DataFrame
    chunk_distribution_df: pd.DataFrame
    split_group_manifest_df: pd.DataFrame
    threshold_manifest_payload: dict[str, object]
    original_event_integrity_payload: dict[str, object]
    dataset_manifest_payload: dict[str, object]
    schema_payload: dict[str, object]
    quality_report_payload: dict[str, object]
    audit_report_markdown: str
