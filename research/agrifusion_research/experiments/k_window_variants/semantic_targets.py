from __future__ import annotations

from pathlib import Path

import pandas as pd

from .targets import (
    LOW_TEMPORAL,
    REF_TEMPORAL,
    UNRES_TEMPORAL,
    load_temporal_target_frame,
)


Y_ONLINE = "temporal_online_3h"
Y_EVENT = "temporal_event_3h"
TARGET_LABELS = (LOW_TEMPORAL, UNRES_TEMPORAL, REF_TEMPORAL)


def load_online_event_target_frame(
    *,
    native_release_dir: Path,
    protocol_run_dir: Path,
    target_view_run_dir: Path,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Join paired online/event targets to the locked current protocol."""

    protocol_frame, base_metadata = load_temporal_target_frame(
        native_release_dir=native_release_dir,
        protocol_run_dir=protocol_run_dir,
    )
    target_rows = pd.read_parquet(
        target_view_run_dir.resolve() / "target_views_assignments.parquet"
    ).convert_dtypes()
    target_rows = target_rows.loc[target_rows["target_view_id"].astype("string").isin([Y_ONLINE, Y_EVENT])].copy()
    target_rows["sample_id"] = target_rows["sample_id"].astype("string")
    if target_rows.duplicated(["sample_id", "target_view_id"]).any():
        raise ValueError("Paired target-view artifact is not unique by sample_id and target_view_id.")
    pivot_frames: list[pd.DataFrame] = []
    for target_view_id, prefix in ((Y_ONLINE, "online"), (Y_EVENT, "event")):
        view = target_rows.loc[target_rows["target_view_id"].eq(target_view_id), [
            "sample_id", "label_name", "label_status", "intrinsic_eligibility"
        ]].rename(columns={
            "label_name": f"label_{prefix}",
            "label_status": f"label_status_{prefix}",
            "intrinsic_eligibility": f"intrinsic_eligibility_{prefix}",
        })
        pivot_frames.append(view)
    lineage = target_rows.loc[target_rows["target_view_id"].eq(Y_ONLINE), [
        "sample_id", "point_label", "support_depth_at_anchor", "eventual_run_length",
        "run_complete", "required_k", "unres_origin", "target_pair_status",
        "event_vs_online_changed", "m_relation_to_q", "moisture_value", "q_threshold",
    ]].rename(columns={
        "support_depth_at_anchor": "target_support_depth_at_anchor",
        "required_k": "target_required_k",
    }).drop_duplicates("sample_id", keep=False)
    frame = protocol_frame.merge(pivot_frames[0], on="sample_id", how="left", validate="one_to_one")
    frame = frame.merge(pivot_frames[1], on="sample_id", how="left", validate="one_to_one")
    frame = frame.merge(lineage, on="sample_id", how="left", validate="one_to_one")
    trainable = frame["final_trainability"].fillna(False).astype(bool)
    missing_online = trainable & frame["label_online"].isna()
    missing_event = trainable & frame["label_event"].isna()
    if missing_online.any() or missing_event.any():
        raise ValueError(
            "Online/event target artifact does not cover all trainable protocol rows: "
            f"online_missing={int(missing_online.sum())}, event_missing={int(missing_event.sum())}"
        )
    online_mismatch = trainable & frame["label_online"].astype("string").ne(frame["protocol_label"])
    if online_mismatch.any():
        raise ValueError("Online target view disagrees with the native protocol on trainable rows.")
    protocol_support = pd.to_numeric(frame["support_depth_at_anchor"], errors="coerce").fillna(0).astype(int)
    target_support = pd.to_numeric(frame["target_support_depth_at_anchor"], errors="coerce").fillna(0).astype(int)
    support_mismatch = trainable & protocol_support.ne(target_support)
    if support_mismatch.any():
        raise ValueError("Target-view support depth disagrees with the protocol on trainable rows.")
    frame["support_depth_at_anchor"] = protocol_support
    if not frame.loc[trainable, "label_status_event"].astype("string").eq("LABELED").all():
        raise ValueError("The event target contains non-labeled rows in the trainable protocol cohort.")
    for column in ("label_online", "label_event"):
        invalid = trainable & ~frame[column].astype("string").isin(TARGET_LABELS)
        if invalid.any():
            raise ValueError(f"Unexpected model label in {column}: {sorted(frame.loc[invalid, column].astype('string').unique().tolist())}")
    frame["eventual_run_length"] = pd.to_numeric(frame["eventual_run_length"], errors="coerce").astype("Int64")
    frame["required_k"] = pd.to_numeric(frame["required_k"], errors="coerce").fillna(3).astype(int)
    metadata = {
        **base_metadata,
        "target_view_run_dir": str(target_view_run_dir.resolve()),
        "target_view_ids": [Y_ONLINE, Y_EVENT],
        "online_trainable_counts": frame.loc[trainable, "label_online"].value_counts().to_dict(),
        "event_trainable_counts": frame.loc[trainable, "label_event"].value_counts().to_dict(),
        "changed_trainable_rows": int((trainable & frame["event_vs_online_changed"].fillna(False).astype(bool)).sum()),
    }
    return frame.convert_dtypes(), metadata
