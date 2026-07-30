from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from Backend.Benchmark.evaluation_protocols.lineage.fold_support import (
    append_matched_rows_for_fold,
    build_fold_manifest_rows,
    build_unsupported_rows_for_fold,
)
from Backend.Benchmark.evaluation_protocols.lineage.point_v2 import (
    build_fold_point_assignments,
    build_fold_v2_assignments,
    build_p1_base_assignments,
    build_p2_base_assignments,
    build_p2_holdout_view_assignments,
)


@dataclass(frozen=True)
class ProtocolAssignmentArtifacts:
    fold_manifest: pd.DataFrame
    unsupported_class_audit: pd.DataFrame
    base_split_assignments: pd.DataFrame
    view_split_assignments: pd.DataFrame
    matched_cohorts: dict[str, pd.DataFrame]


def build_protocol_assignment_artifacts(
    *,
    fold_specs,
    working: pd.DataFrame,
    point_labels: pd.DataFrame,
    v2_same_y: pd.DataFrame,
    v2_temporal_3h: pd.DataFrame,
    v2_temporal_8h: pd.DataFrame,
    v2_evidence_3h: pd.DataFrame,
    v2_evidence_8h: pd.DataFrame,
    expected_interval_sec: int,
) -> ProtocolAssignmentArtifacts:
    record_lookup = working.loc[
        :,
        ["record.id", "record.segment_id", "record.ts_sample", "timestamp_local", "deployment_domain_name"],
    ].copy()
    record_time = record_lookup.set_index("record.id")["timestamp_local"].to_dict()
    record_domain = record_lookup.set_index("record.id")["deployment_domain_name"].astype("string").to_dict()
    record_segment = record_lookup.set_index("record.id")["record.segment_id"].astype("string").to_dict()
    p1_records = record_lookup.loc[record_lookup["deployment_domain_name"].astype("string") == "P1_SOURCE"].copy()
    p2_records = record_lookup.loc[record_lookup["deployment_domain_name"].astype("string") == "P2_TARGET"].copy()

    point_labels = point_labels.copy()
    point_labels["deployment_domain_name"] = point_labels["sample_id"].astype("string").map(record_domain)
    same_y_labels = v2_same_y.copy()
    same_y_labels["deployment_domain_name"] = same_y_labels["sample_id"].astype("string").map(record_domain)
    temporal_3h_labels = v2_temporal_3h.copy()
    temporal_3h_labels["deployment_domain_name"] = temporal_3h_labels["sample_id"].astype("string").map(record_domain)
    temporal_8h_labels = v2_temporal_8h.copy()
    temporal_8h_labels["deployment_domain_name"] = temporal_8h_labels["sample_id"].astype("string").map(record_domain)

    label_frames: dict[str, pd.DataFrame] = {
        "v0_point_train": point_labels.loc[point_labels["task_id"] == "v0_point_train"].copy(),
        "v1_point_train": point_labels.loc[point_labels["task_id"] == "v1_point_train"].copy(),
        "v2_same_y_3h": same_y_labels.loc[same_y_labels["task_id"] == "v2_same_y_3h"].copy(),
        "v2_same_y_8h": same_y_labels.loc[same_y_labels["task_id"] == "v2_same_y_8h"].copy(),
        "v2_temporal_3h": temporal_3h_labels.copy(),
        "v2_temporal_8h": temporal_8h_labels.copy(),
    }
    v2_group_lookup = {
        "v2_same_y_3h": v2_evidence_3h.set_index("record.id")["record.continuity_chunk_id"].astype("string").to_dict(),
        "v2_temporal_3h": v2_evidence_3h.set_index("record.id")["record.continuity_chunk_id"].astype("string").to_dict(),
        "v2_same_y_8h": v2_evidence_8h.set_index("record.id")["record.continuity_chunk_id"].astype("string").to_dict(),
        "v2_temporal_8h": v2_evidence_8h.set_index("record.id")["record.continuity_chunk_id"].astype("string").to_dict(),
    }

    base_rows: list[dict[str, object]] = []
    view_rows: list[dict[str, object]] = []
    fold_manifest_rows: list[dict[str, object]] = []
    unsupported_rows: list[dict[str, object]] = []
    matched_rows: dict[str, list[dict[str, object]]] = {
        "matched_v0_v2_3h.csv": [],
        "matched_v1_v2_3h.csv": [],
        "matched_v0_v2_8h.csv": [],
        "matched_v1_v2_8h.csv": [],
    }

    for spec in fold_specs:
        base_rows.extend(build_p1_base_assignments(p1_records, spec))
        view_rows.extend(build_fold_point_assignments(point_labels, spec, record_time))

        for task_id, purge_minutes in (
            ("v2_same_y_3h", 180),
            ("v2_temporal_3h", 180),
            ("v2_same_y_8h", 480),
            ("v2_temporal_8h", 480),
        ):
            view_rows.extend(
                build_fold_v2_assignments(
                    label_frame=label_frames[task_id],
                    task_id=task_id,
                    spec=spec,
                    record_time=record_time,
                    group_lookup=v2_group_lookup[task_id],
                    purge_minutes=purge_minutes,
                )
            )
        fold_manifest_rows.extend(
            build_fold_manifest_rows(
                spec=spec,
                p1_records=p1_records,
                expected_interval_sec=expected_interval_sec,
                label_frames=label_frames,
                view_rows=view_rows,
                boundary_rows=[],
            )
        )
        unsupported_rows.extend(
            build_unsupported_rows_for_fold(
                spec=spec,
                label_frames=label_frames,
                view_rows=view_rows,
            )
        )
        append_matched_rows_for_fold(
            spec=spec,
            matched_rows=matched_rows,
            view_rows=view_rows,
            label_frames=label_frames,
        )

    base_rows.extend(build_p2_base_assignments(p2_records))
    view_rows.extend(
        build_p2_holdout_view_assignments(
            point_labels=point_labels,
            same_y_labels=same_y_labels,
            temporal_3h_labels=temporal_3h_labels,
            temporal_8h_labels=temporal_8h_labels,
        )
    )

    return ProtocolAssignmentArtifacts(
        fold_manifest=pd.DataFrame(fold_manifest_rows).convert_dtypes(),
        unsupported_class_audit=pd.DataFrame(unsupported_rows).convert_dtypes(),
        base_split_assignments=pd.DataFrame(base_rows).convert_dtypes(),
        view_split_assignments=pd.DataFrame(view_rows).convert_dtypes(),
        matched_cohorts={name: pd.DataFrame(rows).convert_dtypes() for name, rows in matched_rows.items()},
    )


__all__ = [
    "ProtocolAssignmentArtifacts",
    "build_protocol_assignment_artifacts",
]
