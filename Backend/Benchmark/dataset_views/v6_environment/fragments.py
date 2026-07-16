from __future__ import annotations

import pandas as pd

from Backend.Benchmark.dataset_views.configs import V6_AUXILIARY_FEATURE_COLUMNS, V6_PRIMARY_FEATURE_COLUMNS


def build_view_frames(sequence_rows_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    kept = sequence_rows_df.loc[sequence_rows_df["chunk_kept"].fillna(False)].copy()
    x_columns = [column for column in V6_PRIMARY_FEATURE_COLUMNS if column in kept.columns]
    y_columns = [
        "final_train_label",
    ]
    index_columns = [
        "chunk_id",
        "chunk_day_key",
        "chunk_window_label",
        "chunk_timestep_index",
        "sequence.timestamp_grid",
        "sequence.timestamp_grid_iso",
        "sequence.source_record_id",
        "target_loss_mask",
        "online_stage",
        "candidate_event_type",
        "candidate_priority_reason",
        "detailed_event_type",
        "final_train_label",
        "event_id",
        "split_group_id",
        "split_group_kind",
        "original_event_id",
        "original_event_start_time",
        "original_event_confirmation_time",
        "original_event_end_time",
        "original_event_step_index",
        "original_event_run_length",
        "event_start_time",
        "event_confirmation_time",
        "event_end_time",
        "fragment_at_chunk_start",
        "fragment_at_chunk_end",
        "crosses_chunk_boundary",
    ]
    auxiliary_columns = [column for column in V6_AUXILIARY_FEATURE_COLUMNS if column in kept.columns]
    return (
        kept.loc[:, x_columns].copy(),
        kept.loc[:, y_columns].copy(),
        kept.loc[:, [column for column in (*index_columns, *auxiliary_columns) if column in kept.columns]].copy(),
    )


def annotate_chunk_fragments(
    chunk_slice: pd.DataFrame,
    *,
    fragment_rows: list[dict[str, object]],
) -> pd.DataFrame:
    annotated = chunk_slice.sort_values(["sequence.timestamp_grid", "sequence.grid_index"], kind="stable").reset_index(drop=True)
    annotated["event_id"] = pd.Series([pd.NA] * len(annotated), dtype="string")
    annotated["event_start_time"] = pd.Series([pd.NA] * len(annotated), dtype="string")
    annotated["event_confirmation_time"] = pd.Series([pd.NA] * len(annotated), dtype="string")
    annotated["event_end_time"] = pd.Series([pd.NA] * len(annotated), dtype="string")
    annotated["fragment_at_chunk_start"] = pd.Series([False] * len(annotated), dtype="boolean")
    annotated["fragment_at_chunk_end"] = pd.Series([False] * len(annotated), dtype="boolean")
    annotated["crosses_chunk_boundary"] = pd.Series([False] * len(annotated), dtype="boolean")
    annotated["split_group_id"] = pd.Series([pd.NA] * len(annotated), dtype="string")
    annotated["split_group_kind"] = pd.Series(["normal_chunk"] * len(annotated), dtype="string")
    if "target_loss_mask" not in annotated.columns:
        annotated["target_loss_mask"] = annotated["sequence.observed_mask"].fillna(False).astype("boolean")

    event_counter = 0
    normal_group_id = f"normal_chunk::{str(annotated.loc[0, 'chunk_id'])}"
    normal_mask = annotated["original_event_id"].isna()
    annotated.loc[normal_mask, "split_group_id"] = normal_group_id

    event_positions = annotated.index[annotated["original_event_id"].notna()].tolist()
    run_start: int | None = None
    active_original_event_id: str | None = None
    for position in event_positions + [len(annotated)]:
        if position == len(annotated):
            current_original_event_id = None
        else:
            current_original_event_id = str(annotated.loc[position, "original_event_id"])
        if active_original_event_id is None:
            run_start = position if position != len(annotated) else None
            active_original_event_id = current_original_event_id
            continue
        if current_original_event_id == active_original_event_id:
            continue
        if run_start is not None and active_original_event_id is not None:
            event_counter += 1
            _finalize_fragment_run(
                annotated,
                start_pos=run_start,
                end_pos=position - 1,
                event_counter=event_counter,
                fragment_rows=fragment_rows,
            )
        run_start = position if position != len(annotated) else None
        active_original_event_id = current_original_event_id
    return annotated


def _finalize_fragment_run(
    annotated: pd.DataFrame,
    *,
    start_pos: int,
    end_pos: int,
    event_counter: int,
    fragment_rows: list[dict[str, object]],
) -> None:
    event_id = f"{str(annotated.loc[0, 'chunk_id'])}_evt_{event_counter:04d}"
    run_indices = list(range(start_pos, end_pos + 1))
    run_length = len(run_indices)
    fragment_start_time = str(annotated.loc[start_pos, "sequence.timestamp_grid_iso"])
    fragment_end_time = str(annotated.loc[end_pos, "sequence.timestamp_grid_iso"])
    original_event_id = str(annotated.loc[start_pos, "original_event_id"])
    candidate_type = str(annotated.loc[start_pos, "candidate_event_type"])
    detailed_event_type = str(annotated.loc[start_pos, "detailed_event_type"])
    final_train_label = str(annotated.loc[start_pos, "final_train_label"])
    original_start = (
        str(annotated.loc[start_pos, "original_event_start_time"])
        if pd.notna(annotated.loc[start_pos, "original_event_start_time"])
        else fragment_start_time
    )
    original_confirmation = annotated.loc[start_pos, "original_event_confirmation_time"]
    original_end = (
        str(annotated.loc[start_pos, "original_event_end_time"])
        if pd.notna(annotated.loc[start_pos, "original_event_end_time"])
        else fragment_end_time
    )
    fragment_at_chunk_start = bool(fragment_start_time != original_start)
    fragment_at_chunk_end = bool(fragment_end_time != original_end)
    crosses_chunk_boundary = fragment_at_chunk_start or fragment_at_chunk_end

    for position in run_indices:
        annotated.loc[position, "event_id"] = event_id
        annotated.loc[position, "event_start_time"] = original_start
        annotated.loc[position, "event_confirmation_time"] = original_confirmation
        annotated.loc[position, "event_end_time"] = original_end
        annotated.loc[position, "fragment_at_chunk_start"] = fragment_at_chunk_start
        annotated.loc[position, "fragment_at_chunk_end"] = fragment_at_chunk_end
        annotated.loc[position, "crosses_chunk_boundary"] = crosses_chunk_boundary
        annotated.loc[position, "split_group_id"] = original_event_id
        annotated.loc[position, "split_group_kind"] = "original_event"

    fragment_rows.append(
        {
            "chunk_id": str(annotated.loc[0, "chunk_id"]),
            "event_id": event_id,
            "original_event_id": original_event_id,
            "continuity_segment_id": str(annotated.loc[start_pos, "continuity_segment_id"]),
            "candidate_event_type": candidate_type,
            "detailed_event_type": detailed_event_type,
            "final_train_label": final_train_label,
            "fragment_length": run_length,
            "event_start_time": original_start,
            "event_confirmation_time": original_confirmation,
            "event_end_time": original_end,
            "fragment_start_time": fragment_start_time,
            "fragment_end_time": fragment_end_time,
            "fragment_at_chunk_start": fragment_at_chunk_start,
            "fragment_at_chunk_end": fragment_at_chunk_end,
            "crosses_chunk_boundary": crosses_chunk_boundary,
        }
    )
