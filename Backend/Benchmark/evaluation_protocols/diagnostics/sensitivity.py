from __future__ import annotations

from dataclasses import dataclass
import json

import pandas as pd

from Backend.Benchmark.evaluation_protocols.lineage import (
    attach_block_domains,
    attach_event_domains,
    build_protocol_assignment_artifacts,
)
from Backend.Benchmark.shared.weak_rules import LowRelativeMoistureThresholds
from Backend.Benchmark.weak_labels.point import ThresholdContext, build_point_label_artifacts
from Backend.Benchmark.weak_labels.v2 import build_v2_label_artifacts
from Backend.Benchmark.weak_labels.v6 import build_v6_label_artifacts


@dataclass(frozen=True)
class ThresholdSensitivityArtifacts:
    summary: pd.DataFrame
    distributions: pd.DataFrame


def build_threshold_sensitivity_transport(
    *,
    working: pd.DataFrame,
    base_threshold_context: ThresholdContext,
    fold_specs,
    segment_manifest: dict[str, object],
    domain_by_segment: dict[str, str],
    expected_interval_sec: int,
    q_values: dict[str, float],
) -> ThresholdSensitivityArtifacts:
    summary_rows: list[dict[str, object]] = []
    distribution_rows: list[dict[str, object]] = []
    record_domain_lookup = working.set_index("record.id")["deployment_domain_name"].astype("string").to_dict()
    for threshold_id, threshold_value in q_values.items():
        threshold_context = ThresholdContext(
            threshold_mode=base_threshold_context.threshold_mode,
            low_moisture_global=LowRelativeMoistureThresholds(
                q10=float(threshold_value),
                q15=base_threshold_context.low_moisture_global.q15,
                fit_value_count=base_threshold_context.low_moisture_global.fit_value_count,
                scope_key=threshold_id,
            ),
            low_moisture_by_segment={},
            ec_shift_abs_delta_q95=base_threshold_context.ec_shift_abs_delta_q95,
            threshold_records=base_threshold_context.threshold_records,
            sensitivity_df=base_threshold_context.sensitivity_df,
        )
        point_artifacts = build_point_label_artifacts(working, threshold_context=threshold_context)
        v2_artifacts = build_v2_label_artifacts(point_artifacts.enriched_df, segment_manifest=segment_manifest, boundary_timestamps={})
        v6_artifacts = build_v6_label_artifacts(point_artifacts.enriched_df, segment_manifest=segment_manifest)

        point_labels = point_artifacts.point_labels_train.loc[
            point_artifacts.point_labels_train["task_id"] == "v0_point_train"
        ].copy()
        point_labels["deployment_domain_name"] = point_labels["sample_id"].astype("string").map(record_domain_lookup)
        v2_temporal_3h = v2_artifacts.temporal_labels_3h.copy()
        v2_temporal_3h["deployment_domain_name"] = v2_temporal_3h["sample_id"].astype("string").map(record_domain_lookup)
        v2_temporal_8h = v2_artifacts.temporal_labels_8h.copy()
        v2_temporal_8h["deployment_domain_name"] = v2_temporal_8h["sample_id"].astype("string").map(record_domain_lookup)
        v2_same_y = v2_artifacts.same_y_labels.copy()
        v2_same_y["deployment_domain_name"] = v2_same_y["sample_id"].astype("string").map(record_domain_lookup)
        v6_events = attach_event_domains(v6_artifacts.event_labels, domain_by_segment)
        v6_blocks = attach_block_domains(v6_artifacts.block_labels, v6_artifacts.block_composition, domain_by_segment)
        assignment_artifacts = build_protocol_assignment_artifacts(
            fold_specs=fold_specs,
            point_labels=point_labels,
            v2_same_y=v2_same_y,
            v2_temporal_3h=v2_temporal_3h,
            v2_temporal_8h=v2_temporal_8h,
            v2_evidence_3h=v2_artifacts.temporal_evidence_3h,
            v2_evidence_8h=v2_artifacts.temporal_evidence_8h,
            v6_events=v6_events,
            v6_blocks=v6_blocks,
            working=working,
            expected_interval_sec=expected_interval_sec,
        )
        summary_variant, distributions_variant = _summarize_threshold_variant(
            threshold_id=threshold_id,
            threshold_value=float(threshold_value),
            point_labels=point_labels,
            v2_temporal_3h=v2_temporal_3h,
            v2_temporal_8h=v2_temporal_8h,
            v6_events=v6_events,
            view_assignments=assignment_artifacts.view_split_assignments,
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
    v6_events: pd.DataFrame,
    view_assignments: pd.DataFrame,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    summary_rows: list[dict[str, object]] = []
    distribution_rows: list[dict[str, object]] = []
    task_frames = {
        "v0_point_train": point_labels,
        "v2_temporal_3h": v2_temporal_3h,
        "v2_temporal_8h": v2_temporal_8h,
        "v6_event": v6_events,
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
            duration_summary = pd.NA
            if task_id == "v6_event" and not task_frame.empty:
                event_hours = (
                    pd.to_datetime(task_frame["event_end_local"], errors="coerce")
                    - pd.to_datetime(task_frame["event_start_local"], errors="coerce")
                ).dt.total_seconds() / 3600.0
                duration_summary = json.dumps(
                    {
                        "median_hours": float(event_hours.median()),
                        "q25_hours": float(event_hours.quantile(0.25)),
                        "q75_hours": float(event_hours.quantile(0.75)),
                        "max_hours": float(event_hours.max()),
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            persistent_window_count = int(label_counts.get("persistent_low_relative_moisture_window", 0))
            persistent_event_count = int(label_counts.get("persistent_low_relative_moisture_event", 0))
            normal_event_count = int(label_counts.get("normal", 0))
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
                    "persistent_event_count": persistent_event_count,
                    "normal_event_count": normal_event_count,
                    "majority_prevalence_among_eligible": majority_prevalence,
                    "collapse_indicator": collapse_indicator,
                    "event_duration_distribution": duration_summary,
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
