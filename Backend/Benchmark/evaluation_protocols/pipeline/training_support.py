from __future__ import annotations

import json

import pandas as pd

from Backend.Benchmark.model_suite.families.xgboost_adapter import XGBOOST_IMPORT_ERROR, xgb
from Backend.Benchmark.model_suite.pipeline.native_runner import run_protocol_model_job


def run_xgboost_training_job(
    *,
    stage_id: str,
    run_scope: str,
    comparison_id: str | None,
    comparison_side: str | None,
    feature_view_id: str,
    fold_id: str,
    registry_row: pd.Series,
    task_rows: pd.DataFrame,
    feature_cache: dict[str, pd.DataFrame],
    output_dir,
    random_seed: int,
    thread_count: int,
    n_estimators: int,
    max_depth: int,
    learning_rate: float,
    use_balanced_sample_weight: bool,
    evaluation_partitions: tuple[str, ...] = ("validation", "test"),
) -> dict[str, object]:
    result = run_protocol_model_job(
        model_key="xgboost",
        stage_id=stage_id,
        run_scope=run_scope,
        comparison_id=comparison_id,
        comparison_side=comparison_side,
        feature_view_id=feature_view_id,
        fold_id=fold_id,
        registry_row=registry_row,
        task_rows=task_rows,
        feature_cache=feature_cache,
        output_dir=output_dir,
        random_seed=random_seed,
        thread_count=thread_count,
        hyperparameter_overrides={
            "n_estimators": n_estimators,
            "max_depth": max_depth,
            "learning_rate": learning_rate,
        },
        use_balanced_sample_weight=use_balanced_sample_weight,
        evaluation_partitions=evaluation_partitions,
    )
    summary = dict(result["summary"])
    if str(summary.get("status")) == "model_unavailable":
        summary["status"] = "xgboost_unavailable"
    result["summary"] = summary
    for row in result.get("validation_rows", []):
        row.pop("model_key", None)
    for row in result.get("prediction_rows", []):
        row.pop("model_key", None)
    return result
