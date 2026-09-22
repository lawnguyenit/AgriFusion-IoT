"""Orchestration for the post-hoc online run-depth focal analysis."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from Backend.Benchmark.shared.artifacts import create_run_directory, write_json, write_text
from Backend.Benchmark.weak_labels.analysis.temporal_target_views import Y_ONLINE
from Backend.Benchmark.weak_labels.infrastructure.hashing import file_sha256

from .online_run_depth_stratification_data import (
    DEFAULT_FEATURE_VIEW_IDS,
    DEFAULT_PARTITIONS,
    LOW_LABEL,
    build_prediction_summary,
    build_population_summary,
    build_q_positive_population,
    join_online_predictions,
    select_predictions,
)
from .online_run_depth_stratification_reporting import build_readme, build_report, write_chart


@dataclass(frozen=True)
class OnlineRunDepthStratificationConfig:
    """Inputs for the non-mutating run-depth analysis."""

    model_suite_run_dir: Path
    target_views_artifact_dir: Path
    output_root: Path | None = None
    profile_name: str = "temporal_event_online_3h"
    target_view_id: str = Y_ONLINE
    feature_view_ids: tuple[str, ...] = DEFAULT_FEATURE_VIEW_IDS
    partitions: tuple[str, ...] = DEFAULT_PARTITIONS


@dataclass(frozen=True)
class OnlineRunDepthStratificationResult:
    run_id: str
    output_dir: Path
    q_positive_row_count: int
    prediction_row_count: int
    summary_row_count: int


def build_online_run_depth_stratification(
    config: OnlineRunDepthStratificationConfig,
) -> OnlineRunDepthStratificationResult:
    """Persist a traceable focal report from existing online predictions."""

    model_run_dir = config.model_suite_run_dir.resolve()
    target_dir = config.target_views_artifact_dir.resolve()
    if not model_run_dir.is_dir():
        raise FileNotFoundError(f"Model run directory does not exist: {model_run_dir}")
    if not target_dir.is_dir():
        raise FileNotFoundError(f"Target-view artifact directory does not exist: {target_dir}")
    if not config.feature_view_ids or not config.partitions:
        raise ValueError("At least one feature view and partition are required.")

    model_manifest_path = model_run_dir / "run_manifest.json"
    target_manifest_path = target_dir / "run_metadata" / "run_manifest.json"
    target_path = target_dir / "target_views_assignments.parquet"
    if not model_manifest_path.exists():
        raise FileNotFoundError(f"Model run manifest is missing: {model_manifest_path}")
    if not target_manifest_path.exists():
        raise FileNotFoundError(f"Target-view manifest is missing: {target_manifest_path}")
    if not target_path.exists():
        raise FileNotFoundError(f"Target-view assignments are missing: {target_path}")

    model_manifest = json.loads(model_manifest_path.read_text(encoding="utf-8"))
    target_manifest = json.loads(target_manifest_path.read_text(encoding="utf-8"))
    prediction_path = _resolve_prediction_path(model_run_dir, config.profile_name)
    predictions = pd.read_csv(prediction_path).convert_dtypes()
    targets = pd.read_parquet(target_path).convert_dtypes()

    q_population = build_q_positive_population(targets, target_view_id=config.target_view_id)
    selected_predictions = select_predictions(
        predictions,
        target_view_id=config.target_view_id,
        feature_view_ids=config.feature_view_ids,
        partitions=config.partitions,
    )
    joined = join_online_predictions(selected_predictions, q_population)
    population_summary = build_population_summary(q_population)
    prediction_summary = build_prediction_summary(joined)

    run_id, output_dir = create_run_directory(
        (config.output_root or model_run_dir.parent).resolve(),
        prefix="online_run_depth_focal",
    )
    population_path = output_dir / "q_positive_run_depth_population.parquet"
    joined_path = output_dir / "online_run_depth_prediction_rows.parquet"
    population_summary_path = output_dir / "q_positive_run_depth_population_summary.csv"
    prediction_summary_path = output_dir / "online_run_depth_prediction_summary.csv"
    chart_path = output_dir / "online_low_prediction_rate.png"
    q_population.to_parquet(population_path, index=False)
    joined.to_parquet(joined_path, index=False)
    population_summary.to_csv(population_summary_path, index=False)
    prediction_summary.to_csv(prediction_summary_path, index=False)
    write_chart(prediction_summary, chart_path)

    manifest = {
        "artifact_type": "DERIVED_ONLINE_RUN_DEPTH_FOCAL_ANALYSIS",
        "artifact_status": "DERIVED_ANALYSIS_ONLY",
        "authority_status": "CANDIDATE_REFERENCE_ONLY",
        "run_id": run_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_model_run_id": str(model_manifest.get("run_id", model_run_dir.name)),
        "source_model_run_dir": str(model_run_dir),
        "source_prediction_path": str(prediction_path),
        "source_target_views_artifact_id": str(target_manifest.get("run_id", target_dir.name)),
        "source_target_views_artifact_dir": str(target_dir),
        "source_target_assignments_path": str(target_path),
        "profile_name": config.profile_name,
        "target_view_id": config.target_view_id,
        "feature_view_ids": list(config.feature_view_ids),
        "partitions": list(config.partitions),
        "q_positive_definition": "point_label == low_relative_moisture_point (M_t <= Q)",
        "depth_definition": {
            "d=1": "support_depth_at_anchor == 1",
            "d=2": "support_depth_at_anchor == 2",
            "d>=3": "support_depth_at_anchor >= 3",
        },
        "run_outcome_definition": {
            "successful": "run_complete and L_r >= K",
            "failed": "run_complete and L_r < K",
            "censored_or_unknown": "run incomplete or eventual L_r/K unavailable",
        },
        "primary_quantity": "mean(1[predicted_label == LOW]) within each Q-positive depth/outcome stratum",
        "secondary_quantity": "mean(predicted probability for LOW) within each stratum",
        "future_values_used_for": "successful/failed run stratification and reporting only",
        "future_values_forbidden_in_model_inputs": True,
        "model_training_executed": False,
        "model_weights_loaded": False,
        "new_model_inference_executed": False,
        "posthoc_prediction_analysis_executed": True,
        "native_label_mutated": False,
        "target_ontology_changed": False,
        "source_files": {
            "model_manifest": {"path": str(model_manifest_path), "sha256": file_sha256(model_manifest_path)},
            "predictions": {"path": str(prediction_path), "sha256": file_sha256(prediction_path)},
            "target_manifest": {"path": str(target_manifest_path), "sha256": file_sha256(target_manifest_path)},
            "target_assignments": {"path": str(target_path), "sha256": file_sha256(target_path)},
        },
        "output_files": {
            "population_rows": str(population_path),
            "prediction_rows": str(joined_path),
            "population_summary": str(population_summary_path),
            "prediction_summary": str(prediction_summary_path),
            "chart": str(chart_path),
        },
        "row_counts": {
            "q_positive_population": int(len(q_population)),
            "prediction_rows": int(len(joined)),
            "prediction_unique_samples": int(joined["sample_id"].nunique()),
            "population_summary_rows": int(len(population_summary)),
            "prediction_summary_rows": int(len(prediction_summary)),
        },
        "population_summary": _json_records(population_summary),
        "prediction_summary": _json_records(prediction_summary),
    }
    write_json(output_dir / "run_metadata.json", manifest)
    write_text(output_dir / "README.md", build_readme(manifest))
    write_text(
        output_dir / "online_run_depth_focal_report.md",
        build_report(manifest, population_summary, prediction_summary),
    )
    return OnlineRunDepthStratificationResult(
        run_id=run_id,
        output_dir=output_dir,
        q_positive_row_count=len(q_population),
        prediction_row_count=len(joined),
        summary_row_count=len(prediction_summary),
    )


def _resolve_prediction_path(model_run_dir: Path, profile_name: str) -> Path:
    candidates = [model_run_dir / "profiles" / profile_name / "per_sample_predictions.csv"]
    candidates.extend(model_run_dir.rglob("per_sample_predictions.csv"))
    unique = list(dict.fromkeys(path.resolve() for path in candidates if path.exists()))
    if len(unique) != 1:
        raise FileNotFoundError(f"Expected one per_sample_predictions.csv, found: {unique}")
    return unique[0]


def _json_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    return json.loads(frame.to_json(orient="records"))


__all__ = [
    "DEFAULT_FEATURE_VIEW_IDS",
    "DEFAULT_PARTITIONS",
    "LOW_LABEL",
    "OnlineRunDepthStratificationConfig",
    "OnlineRunDepthStratificationResult",
    "build_online_run_depth_stratification",
    "build_prediction_summary",
    "build_population_summary",
    "build_q_positive_population",
    "join_online_predictions",
]
