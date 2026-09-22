from __future__ import annotations

import pandas as pd

from Backend.Benchmark.evaluation_protocols.pipeline.smoke_support import build_stage_run_frames
from Backend.Benchmark.weak_labels.analysis.temporal_target_views import (
    EVENT_UNDETERMINED,
    LOW_LABEL,
    UNRES_LABEL,
    _event_label,
    _event_label_status,
)


def _row(**overrides: object) -> pd.Series:
    values: dict[str, object] = {
        "point_label": "low_relative_moisture_point",
        "online_label_name": UNRES_LABEL,
        "online_label_status": "LABELED",
        "run_complete": True,
        "eventual_run_length": 3,
        "support_depth_at_anchor": 1,
    }
    values.update(overrides)
    return pd.Series(values)


def test_event_target_marks_successful_run_prefix_low() -> None:
    assert _event_label(_row(), required_k=3) == LOW_LABEL
    assert _event_label(_row(eventual_run_length=2), required_k=3) == UNRES_LABEL
    assert _event_label(_row(run_complete=False), required_k=3) == EVENT_UNDETERMINED


def test_event_target_preserves_auxiliary_unresolved_and_status() -> None:
    row = _row(point_label="unresolved_environmental_evidence_point", online_label_name=UNRES_LABEL)
    assert _event_label(row, required_k=3) == UNRES_LABEL
    labeled = row.copy()
    labeled["event_label_name"] = UNRES_LABEL
    assert _event_label_status(labeled) == "LABELED"
    censored = _row(run_complete=False)
    censored["event_label_name"] = EVENT_UNDETERMINED
    assert _event_label_status(censored) == "ABSTAIN_EVENT_UNDETERMINED"


def test_target_aware_stage_groups_each_feature_and_target_view() -> None:
    rows = []
    for target_view_id in ("temporal_online_3h", "temporal_event_3h"):
        for feature_view_id in ("v2_temporal_mini_3h", "v2_temporal_full_3h"):
            for sample_index in range(2):
                rows.append(
                    {
                        "target_view_id": target_view_id,
                        "feature_view_id": feature_view_id,
                        "fold_id": "fold_01",
                        "partition": "train",
                        "sample_id": f"sample-{sample_index}",
                        "label_name": LOW_LABEL,
                        "final_trainability": True,
                    }
                )
    task_manifest = pd.DataFrame(rows).convert_dtypes()
    stage_runs, validation = build_stage_run_frames(
        stage_spec={
            "stage_id": "paired",
            "source_kind": "task_and_comparison",
            "feature_views": ["v2_temporal_mini_3h", "v2_temporal_full_3h"],
            "target_views": ["temporal_online_3h", "temporal_event_3h"],
            "fold_ids": ["fold_01"],
            "comparison_ids": [],
        },
        task_training_manifest=task_manifest,
        comparison_training_manifest=pd.DataFrame(),
    )
    assert len(stage_runs) == 4
    assert {(row["target_view_id"], row["feature_view_id"]) for row in stage_runs} == {
        (target, feature)
        for target in ("temporal_online_3h", "temporal_event_3h")
        for feature in ("v2_temporal_mini_3h", "v2_temporal_full_3h")
    }
    assert validation[0]["passed"] is True
