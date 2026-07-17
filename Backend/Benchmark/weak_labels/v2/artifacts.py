from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from Backend.Benchmark.dataset_views.configs.windowing import V2_MEASUREMENT_CHANNELS
from Backend.Benchmark.dataset_views.windowing.builder import build_v2_sensor_window_view
from Backend.Benchmark.weak_labels.shared.configs import V2_SAME_Y_TASK_IDS, V2_TEMPORAL_TASK_IDS
from Backend.Benchmark.weak_labels.v2.frames import (
    build_label_agreement,
    build_matched_cohort_manifest,
    build_same_y_frame,
    build_temporal_labels,
    resolve_v2_intrinsic_state,
)


@dataclass(frozen=True)
class V2LabelArtifacts:
    same_y_labels: pd.DataFrame
    temporal_evidence_3h: pd.DataFrame
    temporal_evidence_8h: pd.DataFrame
    temporal_labels_3h: pd.DataFrame
    temporal_labels_8h: pd.DataFrame
    matched_cohort_manifest: pd.DataFrame
    label_agreement_3h_8h: pd.DataFrame


def build_v2_label_artifacts(
    continuity_df: pd.DataFrame,
    *,
    segment_manifest: dict[str, object],
    boundary_timestamps: dict[str, int],
) -> V2LabelArtifacts:
    horizon_outputs: dict[str, tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]] = {}
    same_y_frames: list[pd.DataFrame] = []
    matched_frames: list[pd.DataFrame] = []
    point_lookup = continuity_df.set_index("record.id")

    for horizon_name, task_same_y, task_temporal, purge_seconds in (
        ("3h", V2_SAME_Y_TASK_IDS[0], V2_TEMPORAL_TASK_IDS[0], 3 * 3600),
        ("8h", V2_SAME_Y_TASK_IDS[1], V2_TEMPORAL_TASK_IDS[1], 8 * 3600),
    ):
        artifacts = build_v2_sensor_window_view(
            continuity_df,
            measurement_columns=V2_MEASUREMENT_CHANNELS,
            segment_manifest=segment_manifest,
            selected_horizon_names=(horizon_name,),
        )
        audit_df = artifacts.audit_frame.copy()
        audit_df["record.id"] = continuity_df["record.id"].astype("string")
        audit_df["record.segment_id"] = continuity_df["record.segment_id"].astype("string")
        audit_df["point_label_status"] = continuity_df["point_label_status"].astype("string")
        audit_df["point_train_label_name"] = continuity_df["point_train_label_name"].astype("string")
        audit_df["low_run_length_ending_at_point"] = continuity_df["low_run_length_ending_at_point"].astype("Int64")
        audit_df["positive_environmental_evidence_count"] = continuity_df["positive_environmental_evidence_count"].astype("Int64")
        audit_df["record.continuity_chunk_id"] = continuity_df["record.continuity_chunk_id"].astype("string")
        audit_df["record.ts_sample"] = pd.to_numeric(continuity_df["record.ts_sample"], errors="coerce").astype("int64")

        intrinsic_eligibility, exclusion_reason = resolve_v2_intrinsic_state(
            audit_df=audit_df,
            boundary_timestamps=boundary_timestamps,
            purge_seconds=purge_seconds,
        )
        audit_df["intrinsic_eligibility"] = intrinsic_eligibility.astype("boolean")
        audit_df["intrinsic_exclusion_reason"] = exclusion_reason.astype("string")

        same_y_df = build_same_y_frame(audit_df, task_id=task_same_y)
        temporal_labels = build_temporal_labels(audit_df, task_id=task_temporal)
        evidence_df = audit_df.copy().convert_dtypes()
        evidence_df["task_id"] = task_temporal
        evidence_df["label_task_id"] = task_temporal
        evidence_df["window_horizon_name"] = horizon_name

        same_y_frames.append(same_y_df)
        matched_frames.append(build_matched_cohort_manifest(same_y_df, horizon_name=horizon_name, task_id=task_same_y))
        horizon_outputs[horizon_name] = (evidence_df, temporal_labels, same_y_df)
    agreement_df = build_label_agreement(horizon_outputs["3h"][1], horizon_outputs["8h"][1])

    return V2LabelArtifacts(
        same_y_labels=pd.concat(same_y_frames, ignore_index=True).convert_dtypes(),
        temporal_evidence_3h=horizon_outputs["3h"][0].convert_dtypes(),
        temporal_evidence_8h=horizon_outputs["8h"][0].convert_dtypes(),
        temporal_labels_3h=horizon_outputs["3h"][1].convert_dtypes(),
        temporal_labels_8h=horizon_outputs["8h"][1].convert_dtypes(),
        matched_cohort_manifest=pd.concat(matched_frames, ignore_index=True).convert_dtypes(),
        label_agreement_3h_8h=agreement_df.convert_dtypes(),
    )
