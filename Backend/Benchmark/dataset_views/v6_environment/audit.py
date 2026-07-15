from __future__ import annotations

import json

import pandas as pd


def build_v6_distribution_frames(
    *,
    sequence_rows_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    kept_rows = sequence_rows_df.loc[sequence_rows_df["chunk_kept"].fillna(False)].copy()
    event_rows = kept_rows.loc[kept_rows["original_event_id"].notna()].copy()

    original_event_distribution_df = (
        event_rows.groupby(
            [
                "original_event_id",
                "continuity_segment_id",
                "candidate_event_type",
                "detailed_event_type",
                "final_train_label",
            ],
            dropna=False,
        )
        .agg(
            row_count=("original_event_id", "size"),
            target_loss_count=("target_loss_mask", lambda s: int(s.fillna(False).sum())),
            chunk_count=("chunk_id", "nunique"),
            day_count=("chunk_day_key", "nunique"),
            start_time=("original_event_start_time", "first"),
            confirmation_time=("original_event_confirmation_time", "first"),
            end_time=("original_event_end_time", "first"),
        )
        .reset_index()
        .convert_dtypes()
        if not event_rows.empty
        else pd.DataFrame(
            columns=[
                "original_event_id",
                "continuity_segment_id",
                "candidate_event_type",
                "detailed_event_type",
                "final_train_label",
                "row_count",
                "target_loss_count",
                "chunk_count",
                "day_count",
                "start_time",
                "confirmation_time",
                "end_time",
            ]
        ).convert_dtypes()
    )

    day_distribution_df = (
        kept_rows.groupby(["chunk_day_key", "final_train_label"], dropna=False)
        .agg(
            row_count=("final_train_label", "size"),
            target_loss_count=("target_loss_mask", lambda s: int(s.fillna(False).sum())),
            unique_chunk_count=("chunk_id", "nunique"),
            unique_original_event_count=("original_event_id", lambda s: int(s.dropna().nunique())),
        )
        .reset_index()
        .convert_dtypes()
        if not kept_rows.empty
        else pd.DataFrame(
            columns=[
                "chunk_day_key",
                "final_train_label",
                "row_count",
                "target_loss_count",
                "unique_chunk_count",
                "unique_original_event_count",
            ]
        ).convert_dtypes()
    )

    chunk_distribution_df = (
        kept_rows.groupby(["chunk_id", "chunk_day_key", "chunk_window_label", "final_train_label"], dropna=False)
        .agg(
            row_count=("final_train_label", "size"),
            target_loss_count=("target_loss_mask", lambda s: int(s.fillna(False).sum())),
            unique_original_event_count=("original_event_id", lambda s: int(s.dropna().nunique())),
        )
        .reset_index()
        .convert_dtypes()
        if not kept_rows.empty
        else pd.DataFrame(
            columns=[
                "chunk_id",
                "chunk_day_key",
                "chunk_window_label",
                "final_train_label",
                "row_count",
                "target_loss_count",
                "unique_original_event_count",
            ]
        ).convert_dtypes()
    )

    split_group_manifest_df = (
        kept_rows.groupby(["split_group_id", "split_group_kind"], dropna=False)
        .agg(
            row_count=("split_group_id", "size"),
            target_loss_count=("target_loss_mask", lambda s: int(s.fillna(False).sum())),
            unique_chunk_count=("chunk_id", "nunique"),
            unique_day_count=("chunk_day_key", "nunique"),
            unique_original_event_count=("original_event_id", lambda s: int(s.dropna().nunique())),
            unique_final_train_label_count=("final_train_label", lambda s: int(s.dropna().nunique())),
            final_train_label=("final_train_label", "first"),
            original_event_id=("original_event_id", "first"),
        )
        .reset_index()
        .convert_dtypes()
        if not kept_rows.empty
        else pd.DataFrame(
            columns=[
                "split_group_id",
                "split_group_kind",
                "row_count",
                "target_loss_count",
                "unique_chunk_count",
                "unique_day_count",
                "unique_original_event_count",
                "unique_final_train_label_count",
                "final_train_label",
                "original_event_id",
            ]
        ).convert_dtypes()
    )

    integrity_payload = build_v6_original_event_integrity_payload(sequence_rows_df=sequence_rows_df)
    return (
        original_event_distribution_df,
        day_distribution_df,
        chunk_distribution_df,
        split_group_manifest_df,
        integrity_payload,
    )


def build_v6_original_event_integrity_payload(
    *,
    sequence_rows_df: pd.DataFrame,
) -> dict[str, object]:
    event_rows = sequence_rows_df.loc[sequence_rows_df["original_event_id"].notna()].copy()
    issues: list[dict[str, object]] = []
    if not event_rows.empty:
        for original_event_id, group in event_rows.groupby("original_event_id", sort=False, dropna=False):
            continuity_count = int(group["continuity_segment_id"].astype("string").dropna().nunique())
            candidate_types = sorted(group["candidate_event_type"].astype("string").dropna().unique().tolist())
            detailed_types = sorted(group["detailed_event_type"].astype("string").dropna().unique().tolist())
            final_labels = sorted(group["final_train_label"].astype("string").dropna().unique().tolist())
            priority_reasons = sorted(group["candidate_priority_reason"].astype("string").dropna().unique().tolist())
            issue_reasons: list[str] = []
            if continuity_count != 1:
                issue_reasons.append("multiple_continuity_segments")
            if len(candidate_types) != 1:
                issue_reasons.append("multiple_candidate_types")
            if len(detailed_types) != 1:
                issue_reasons.append("multiple_detailed_types")
            if len(final_labels) != 1:
                issue_reasons.append("multiple_final_train_labels")
            if group["candidate_event_type"].isna().any():
                issue_reasons.append("missing_candidate_event_type")
            if group["candidate_priority_reason"].isna().any():
                issue_reasons.append("missing_candidate_priority_reason")
            if group["detailed_event_type"].isna().any():
                issue_reasons.append("missing_detailed_event_type")
            if group["final_train_label"].isna().any():
                issue_reasons.append("missing_final_train_label")
            if issue_reasons:
                issues.append(
                    {
                        "original_event_id": str(original_event_id),
                        "continuity_segment_count": continuity_count,
                        "candidate_event_types": candidate_types,
                        "candidate_priority_reasons": priority_reasons,
                        "detailed_event_types": detailed_types,
                        "final_train_labels": final_labels,
                        "row_count": int(len(group)),
                        "issue_reasons": issue_reasons,
                    }
                )
    return {
        "event_count": int(event_rows["original_event_id"].astype("string").dropna().nunique()) if not event_rows.empty else 0,
        "issue_count": len(issues),
        "issues": issues,
    }


def build_v6_audit_payloads(
    *,
    sequence_rows_df: pd.DataFrame,
    chunk_manifest_df: pd.DataFrame,
    discarded_chunks_df: pd.DataFrame,
    event_fragment_registry_df: pd.DataFrame,
    threshold_manifest_payload: dict[str, object],
    original_event_distribution_df: pd.DataFrame,
    day_distribution_df: pd.DataFrame,
    chunk_distribution_df: pd.DataFrame,
    split_group_manifest_df: pd.DataFrame,
    original_event_integrity_payload: dict[str, object],
) -> tuple[dict[str, object], dict[str, object], str]:
    kept_rows = sequence_rows_df.loc[sequence_rows_df["chunk_kept"].fillna(False)].copy()
    quality_payload = {
        "sequence_row_count": int(len(sequence_rows_df)),
        "kept_sequence_row_count": int(len(kept_rows)),
        "chunk_count": int(len(chunk_manifest_df)),
        "kept_chunk_count": int(chunk_manifest_df["chunk_kept"].fillna(False).sum()) if not chunk_manifest_df.empty else 0,
        "discarded_chunk_count": int(len(discarded_chunks_df)),
        "discard_reason_counts": (
            {str(key): int(value) for key, value in discarded_chunks_df.groupby("discard_reason", dropna=False).size().to_dict().items()}
            if not discarded_chunks_df.empty
            else {}
        ),
        "train_label_counts": (
            {str(key): int(value) for key, value in kept_rows.groupby("final_train_label", dropna=False).size().to_dict().items()}
            if not kept_rows.empty
            else {}
        ),
        "detailed_event_counts": (
            {str(key): int(value) for key, value in event_fragment_registry_df.groupby("detailed_event_type", dropna=False).size().to_dict().items()}
            if not event_fragment_registry_df.empty
            else {}
        ),
        "train_label_counts_by_original_event": (
            {str(key): int(value) for key, value in original_event_distribution_df.groupby("final_train_label", dropna=False).size().to_dict().items()}
            if not original_event_distribution_df.empty
            else {}
        ),
        "train_label_counts_by_day": (
            {str(key): int(value) for key, value in day_distribution_df.groupby("final_train_label", dropna=False).size().to_dict().items()}
            if not day_distribution_df.empty
            else {}
        ),
        "train_label_counts_by_chunk": (
            {str(key): int(value) for key, value in chunk_distribution_df.groupby("final_train_label", dropna=False).size().to_dict().items()}
            if not chunk_distribution_df.empty
            else {}
        ),
        "split_group_kind_counts": (
            {str(key): int(value) for key, value in split_group_manifest_df.groupby("split_group_kind", dropna=False).size().to_dict().items()}
            if not split_group_manifest_df.empty
            else {}
        ),
        "original_event_integrity": original_event_integrity_payload,
    }
    schema_payload = {
        "sequence_rows_columns": list(sequence_rows_df.columns),
        "chunk_manifest_columns": list(chunk_manifest_df.columns),
        "event_fragment_registry_columns": list(event_fragment_registry_df.columns),
        "original_event_distribution_columns": list(original_event_distribution_df.columns),
        "day_distribution_columns": list(day_distribution_df.columns),
        "chunk_distribution_columns": list(chunk_distribution_df.columns),
        "split_group_manifest_columns": list(split_group_manifest_df.columns),
    }
    markdown = "\n".join(
        [
            "# V6 Sequence Audit",
            "",
            f"- sequence rows: {quality_payload['sequence_row_count']}",
            f"- kept sequence rows: {quality_payload['kept_sequence_row_count']}",
            f"- chunks: {quality_payload['chunk_count']}",
            f"- kept chunks: {quality_payload['kept_chunk_count']}",
            f"- discarded chunks: {quality_payload['discarded_chunk_count']}",
            "",
            "## Train label counts",
            "",
            *(
                f"- {label}: {count}"
                for label, count in quality_payload["train_label_counts"].items()
            ),
            "",
            "## Detailed event counts",
            "",
            *(
                f"- {label}: {count}"
                for label, count in quality_payload["detailed_event_counts"].items()
            ),
            "",
            "## Label distribution by original event",
            "",
            *(
                f"- {label}: {count}"
                for label, count in quality_payload["train_label_counts_by_original_event"].items()
            ),
            "",
            "## Label distribution by day",
            "",
            *(
                f"- {label}: {count}"
                for label, count in quality_payload["train_label_counts_by_day"].items()
            ),
            "",
            "## Label distribution by chunk",
            "",
            *(
                f"- {label}: {count}"
                for label, count in quality_payload["train_label_counts_by_chunk"].items()
            ),
            "",
            "## Original-event integrity",
            "",
            f"- event count: {original_event_integrity_payload['event_count']}",
            f"- issue count: {original_event_integrity_payload['issue_count']}",
            "",
            "## Threshold manifest",
            "",
            "```json",
            json.dumps(threshold_manifest_payload, indent=2, ensure_ascii=False),
            "```",
        ]
    ).strip() + "\n"
    return quality_payload, schema_payload, markdown
