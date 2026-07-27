from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil

import pandas as pd
from Backend.Benchmark.evaluation_protocols.pipeline.smoke_support import (
    build_frozen_target_run_frames,
    build_pooled_prediction_summary,
    build_stage_run_frames,
)
from Backend.Benchmark.evaluation_protocols.pipeline.training_support import (
    XGBOOST_IMPORT_ERROR,
    run_xgboost_training_job,
    xgb,
)
from Backend.Benchmark.evaluation_protocols.scope import PRIMARY_COMPARISON_IDS, PRIMARY_FEATURE_VIEW_IDS, PRIMARY_FOLD_IDS


SMOKE_RANDOM_SEED = 20260716
SMOKE_THREAD_COUNT = 1
APPROVED_FEATURE_VIEWS: tuple[str, ...] = PRIMARY_FEATURE_VIEW_IDS
STAGE_SPECS: tuple[dict[str, object], ...] = (
    {
        "stage_id": "level_1_v0_fold_01",
        "feature_views": ("v0_point",),
        "fold_ids": ("fold_01",),
        "comparison_ids": (),
    },
    {
        "stage_id": "level_2_v0_vs_v2_mini_3h_fold_01",
        "feature_views": ("v0_point", "v2_same_y_mini_3h"),
        "fold_ids": ("fold_01",),
        "comparison_ids": ("v0_vs_v2_mini_3h",),
    },
    {
        "stage_id": "level_3_primary_matrix",
        "feature_views": APPROVED_FEATURE_VIEWS,
        "fold_ids": PRIMARY_FOLD_IDS,
        "comparison_ids": PRIMARY_COMPARISON_IDS,
    },
)


@dataclass(frozen=True)
class SmokeRunResult:
    output_dir: Path
    summary: pd.DataFrame
    validation: pd.DataFrame
    readiness_report: dict[str, object]


def run_smoke_training(protocol_run_dir: Path) -> SmokeRunResult:
    runner_dir = protocol_run_dir / "primary_protocol" / "runner"
    smoke_dir = runner_dir / "smoke_train"
    if smoke_dir.exists():
        shutil.rmtree(smoke_dir)
    smoke_dir.mkdir(parents=True, exist_ok=True)
    run_metadata_dir = protocol_run_dir / "run_metadata"

    registry_df = pd.read_csv(runner_dir / "task_view_registry.csv").convert_dtypes()
    task_training_manifest = pd.read_parquet(runner_dir / "task_training_manifest.parquet").convert_dtypes()
    comparison_training_manifest = pd.read_parquet(runner_dir / "comparison_training_manifest.parquet").convert_dtypes()
    frozen_target_manifest = pd.read_parquet(runner_dir / "frozen_target_manifest.parquet").convert_dtypes()

    feature_cache: dict[str, pd.DataFrame] = {}
    summary_rows: list[dict[str, object]] = []
    validation_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    completed_stage_ids: list[str] = []

    for stage_spec in STAGE_SPECS:
        stage_id = str(stage_spec["stage_id"])
        stage_dir = smoke_dir / stage_id
        stage_dir.mkdir(parents=True, exist_ok=True)
        stage_runs, stage_validation_rows = build_stage_run_frames(
            stage_spec=stage_spec,
            task_training_manifest=task_training_manifest,
            comparison_training_manifest=comparison_training_manifest,
        )
        validation_rows.extend(stage_validation_rows)

        for stage_run in stage_runs:
            feature_view_id = str(stage_run["feature_view_id"])
            fold_id = str(stage_run["fold_id"])
            task_rows = pd.DataFrame(stage_run["task_rows"]).convert_dtypes()
            registry_rows = registry_df.loc[
                registry_df["feature_view_id"].astype("string") == str(feature_view_id)
            ].copy()
            if len(registry_rows) != 1:
                raise ValueError(f"Expected exactly one registry row for feature_view_id={feature_view_id}.")
            registry_row = registry_rows.iloc[0]
            result = _run_task_fold_smoke(
                stage_dir=stage_dir,
                stage_id=stage_id,
                run_scope=str(stage_run["run_scope"]),
                comparison_id=(
                    str(stage_run["comparison_id"])
                    if stage_run["comparison_id"] is not None
                    else None
                ),
                comparison_side=(
                    str(stage_run["comparison_side"])
                    if stage_run["comparison_side"] is not None
                    else None
                ),
                feature_view_id=str(feature_view_id),
                fold_id=str(fold_id),
                registry_row=registry_row,
                task_rows=task_rows.copy(),
                feature_cache=feature_cache,
            )
            summary_rows.append(result["summary"])
            validation_rows.extend(result["validation_rows"])
            prediction_rows.extend(result["prediction_rows"])
        completed_stage_ids.append(stage_id)

    frozen_runs, frozen_validation_rows = build_frozen_target_run_frames(
        frozen_target_manifest,
        feature_view_ids=APPROVED_FEATURE_VIEWS,
    )
    validation_rows.extend(frozen_validation_rows)
    frozen_stage_dir = smoke_dir / "frozen_target_holdout"
    frozen_stage_dir.mkdir(parents=True, exist_ok=True)
    for stage_run in frozen_runs:
        feature_view_id = str(stage_run["feature_view_id"])
        task_rows = pd.DataFrame(stage_run["task_rows"]).convert_dtypes()
        registry_rows = registry_df.loc[
            registry_df["feature_view_id"].astype("string") == str(feature_view_id)
        ].copy()
        if len(registry_rows) != 1:
            raise ValueError(f"Expected exactly one registry row for feature_view_id={feature_view_id}.")
        result = run_xgboost_training_job(
            stage_id="frozen_target_holdout",
            run_scope="task",
            comparison_id=None,
            comparison_side=None,
            feature_view_id=feature_view_id,
            fold_id=str(stage_run["fold_id"]),
            registry_row=registry_rows.iloc[0],
            task_rows=task_rows,
            feature_cache=feature_cache,
            output_dir=frozen_stage_dir / "task" / feature_view_id / str(stage_run["fold_id"]),
            random_seed=SMOKE_RANDOM_SEED,
            thread_count=SMOKE_THREAD_COUNT,
            n_estimators=64,
            max_depth=4,
            learning_rate=0.1,
            use_balanced_sample_weight=False,
            evaluation_partitions=("target_test",),
        )
        summary_rows.append(result["summary"])
        validation_rows.extend(result["validation_rows"])
        prediction_rows.extend(result["prediction_rows"])
    completed_stage_ids.append("frozen_target_holdout")

    summary_df = pd.DataFrame(summary_rows).convert_dtypes()
    validation_df = pd.DataFrame(validation_rows).convert_dtypes()
    prediction_df = pd.DataFrame(prediction_rows).convert_dtypes()
    pooled_prediction_df = build_pooled_prediction_summary(prediction_df)
    prediction_df.to_csv(smoke_dir / "per_sample_predictions.csv", index=False)
    pooled_prediction_df.to_csv(smoke_dir / "pooled_oof_metrics.csv", index=False)
    readiness_report = {
        "smoke_test_executed": True,
        "completed_stage_ids": completed_stage_ids,
        "approved_feature_views": list(APPROVED_FEATURE_VIEWS),
        "random_seed": SMOKE_RANDOM_SEED,
        "thread_count": SMOKE_THREAD_COUNT,
        "model_library_version": getattr(xgb, "__version__", f"IMPORT_ERROR:{type(XGBOOST_IMPORT_ERROR).__name__}" if XGBOOST_IMPORT_ERROR is not None else "UNKNOWN"),
        "preprocessing_library_version": "scikit-learn",
        "ready_for_smoke_train": bool(
            not summary_df.empty
            and summary_df["status"].astype("string").eq("trained").any()
            and validation_df["passed"].astype(bool).all()
        ),
        "per_sample_predictions_generated": not prediction_df.empty,
        "pooled_oof_metrics_generated": not pooled_prediction_df.empty,
        "full_benchmark_ready": False,
    }

    summary_df.to_csv(smoke_dir / "smoke_training_summary.csv", index=False)
    validation_df.to_csv(smoke_dir / "smoke_training_validation.csv", index=False)
    readiness_report_path = smoke_dir / "smoke_readiness_report.json"
    readiness_report_path.write_text(
        json.dumps(readiness_report, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    _update_protocol_validation_report(
        run_metadata_dir=run_metadata_dir,
        smoke_output_dir=smoke_dir,
        readiness_report=readiness_report,
    )
    _update_artifact_catalog(run_metadata_dir=run_metadata_dir, smoke_output_dir=smoke_dir)
    return SmokeRunResult(
        output_dir=smoke_dir,
        summary=summary_df,
        validation=validation_df,
        readiness_report=readiness_report,
    )


def _run_task_fold_smoke(
    *,
    stage_dir: Path,
    stage_id: str,
    run_scope: str,
    comparison_id: str | None,
    comparison_side: str | None,
    feature_view_id: str,
    fold_id: str,
    registry_row: pd.Series,
    task_rows: pd.DataFrame,
    feature_cache: dict[str, pd.DataFrame],
) -> dict[str, object]:
    task_dir = stage_dir / (comparison_id if comparison_id is not None else "task") / feature_view_id / fold_id
    return run_xgboost_training_job(
        stage_id=stage_id,
        run_scope=run_scope,
        comparison_id=comparison_id,
        comparison_side=comparison_side,
        feature_view_id=feature_view_id,
        fold_id=fold_id,
        registry_row=registry_row,
        task_rows=task_rows,
        feature_cache=feature_cache,
        output_dir=task_dir,
        random_seed=SMOKE_RANDOM_SEED,
        thread_count=SMOKE_THREAD_COUNT,
        n_estimators=64,
        max_depth=4,
        learning_rate=0.1,
        use_balanced_sample_weight=False,
    )
def _update_protocol_validation_report(
    *,
    run_metadata_dir: Path,
    smoke_output_dir: Path,
    readiness_report: dict[str, object],
) -> None:
    report_path = run_metadata_dir / "protocol_validation_report.json"
    if not report_path.exists():
        return
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    validation_gates = payload.setdefault("validation_gates", {})
    validation_gates["smoke_test_executed"] = True
    validation_gates["ready_for_smoke_test"] = bool(readiness_report["ready_for_smoke_train"])
    validation_gates["comparison_runner_uses_matched_manifest"] = True
    validation_gates["frozen_target_smoke_executed"] = True
    validation_gates["per_sample_predictions_generated"] = bool(readiness_report.get("per_sample_predictions_generated", False))
    validation_gates["pooled_oof_metrics_generated"] = bool(readiness_report.get("pooled_oof_metrics_generated", False))
    payload["model_outputs_present"] = True
    payload["smoke_training_output_dir"] = str(smoke_output_dir)
    payload["smoke_per_sample_predictions_path"] = str(smoke_output_dir / "per_sample_predictions.csv")
    payload["smoke_pooled_oof_metrics_path"] = str(smoke_output_dir / "pooled_oof_metrics.csv")
    report_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def _update_artifact_catalog(
    *,
    run_metadata_dir: Path,
    smoke_output_dir: Path,
) -> None:
    catalog_path = run_metadata_dir / "artifact_catalog.csv"
    if not catalog_path.exists():
        return
    catalog_df = pd.read_csv(catalog_path).convert_dtypes()
    smoke_rows = pd.DataFrame(
        [
            {
                "artifact_group": "primary_protocol",
                "path": str(smoke_output_dir / "smoke_training_summary.csv"),
                "role": "smoke_training_summary",
                "usage": "stage-level smoke training status and metrics for approved tasks",
            },
            {
                "artifact_group": "primary_protocol",
                "path": str(smoke_output_dir / "smoke_training_validation.csv"),
                "role": "smoke_training_validation",
                "usage": "smoke training partition and comparison gates",
            },
            {
                "artifact_group": "primary_protocol",
                "path": str(smoke_output_dir / "smoke_readiness_report.json"),
                "role": "smoke_readiness_report",
                "usage": "post-protocol readiness summary for smoke train",
            },
            {
                "artifact_group": "primary_protocol",
                "path": str(smoke_output_dir / "per_sample_predictions.csv"),
                "role": "smoke_per_sample_predictions",
                "usage": "held-out per-sample predictions for smoke runner audit",
            },
            {
                "artifact_group": "primary_protocol",
                "path": str(smoke_output_dir / "pooled_oof_metrics.csv"),
                "role": "smoke_pooled_oof_metrics",
                "usage": "pooled held-out smoke metrics across folds for each run scope",
            },
        ]
    ).convert_dtypes()
    merged = pd.concat([catalog_df, smoke_rows], ignore_index=True)
    merged = merged.drop_duplicates(subset=["path"], keep="last")
    merged.to_csv(catalog_path, index=False)
