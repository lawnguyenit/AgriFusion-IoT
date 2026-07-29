from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from Backend.Benchmark.model_suite.contracts.run_spec import ModelSuiteRunSpec
from Backend.Benchmark.model_suite.data import build_stage_run_frames, load_protocol_runner, load_stage_specs_for_profile
from Backend.Benchmark.model_suite.evaluation.comparisons import build_model_comparison_table
from Backend.Benchmark.model_suite.evaluation.pooling import build_pooled_prediction_summary
from Backend.Benchmark.model_suite.persistence.artifact_catalog import write_artifact_catalog
from Backend.Benchmark.model_suite.persistence.run_signature import build_run_manifest
from Backend.Benchmark.model_suite.pipeline.guides import write_run_guides
from Backend.Benchmark.model_suite.pipeline.native_runner import run_protocol_model_job
from Backend.Benchmark.model_suite.pipeline.tuning import resolve_smoke_hyperparameters
from Backend.Benchmark.model_suite.registries import assert_models_available
from Backend.Benchmark.model_suite.reporting.markdown import build_run_report_markdown
from Backend.Benchmark.model_suite.reporting.progress import SmokeJobProgress, SmokeSuiteProgressReporter
from Backend.Benchmark.shared.artifacts import create_run_directory, write_json, write_text

from Backend.Benchmark.model_suite.config import ARTIFACT_POLICY_PATH, MODEL_REGISTRY_PATH, TRAINING_PROFILES_PATH


@dataclass(frozen=True)
class SmokeSuiteResult:
    run_spec: ModelSuiteRunSpec
    summary: pd.DataFrame
    validation: pd.DataFrame
    predictions: pd.DataFrame
    pooled_metrics: pd.DataFrame


def run_smoke_suite(
    *,
    protocol_run_dir: Path,
    profile_name: str = "smoke_phase1_protocol",
    model_keys: tuple[str, ...] | None = None,
    show_progress: bool = True,
) -> SmokeSuiteResult:
    model_registry_payload = json.loads(MODEL_REGISTRY_PATH.read_text(encoding="utf-8"))
    resolved_model_keys = (
        tuple(str(model_key) for model_key in model_keys)
        if model_keys is not None
        else tuple(str(model_key) for model_key in model_registry_payload["smoke_model_keys"])
    )
    assert_models_available(resolved_model_keys)
    loaded = load_protocol_runner(protocol_run_dir.resolve())
    run_id, output_dir = create_run_directory(_default_artifact_root(), prefix="model_suite")
    stage_specs = load_stage_specs_for_profile(TRAINING_PROFILES_PATH, profile_name)
    artifact_policy = json.loads(ARTIFACT_POLICY_PATH.read_text(encoding="utf-8"))
    run_spec = ModelSuiteRunSpec(
        run_id=run_id,
        output_dir=output_dir,
        profile_name=profile_name,
        protocol_source=loaded.source_ref,
        model_keys=resolved_model_keys,
        stage_specs=stage_specs,
        metadata={
            "artifact_policy": artifact_policy,
            "model_registry_config_path": str(MODEL_REGISTRY_PATH),
            "training_profile_config_path": str(TRAINING_PROFILES_PATH),
        },
    )
    summary_rows: list[dict[str, object]] = []
    validation_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    feature_cache: dict[str, pd.DataFrame] = {}
    artifact_catalog_rows: list[dict[str, object]] = []
    stage_run_batches: list[tuple[dict[str, object], str, list[dict[str, object]]]] = []
    for stage_spec in stage_specs:
        stage_id = str(stage_spec["stage_id"])
        stage_runs, stage_validation_rows = build_stage_run_frames(
            stage_spec=stage_spec,
            task_training_manifest=loaded.task_manifest,
            comparison_training_manifest=loaded.comparison_manifest,
            frozen_target_manifest=loaded.frozen_target_manifest,
        )
        validation_rows.extend(stage_validation_rows)
        stage_run_batches.append((stage_spec, stage_id, stage_runs))
    total_jobs = sum(len(stage_runs) * len(resolved_model_keys) for _, _, stage_runs in stage_run_batches)
    completed_jobs = 0
    with SmokeSuiteProgressReporter(enabled=show_progress) as progress:
        progress.start_run(
            run_id=run_id,
            output_dir=output_dir,
            total_jobs=total_jobs,
            profile_name=profile_name,
        )
        job_root = _job_output_root(output_dir, profile_name)
        for stage_spec, stage_id, stage_runs in stage_run_batches:
            progress.enter_stage(stage_id=stage_id, stage_job_count=len(stage_runs) * len(resolved_model_keys))
            for stage_run in stage_runs:
                feature_view_id = str(stage_run["feature_view_id"])
                fold_id = str(stage_run["fold_id"])
                task_rows = pd.DataFrame(stage_run["task_rows"]).convert_dtypes()
                registry_rows = loaded.task_registry.loc[
                    loaded.task_registry["feature_view_id"].astype("string") == feature_view_id
                ].copy()
                if len(registry_rows) != 1:
                    raise ValueError(f"Expected exactly one task registry row for feature_view_id={feature_view_id}.")
                registry_row = registry_rows.iloc[0]
                evaluation_partitions = tuple(
                    str(value) for value in stage_spec.get("evaluation_partitions", ["validation", "test"])
                )
                for model_key in resolved_model_keys:
                    job = SmokeJobProgress(
                        index=completed_jobs + 1,
                        total=total_jobs,
                        stage_id=stage_id,
                        model_key=model_key,
                        feature_view_id=feature_view_id,
                        fold_id=fold_id,
                        run_scope=str(stage_run["run_scope"]),
                    )
                    progress.start_job(job)
                    model_output_dir = job_root / stage_id / model_key / (
                        str(stage_run["comparison_id"]) if stage_run["comparison_id"] is not None else "task"
                    ) / feature_view_id / fold_id
                    try:
                        result = run_protocol_model_job(
                            model_key=model_key,
                            stage_id=stage_id,
                            run_scope=str(stage_run["run_scope"]),
                            comparison_id=(str(stage_run["comparison_id"]) if stage_run["comparison_id"] is not None else None),
                            comparison_side=(str(stage_run["comparison_side"]) if stage_run["comparison_side"] is not None else None),
                            feature_view_id=feature_view_id,
                            fold_id=fold_id,
                            registry_row=registry_row,
                            task_rows=task_rows.copy(),
                            feature_cache=feature_cache,
                            output_dir=model_output_dir,
                            random_seed=int(artifact_policy["random_seed"]),
                            thread_count=int(artifact_policy["thread_count"]),
                            hyperparameter_overrides=resolve_smoke_hyperparameters(model_key),
                            use_balanced_sample_weight=None,
                            evaluation_partitions=evaluation_partitions,
                        )
                    except Exception as exc:
                        completed_jobs += 1
                        progress.fail_job(status="crashed", note=f"{type(exc).__name__}: {exc}")
                        raise
                    completed_jobs += 1
                    progress.complete_job(
                        status=str(result["summary"].get("status", "unknown")),
                        note=(None if result["summary"].get("note") is None else str(result["summary"]["note"])),
                    )
                    summary_rows.append(result["summary"])
                    validation_rows.extend(result["validation_rows"])
                    prediction_rows.extend(result["prediction_rows"])
                    artifact_catalog_rows.extend(result.get("artifact_rows", []))
        summary_df = pd.DataFrame(summary_rows).convert_dtypes()
        validation_df = pd.DataFrame(validation_rows).convert_dtypes()
        predictions_df = pd.DataFrame(prediction_rows).convert_dtypes()
        pooled_df = build_pooled_prediction_summary(predictions_df)
        comparison_df = build_model_comparison_table(summary_df)
        profile_root = _profile_output_root(output_dir, profile_name)
        profile_root.mkdir(parents=True, exist_ok=True)
        summary_filename = "smoke_model_summary.csv" if profile_name.startswith("smoke_") else "training_summary.csv"
        validation_filename = "smoke_model_validation.csv" if profile_name.startswith("smoke_") else "training_validation.csv"
        report_filename = "smoke_report.md" if profile_name.startswith("smoke_") else "run_report.md"
        summary_df.to_csv(profile_root / summary_filename, index=False)
        validation_df.to_csv(profile_root / validation_filename, index=False)
        predictions_df.to_csv(profile_root / "per_sample_predictions.csv", index=False)
        pooled_df.to_csv(profile_root / "pooled_metrics.csv", index=False)
        comparison_df.to_csv(profile_root / "model_comparison_table.csv", index=False)
        write_text(
            profile_root / report_filename,
            build_run_report_markdown(
                run_id=run_id,
                profile_name=profile_name,
                summary_df=summary_df,
                pooled_df=pooled_df,
            ),
        )
        write_json(output_dir / "run_manifest.json", build_run_manifest(run_spec))
        guide_rows = write_run_guides(output_dir=output_dir, profile_name=profile_name)
        write_artifact_catalog(
            output_dir / "artifact_catalog.csv",
            guide_rows
            + artifact_catalog_rows
            + [
                {
                    "artifact_group": "run_metadata",
                    "path": str(output_dir / "run_manifest.json"),
                    "role": "run_manifest",
                    "usage": "top-level model_suite smoke run signature",
                },
                {
                    "artifact_group": "profile_run",
                    "path": str(profile_root / summary_filename),
                    "role": "training_summary",
                    "usage": f"one row per model/stage/feature/fold job for profile {profile_name}",
                },
                {
                    "artifact_group": "profile_run",
                    "path": str(profile_root / validation_filename),
                    "role": "training_validation",
                    "usage": f"validation gates for each job in profile {profile_name}",
                },
                {
                    "artifact_group": "profile_run",
                    "path": str(profile_root / "per_sample_predictions.csv"),
                    "role": "per_sample_predictions",
                    "usage": f"held-out predictions for profile {profile_name}",
                },
                {
                    "artifact_group": "profile_run",
                    "path": str(profile_root / "pooled_metrics.csv"),
                    "role": "pooled_metrics",
                    "usage": f"pooled held-out metrics by model and run scope for profile {profile_name}",
                },
                {
                    "artifact_group": "profile_run",
                    "path": str(profile_root / "model_comparison_table.csv"),
                    "role": "model_comparison_table",
                    "usage": f"compact comparison view across trained jobs for profile {profile_name}",
                },
                {
                    "artifact_group": "profile_run",
                    "path": str(profile_root / report_filename),
                    "role": "run_report",
                    "usage": f"human-readable summary with status counts and pooled metrics for profile {profile_name}",
                },
            ],
        )
        trained_jobs = int(summary_df["status"].astype("string").eq("trained").sum()) if not summary_df.empty else 0
        progress.finish(trained_jobs=trained_jobs, total_jobs=total_jobs, output_dir=output_dir)
    return SmokeSuiteResult(
        run_spec=run_spec,
        summary=summary_df,
        validation=validation_df,
        predictions=predictions_df,
        pooled_metrics=pooled_df,
    )


def _default_artifact_root() -> Path:
    payload = json.loads(ARTIFACT_POLICY_PATH.read_text(encoding="utf-8"))
    return Path(str(payload["artifact_root"])).resolve()


def _profile_output_root(output_dir: Path, profile_name: str) -> Path:
    if profile_name.startswith("smoke_"):
        return output_dir / "smoke_protocol"
    return output_dir / "profiles" / profile_name


def _job_output_root(output_dir: Path, profile_name: str) -> Path:
    if profile_name.startswith("smoke_"):
        return output_dir / "smoke_protocol"
    return output_dir / "profiles" / profile_name / "jobs"
