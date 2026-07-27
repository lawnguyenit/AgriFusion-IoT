from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil

import pandas as pd

from Backend.Benchmark.evaluation_protocols.pipeline.reporting import write_benchmark_readiness_report
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


FULL_RANDOM_SEED = 20260717
FULL_THREAD_COUNT = 1
APPROVED_FEATURE_VIEWS: tuple[str, ...] = PRIMARY_FEATURE_VIEW_IDS
FULL_STAGE_SPECS: tuple[dict[str, object], ...] = (
    {
        "stage_id": "primary_task_matrix",
        "feature_views": APPROVED_FEATURE_VIEWS,
        "fold_ids": PRIMARY_FOLD_IDS,
        "comparison_ids": (),
    },
    {
        "stage_id": "primary_comparison_matrix",
        "feature_views": APPROVED_FEATURE_VIEWS,
        "fold_ids": PRIMARY_FOLD_IDS,
        "comparison_ids": PRIMARY_COMPARISON_IDS,
    },
)


@dataclass(frozen=True)
class FullRunResult:
    output_dir: Path
    summary: pd.DataFrame
    validation: pd.DataFrame
    readiness_report: dict[str, object]


def run_full_training(protocol_run_dir: Path) -> FullRunResult:
    runner_dir = protocol_run_dir / "primary_protocol" / "runner"
    full_dir = runner_dir / "full_train"
    if full_dir.exists():
        shutil.rmtree(full_dir)
    full_dir.mkdir(parents=True, exist_ok=True)
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

    for stage_spec in FULL_STAGE_SPECS:
        stage_id = str(stage_spec["stage_id"])
        stage_dir = full_dir / stage_id
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
                registry_df["feature_view_id"].astype("string") == feature_view_id
            ].copy()
            if len(registry_rows) != 1:
                raise ValueError(f"Expected exactly one registry row for feature_view_id={feature_view_id}.")
            result = run_xgboost_training_job(
                stage_id=stage_id,
                run_scope=str(stage_run["run_scope"]),
                comparison_id=(str(stage_run["comparison_id"]) if stage_run["comparison_id"] is not None else None),
                comparison_side=(str(stage_run["comparison_side"]) if stage_run["comparison_side"] is not None else None),
                feature_view_id=feature_view_id,
                fold_id=fold_id,
                registry_row=registry_rows.iloc[0],
                task_rows=task_rows,
                feature_cache=feature_cache,
                output_dir=stage_dir / (str(stage_run["comparison_id"]) if stage_run["comparison_id"] is not None else "task") / feature_view_id / fold_id,
                random_seed=FULL_RANDOM_SEED,
                thread_count=FULL_THREAD_COUNT,
                n_estimators=250,
                max_depth=5,
                learning_rate=0.05,
                use_balanced_sample_weight=True,
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
    frozen_stage_dir = full_dir / "frozen_target_holdout"
    frozen_stage_dir.mkdir(parents=True, exist_ok=True)
    for stage_run in frozen_runs:
        feature_view_id = str(stage_run["feature_view_id"])
        task_rows = pd.DataFrame(stage_run["task_rows"]).convert_dtypes()
        registry_rows = registry_df.loc[
            registry_df["feature_view_id"].astype("string") == feature_view_id
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
            random_seed=FULL_RANDOM_SEED,
            thread_count=FULL_THREAD_COUNT,
            n_estimators=250,
            max_depth=5,
            learning_rate=0.05,
            use_balanced_sample_weight=True,
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

    summary_df.to_csv(full_dir / "full_training_summary.csv", index=False)
    validation_df.to_csv(full_dir / "full_training_validation.csv", index=False)
    prediction_df.to_csv(full_dir / "per_sample_predictions.csv", index=False)
    pooled_prediction_df.to_csv(full_dir / "pooled_oof_metrics.csv", index=False)

    readiness_report = {
        "full_training_executed": True,
        "completed_stage_ids": completed_stage_ids,
        "approved_feature_views": list(APPROVED_FEATURE_VIEWS),
        "random_seed": FULL_RANDOM_SEED,
        "thread_count": FULL_THREAD_COUNT,
        "model_library_version": getattr(xgb, "__version__", f"IMPORT_ERROR:{type(XGBOOST_IMPORT_ERROR).__name__}" if XGBOOST_IMPORT_ERROR is not None else "UNKNOWN"),
        "preprocessing_library_version": "scikit-learn",
        "ready_for_full_benchmark": bool(
            not summary_df.empty
            and summary_df["status"].astype("string").eq("trained").all()
            and validation_df["passed"].astype(bool).all()
        ),
        "per_sample_predictions_generated": not prediction_df.empty,
        "pooled_oof_metrics_generated": not pooled_prediction_df.empty,
    }
    (full_dir / "full_readiness_report.json").write_text(
        json.dumps(readiness_report, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    benchmark_report_path = write_benchmark_readiness_report(
        protocol_run_dir=protocol_run_dir,
        full_output_dir=full_dir,
        readiness_report=readiness_report,
    )
    _update_protocol_validation_report(
        run_metadata_dir=run_metadata_dir,
        full_output_dir=full_dir,
        readiness_report=readiness_report,
        benchmark_report_path=benchmark_report_path,
    )
    _update_run_manifest(run_metadata_dir=run_metadata_dir, full_output_dir=full_dir, readiness_report=readiness_report)
    _update_artifact_catalog(
        run_metadata_dir=run_metadata_dir,
        full_output_dir=full_dir,
        benchmark_report_path=benchmark_report_path,
    )
    return FullRunResult(
        output_dir=full_dir,
        summary=summary_df,
        validation=validation_df,
        readiness_report=readiness_report,
    )


def _update_protocol_validation_report(
    *,
    run_metadata_dir: Path,
    full_output_dir: Path,
    readiness_report: dict[str, object],
    benchmark_report_path: Path,
) -> None:
    report_path = run_metadata_dir / "protocol_validation_report.json"
    if not report_path.exists():
        return
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    validation_gates = payload.setdefault("validation_gates", {})
    validation_gates["full_runner_executed"] = True
    validation_gates["ready_for_full_benchmark"] = bool(readiness_report["ready_for_full_benchmark"])
    validation_gates["comparison_runner_uses_matched_manifest"] = True
    validation_gates["frozen_target_evaluation_executed"] = True
    validation_gates["per_sample_predictions_generated"] = bool(readiness_report["per_sample_predictions_generated"])
    validation_gates["pooled_oof_metrics_generated"] = bool(readiness_report["pooled_oof_metrics_generated"])
    validation_gates["remaining_blockers"] = [] if bool(readiness_report["ready_for_full_benchmark"]) else list(validation_gates.get("remaining_blockers", []))
    payload["training_deferred"] = not bool(readiness_report["ready_for_full_benchmark"])
    payload["model_outputs_present"] = True
    payload["core_benchmark_ready"] = bool(readiness_report["ready_for_full_benchmark"])
    payload["full_training_output_dir"] = str(full_output_dir)
    payload["full_per_sample_predictions_path"] = str(full_output_dir / "per_sample_predictions.csv")
    payload["full_pooled_oof_metrics_path"] = str(full_output_dir / "pooled_oof_metrics.csv")
    payload["full_readiness_report_path"] = str(full_output_dir / "full_readiness_report.json")
    payload["benchmark_readiness_report_path"] = str(benchmark_report_path)
    report_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def _update_artifact_catalog(
    *,
    run_metadata_dir: Path,
    full_output_dir: Path,
    benchmark_report_path: Path,
) -> None:
    catalog_path = run_metadata_dir / "artifact_catalog.csv"
    if not catalog_path.exists():
        return
    catalog_df = pd.read_csv(catalog_path).convert_dtypes()
    rows = pd.DataFrame(
        [
            {
                "artifact_group": "primary_protocol",
                "path": str(full_output_dir / "full_training_summary.csv"),
                "role": "full_training_summary",
                "usage": "full primary benchmark training summary across task and comparison matrices",
            },
            {
                "artifact_group": "primary_protocol",
                "path": str(full_output_dir / "full_training_validation.csv"),
                "role": "full_training_validation",
                "usage": "full primary benchmark runner validations and hash assertions",
            },
            {
                "artifact_group": "primary_protocol",
                "path": str(full_output_dir / "per_sample_predictions.csv"),
                "role": "full_per_sample_predictions",
                "usage": "held-out per-sample predictions for the full primary benchmark runner",
            },
            {
                "artifact_group": "primary_protocol",
                "path": str(full_output_dir / "pooled_oof_metrics.csv"),
                "role": "full_pooled_oof_metrics",
                "usage": "pooled held-out metrics across folds for the full primary benchmark runner",
            },
            {
                "artifact_group": "primary_protocol",
                "path": str(full_output_dir / "full_readiness_report.json"),
                "role": "full_readiness_report",
                "usage": "readiness summary after full primary benchmark execution",
            },
            {
                "artifact_group": "run_metadata",
                "path": str(benchmark_report_path),
                "role": "benchmark_readiness_report",
                "usage": "single-file benchmark-ready summary with key diagnostics and authoritative outputs",
            },
        ]
    ).convert_dtypes()
    merged = pd.concat([catalog_df, rows], ignore_index=True)
    merged = merged.drop_duplicates(subset=["path"], keep="last")
    merged.to_csv(catalog_path, index=False)


def _update_run_manifest(
    *,
    run_metadata_dir: Path,
    full_output_dir: Path,
    readiness_report: dict[str, object],
) -> None:
    manifest_path = run_metadata_dir / "run_manifest.json"
    if not manifest_path.exists():
        return
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["training_deferred"] = not bool(readiness_report["ready_for_full_benchmark"])
    payload["full_training_executed"] = True
    payload["full_training_output_dir"] = str(full_output_dir)
    payload["full_readiness_report_path"] = str(full_output_dir / "full_readiness_report.json")
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
