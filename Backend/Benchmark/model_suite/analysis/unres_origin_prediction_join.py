"""Join existing temporal predictions to derived UNRES-origin provenance.

This is a post-hoc slice analysis.  It reuses predictions already emitted by a
model-suite run, does not load weights, run inference, retrain, or mutate any
label artifact.  ``UNRES_K`` and ``UNRES_A`` remain analysis-only provenance
values; the model target stays the original three-class ontology.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

from Backend.Benchmark.shared.artifacts import create_run_directory, write_json, write_text

from .unres_origin_prediction_reporting import build_readme, build_report

UNRES_K = "UNRES_K"
UNRES_A = "UNRES_A"
UNRES_ORIGINS = (UNRES_K, UNRES_A)
DEFAULT_FEATURE_VIEW_IDS = ("v2_temporal_mini_3h", "v2_temporal_full_3h")
DEFAULT_PARTITIONS = ("test",)
DISPLAY_LABELS = {
    "persistent_low_relative_moisture_at_anchor": "LOW",
    "unresolved_environmental_evidence_at_anchor": "UNRES",
    "reference_context_at_anchor": "REF",
}
REQUIRED_PREDICTION_COLUMNS = {
    "feature_view_id",
    "partition",
    "sample_id",
    "label_name_true",
    "label_name_pred",
}
REQUIRED_ORIGIN_COLUMNS = {
    "sample_id",
    "unres_origin",
    "temporal_label",
    "origin_formula",
}


@dataclass(frozen=True)
class UnresOriginPredictionJoinConfig:
    """Inputs for a non-mutating prediction/provenance join."""

    model_run_dir: Path
    unres_origin_artifact_dir: Path
    output_root: Path | None = None
    feature_view_ids: tuple[str, ...] = DEFAULT_FEATURE_VIEW_IDS
    partitions: tuple[str, ...] = DEFAULT_PARTITIONS


@dataclass(frozen=True)
class UnresOriginPredictionJoinResult:
    run_id: str
    output_dir: Path
    joined_row_count: int
    confusion_rows: int
    coverage_rows: int


def build_joined_frame(
    predictions: pd.DataFrame,
    origins: pd.DataFrame,
    *,
    feature_view_ids: Iterable[str] = DEFAULT_FEATURE_VIEW_IDS,
    partitions: Iterable[str] = DEFAULT_PARTITIONS,
) -> pd.DataFrame:
    """Return selected held-out predictions with their true UNRES origin.

    The join is intentionally keyed only by ``sample_id``/anchor because the
    origin artifact is one row per native temporal anchor.  View and partition
    remain prediction-side columns and are validated before joining.
    """

    _require_columns(predictions, REQUIRED_PREDICTION_COLUMNS, "model predictions")
    _require_columns(origins, REQUIRED_ORIGIN_COLUMNS, "UNRES origin artifact")
    selected_views = tuple(feature_view_ids)
    selected_partitions = tuple(partitions)
    if not selected_views or not selected_partitions:
        raise ValueError("At least one feature view and partition are required.")

    pred = predictions.loc[
        predictions["feature_view_id"].astype("string").isin(selected_views)
        & predictions["partition"].astype("string").isin(selected_partitions)
    ].copy()
    if pred.empty:
        raise ValueError("No model predictions match the requested feature views and partitions.")
    pred["sample_id"] = pred["sample_id"].astype("string")
    if pred["sample_id"].isna().any():
        raise ValueError("Selected model predictions contain null sample_id/anchor values.")
    duplicate_keys = pred.duplicated(["feature_view_id", "partition", "sample_id"], keep=False)
    if duplicate_keys.any():
        examples = pred.loc[duplicate_keys, ["feature_view_id", "partition", "sample_id"]].head(10).to_dict("records")
        raise ValueError(f"Selected model predictions are not unique by view/partition/anchor: {examples}")
    unknown_predictions = sorted(set(pred["label_name_pred"].dropna()) - set(DISPLAY_LABELS))
    if unknown_predictions:
        raise ValueError(f"Model predictions contain unsupported target labels: {unknown_predictions}")
    pred["pred_label"] = pred["label_name_pred"].map(DISPLAY_LABELS)

    origin = origins.loc[origins["unres_origin"].astype("string").isin(UNRES_ORIGINS)].copy()
    origin["sample_id"] = origin["sample_id"].astype("string")
    if origin["sample_id"].isna().any():
        raise ValueError("UNRES origin artifact contains null sample_id/anchor values.")
    if origin["sample_id"].duplicated().any():
        examples = origin.loc[origin["sample_id"].duplicated(keep=False), ["sample_id", "unres_origin"]].head(10).to_dict("records")
        raise ValueError(f"UNRES origin artifact is not unique by anchor: {examples}")
    origin = origin.rename(columns={"unres_origin": "true_origin"})

    joined = pred.merge(origin, on="sample_id", how="inner", validate="many_to_one", suffixes=("", "_origin"))
    if joined.empty:
        raise ValueError("The selected predictions have no matching UNRES-origin anchors.")
    invalid_true = sorted(set(joined["label_name_true"].dropna()) - {"unresolved_environmental_evidence_at_anchor"})
    if invalid_true:
        raise ValueError(f"UNRES-origin rows have unexpected true model labels: {invalid_true}")
    return joined.sort_values(["feature_view_id", "partition", "sample_id"], kind="stable").reset_index(drop=True).convert_dtypes()


def build_confusion_summary(
    joined: pd.DataFrame,
    *,
    feature_view_ids: Iterable[str] = DEFAULT_FEATURE_VIEW_IDS,
    partitions: Iterable[str] = DEFAULT_PARTITIONS,
) -> pd.DataFrame:
    """Build the requested origin-by-predicted-label table.

    Recall is defined within each true-origin slice as ``Pred UNRES / support``.
    This is not a new class-level F1: the model still predicts LOW/UNRES/REF,
    while the origin is used only to stratify the existing UNRES target.
    """

    required = {"feature_view_id", "partition", "true_origin", "pred_label"}
    _require_columns(joined, required, "joined predictions")
    rows: list[dict[str, object]] = []
    for view_id in feature_view_ids:
        for partition in partitions:
            for origin in UNRES_ORIGINS:
                subset = joined.loc[
                    joined["feature_view_id"].astype("string").eq(view_id)
                    & joined["partition"].astype("string").eq(partition)
                    & joined["true_origin"].astype("string").eq(origin)
                ]
                counts = subset["pred_label"].value_counts()
                support = int(len(subset))
                pred_unres = int(counts.get("UNRES", 0))
                rows.append(
                    {
                        "feature_view_id": view_id,
                        "partition": partition,
                        "true_origin": origin,
                        "pred_low": int(counts.get("LOW", 0)),
                        "pred_unres": pred_unres,
                        "pred_ref": int(counts.get("REF", 0)),
                        "support": support,
                        "recall": round(pred_unres / support, 6) if support else None,
                    }
                )
    return pd.DataFrame(rows).convert_dtypes()


def build_coverage_summary(
    predictions: pd.DataFrame,
    joined: pd.DataFrame,
    *,
    feature_view_ids: Iterable[str],
    partitions: Iterable[str],
) -> pd.DataFrame:
    """Report whether origin rows were found in each prediction slice."""

    rows: list[dict[str, object]] = []
    origin_ids = set(joined["sample_id"].astype("string"))
    for view_id in feature_view_ids:
        for partition in partitions:
            pred_scope = predictions.loc[
                predictions["feature_view_id"].astype("string").eq(view_id)
                & predictions["partition"].astype("string").eq(partition)
            ]
            joined_scope = joined.loc[
                joined["feature_view_id"].astype("string").eq(view_id)
                & joined["partition"].astype("string").eq(partition)
            ]
            expected = len(set(pred_scope["sample_id"].astype("string")) & origin_ids)
            matched = int(joined_scope["sample_id"].nunique())
            rows.append(
                {
                    "feature_view_id": view_id,
                    "partition": partition,
                    "prediction_rows": int(len(pred_scope)),
                    "origin_rows_expected_in_prediction_scope": expected,
                    "origin_rows_joined": matched,
                    "join_rate": round(matched / expected, 6) if expected else None,
                }
            )
    return pd.DataFrame(rows).convert_dtypes()


def build_unres_origin_prediction_join(config: UnresOriginPredictionJoinConfig) -> UnresOriginPredictionJoinResult:
    """Persist a traceable sibling artifact from an existing model run."""

    model_run_dir = config.model_run_dir.resolve()
    origin_artifact_dir = config.unres_origin_artifact_dir.resolve()
    if not model_run_dir.is_dir():
        raise FileNotFoundError(f"Model run directory does not exist: {model_run_dir}")
    if not origin_artifact_dir.is_dir():
        raise FileNotFoundError(f"UNRES-origin artifact directory does not exist: {origin_artifact_dir}")

    model_manifest_path = model_run_dir / "run_manifest.json"
    if not model_manifest_path.exists():
        raise FileNotFoundError(f"Model run manifest is missing: {model_manifest_path}")
    model_manifest = json.loads(model_manifest_path.read_text(encoding="utf-8"))
    predictions_path = _resolve_predictions_path(model_run_dir, model_manifest)
    origin_path = origin_artifact_dir / "unres_origin_assignments.parquet"
    origin_manifest_path = origin_artifact_dir / "run_metadata" / "run_manifest.json"
    if not origin_path.exists():
        raise FileNotFoundError(f"UNRES-origin assignments are missing: {origin_path}")
    if not origin_manifest_path.exists():
        raise FileNotFoundError(f"UNRES-origin artifact manifest is missing: {origin_manifest_path}")
    origin_manifest = json.loads(origin_manifest_path.read_text(encoding="utf-8"))

    predictions = pd.read_csv(predictions_path).convert_dtypes()
    origins = pd.read_parquet(origin_path).convert_dtypes()
    joined = build_joined_frame(
        predictions,
        origins,
        feature_view_ids=config.feature_view_ids,
        partitions=config.partitions,
    )
    confusion = build_confusion_summary(
        joined,
        feature_view_ids=config.feature_view_ids,
        partitions=config.partitions,
    )
    coverage = build_coverage_summary(
        predictions,
        joined,
        feature_view_ids=config.feature_view_ids,
        partitions=config.partitions,
    )
    if coverage["join_rate"].isna().any() or not coverage["join_rate"].eq(1.0).all():
        raise ValueError("UNRES-origin join is incomplete for at least one requested prediction slice.")

    output_root = (config.output_root or model_run_dir.parent).resolve()
    run_id, output_dir = create_run_directory(output_root, prefix="temporal_unres_origin_prediction_join")
    joined_path = output_dir / "unres_origin_prediction_rows.parquet"
    confusion_path = output_dir / "unres_origin_prediction_confusion.csv"
    coverage_path = output_dir / "unres_origin_prediction_join_coverage.csv"
    report_path = output_dir / "unres_origin_prediction_report.md"
    joined.to_parquet(joined_path, index=False)
    confusion.to_csv(confusion_path, index=False)
    coverage.to_csv(coverage_path, index=False)

    manifest = {
        "artifact_type": "DERIVED_UNRES_ORIGIN_PREDICTION_JOIN",
        "artifact_status": "DERIVED_ANALYSIS_ONLY",
        "authority_status": "CANDIDATE_REFERENCE_ONLY",
        "run_id": run_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_model_run_id": str(model_manifest.get("run_id", model_run_dir.name)),
        "source_model_run_dir": str(model_run_dir),
        "source_predictions_path": str(predictions_path),
        "source_unres_origin_artifact_id": str(origin_manifest.get("run_id", origin_artifact_dir.name)),
        "source_unres_origin_artifact_dir": str(origin_artifact_dir),
        "join_key": "sample_id (temporal anchor)",
        "feature_view_ids": list(config.feature_view_ids),
        "partitions": list(config.partitions),
        "model_training_executed": False,
        "new_model_inference_executed": False,
        "posthoc_prediction_analysis_executed": True,
        "native_label_mutated": False,
        "target_ontology_changed": False,
        "prediction_label_mapping": DISPLAY_LABELS,
        "recall_definition": "Pred UNRES / support within each true UNRES origin slice",
        "source_files": {
            "model_run_manifest": {"path": str(model_manifest_path), "sha256": _sha256(model_manifest_path)},
            "predictions": {"path": str(predictions_path), "sha256": _sha256(predictions_path)},
            "unres_origin_manifest": {"path": str(origin_manifest_path), "sha256": _sha256(origin_manifest_path)},
            "unres_origin_assignments": {"path": str(origin_path), "sha256": _sha256(origin_path)},
        },
        "output_files": {
            "joined_rows": str(joined_path),
            "confusion_summary": str(confusion_path),
            "join_coverage": str(coverage_path),
            "report": str(report_path),
        },
        "joined_row_count": int(len(joined)),
        "confusion_summary": _json_records(confusion),
        "join_coverage": _json_records(coverage),
    }
    write_json(output_dir / "run_metadata" / "run_manifest.json", manifest)
    write_text(output_dir / "README.md", build_readme(manifest, report_path.name))
    write_text(report_path, build_report(manifest, confusion, coverage))
    return UnresOriginPredictionJoinResult(
        run_id=run_id,
        output_dir=output_dir,
        joined_row_count=len(joined),
        confusion_rows=len(confusion),
        coverage_rows=len(coverage),
    )


def _resolve_predictions_path(model_run_dir: Path, model_manifest: dict[str, object]) -> Path:
    profile_name = str(model_manifest.get("profile_name", ""))
    candidates = []
    if profile_name:
        candidates.append(model_run_dir / "profiles" / profile_name / "per_sample_predictions.csv")
    candidates.extend(model_run_dir.rglob("per_sample_predictions.csv"))
    unique_candidates = list(dict.fromkeys(path.resolve() for path in candidates if path.exists()))
    if len(unique_candidates) != 1:
        raise FileNotFoundError(f"Expected one per_sample_predictions.csv under {model_run_dir}, found: {unique_candidates}")
    return unique_candidates[0]


def _require_columns(frame: pd.DataFrame, required: set[str], name: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{name} is missing required columns: {missing}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    return json.loads(frame.to_json(orient="records"))
