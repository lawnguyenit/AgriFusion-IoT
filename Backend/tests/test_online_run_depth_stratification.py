from __future__ import annotations

import json

import pandas as pd

from Backend.Benchmark.model_suite.analysis.online_run_depth_stratification import (
    LOW_LABEL,
    build_prediction_summary,
    build_population_summary,
    build_q_positive_population,
    join_online_predictions,
)


CLASS_NAMES = [
    LOW_LABEL,
    "unresolved_environmental_evidence_at_anchor",
    "reference_context_at_anchor",
]


def _target_row(sample_id: str, depth: int, eventual: int | None, complete: bool | None = True) -> dict[str, object]:
    return {
        "sample_id": sample_id,
        "target_view_id": "temporal_online_3h",
        "point_label": "low_relative_moisture_point",
        "m_relation_to_q": "M_t<=Q",
        "support_depth_at_anchor": depth,
        "eventual_run_length": eventual,
        "run_complete": complete,
        "required_k": 3,
        "run_id": f"run-{sample_id}",
        "sample_time_utc": "2026-05-01T00:00:00Z",
        "online_label_name": "unresolved_environmental_evidence_at_anchor",
        "online_label_status": "LABELED",
    }


def _prediction_row(sample_id: str, label: str, low_probability: float) -> dict[str, object]:
    probabilities = [low_probability, 1.0 - low_probability, 0.0]
    return {
        "target_view_id": "temporal_online_3h",
        "feature_view_id": "v2_temporal_mini_3h",
        "partition": "test",
        "sample_id": sample_id,
        "label_name_pred": label,
        "class_names_json": json.dumps(CLASS_NAMES),
        "prediction_probability_json": json.dumps(probabilities),
    }


def test_run_depth_population_separates_success_failed_and_censored() -> None:
    targets = pd.DataFrame(
        [
            _target_row("s1", 1, 3),
            _target_row("s2", 1, 2),
            _target_row("s3", 2, 3),
            _target_row("s4", 3, 4),
            _target_row("s5", 1, None, False),
        ]
    ).convert_dtypes()

    population = build_q_positive_population(targets)
    assert population["run_outcome"].value_counts().to_dict() == {
        "successful": 3,
        "failed": 1,
        "censored_or_unknown": 1,
    }
    summary = build_population_summary(population)
    success_d1 = summary.loc[
        summary["run_outcome"].eq("successful") & summary["depth_bin"].eq("d=1")
    ].iloc[0]
    failed_d1 = summary.loc[
        summary["run_outcome"].eq("failed") & summary["depth_bin"].eq("d=1")
    ].iloc[0]
    assert int(success_d1["q_positive_rows"]) == 1
    assert int(failed_d1["q_positive_rows"]) == 1


def test_prediction_summary_reports_hard_low_rate_and_mean_probability() -> None:
    targets = pd.DataFrame(
        [_target_row("s1", 1, 3), _target_row("s2", 1, 2), _target_row("s3", 3, 3)]
    ).convert_dtypes()
    population = build_q_positive_population(targets)
    predictions = pd.DataFrame(
        [
            _prediction_row("s1", LOW_LABEL, 0.8),
            _prediction_row("s2", "unresolved_environmental_evidence_at_anchor", 0.2),
            _prediction_row("s3", LOW_LABEL, 0.9),
        ]
    ).convert_dtypes()

    joined = join_online_predictions(predictions, population)
    summary = build_prediction_summary(joined)
    success_d1 = summary.loc[
        summary["run_outcome"].eq("successful") & summary["depth_bin"].eq("d=1")
    ].iloc[0]
    failed_d1 = summary.loc[
        summary["run_outcome"].eq("failed") & summary["depth_bin"].eq("d=1")
    ].iloc[0]
    success_d3 = summary.loc[
        summary["run_outcome"].eq("successful") & summary["depth_bin"].eq("d>=3")
    ].iloc[0]
    assert float(success_d1["pred_low_rate"]) == 1.0
    assert float(success_d1["mean_predicted_low_probability"]) == 0.8
    assert float(failed_d1["pred_low_rate"]) == 0.0
    assert float(success_d3["pred_low_rate"]) == 1.0


if __name__ == "__main__":
    import unittest

    unittest.main()
