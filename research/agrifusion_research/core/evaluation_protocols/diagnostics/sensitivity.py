from __future__ import annotations

from dataclasses import dataclass
import json

import pandas as pd



@dataclass(frozen=True)
class ThresholdSensitivityArtifacts:
    summary: pd.DataFrame
    distributions: pd.DataFrame


def build_threshold_sensitivity_transport(
    *,
    label_frames: dict[str, pd.DataFrame],
    view_assignments: pd.DataFrame,
    q_values: dict[str, float],
) -> ThresholdSensitivityArtifacts:
    """Summarize already-materialized native labels.

    Evaluation is not allowed to refit thresholds or rerun label builders.
    The variants are therefore provenance-only projections of the native
    release, not newly generated labels.
    """
    summary_rows: list[dict[str, object]] = []
    distribution_rows: list[dict[str, object]] = []
    for threshold_id, threshold_value in q_values.items():
        summary_variant, distributions_variant = _summarize_threshold_variant(
            threshold_id=threshold_id,
            threshold_value=float(threshold_value),
            point_labels=label_frames["v0_point_train"],
            v2_temporal_3h=label_frames["v2_temporal_3h"],
            v2_temporal_8h=label_frames["v2_temporal_8h"],
            view_assignments=view_assignments,
        )
        summary_rows.extend(summary_variant)
        distribution_rows.extend(distributions_variant)
    return ThresholdSensitivityArtifacts(
        summary=pd.DataFrame(summary_rows).convert_dtypes(),
        distributions=pd.DataFrame(distribution_rows).convert_dtypes(),
    )


def _summarize_threshold_variant(
    *,
    threshold_id: str,
    threshold_value: float,
    point_labels: pd.DataFrame,
    v2_temporal_3h: pd.DataFrame,
    v2_temporal_8h: pd.DataFrame,
    view_assignments: pd.DataFrame,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    summary_rows: list[dict[str, object]] = []
    distribution_rows: list[dict[str, object]] = []
    task_frames = {
        "v0_point_train": point_labels,
        "v2_temporal_3h": v2_temporal_3h,
        "v2_temporal_8h": v2_temporal_8h,
    }
    for task_id, frame in task_frames.items():
        task_assignments = view_assignments.loc[view_assignments["view_id"].astype("string") == task_id].copy()
        for (deployment_domain, fold_id, partition), assignment_group in task_assignments.groupby(
            ["deployment_domain", "fold_id", "effective_partition"],
            dropna=False,
            sort=False,
        ):
            sample_ids = assignment_group["sample_id"].astype("string").tolist()
            task_frame = frame.loc[frame["sample_id"].astype("string").isin(sample_ids)].copy()
            label_counts = (
                task_frame["label_name"].astype("string").value_counts(dropna=False).to_dict()
                if not task_frame.empty
                else {}
            )
            eligible_count = int(len(task_frame))
            total_count = int(len(assignment_group))
            excluded_count = int(total_count - eligible_count)
            majority_prevalence = (
                float(max(label_counts.values()) / eligible_count) if label_counts and eligible_count > 0 else pd.NA
            )
            collapse_indicator = bool(pd.notna(majority_prevalence) and float(majority_prevalence) >= 0.90)
            persistent_window_count = int(label_counts.get("persistent_low_relative_moisture_at_anchor", 0))
            summary_rows.append(
                {
                    "threshold_id": threshold_id,
                    "threshold_value": threshold_value,
                    "deployment_domain": deployment_domain,
                    "fold_id": fold_id,
                    "partition": partition,
                    "task_id": task_id,
                    "total_count": total_count,
                    "eligible_count": eligible_count,
                    "excluded_count": excluded_count,
                    "label_counts": json.dumps({str(k): int(v) for k, v in label_counts.items()}, ensure_ascii=False, separators=(",", ":")),
                    "labeled_or_eligible_count": eligible_count,
                    "persistent_window_count": persistent_window_count,
                    "persistent_event_count": 0,
                    "normal_event_count": 0,
                    "majority_prevalence_among_eligible": majority_prevalence,
                    "collapse_indicator": collapse_indicator,
                    "event_duration_distribution": pd.NA,
                }
            )
            for label_name, label_count in sorted(label_counts.items(), key=lambda item: str(item[0])):
                distribution_rows.append(
                    {
                        "threshold_id": threshold_id,
                        "threshold_value": threshold_value,
                        "deployment_domain": deployment_domain,
                        "fold_id": fold_id,
                        "partition": partition,
                        "task_id": task_id,
                        "label_name": str(label_name),
                        "label_count": int(label_count),
                        "label_prevalence_among_eligible": float(label_count / eligible_count) if eligible_count > 0 else pd.NA,
                        "eligible_count": eligible_count,
                        "total_count": total_count,
                        "excluded_count": excluded_count,
                    }
                )
    return summary_rows, distribution_rows
