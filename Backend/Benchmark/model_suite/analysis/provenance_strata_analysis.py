"""Orchestration for the provenance-aware, post-hoc model analysis."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from Backend.Benchmark.shared.artifacts import create_run_directory, write_json, write_text
from Backend.Benchmark.weak_labels.analysis.temporal_target_views import Y_EVENT, Y_ONLINE
from Backend.Benchmark.weak_labels.infrastructure.hashing import file_sha256

from .provenance_strata_analysis_data import (
    build_event_online_probability_deltas,
    build_k_contrasts,
    build_k_decomposition,
    build_prediction_count_summary,
    build_prediction_transitions,
    build_probability_summary,
    build_provenance_frame,
    build_provenance_summary,
    build_row_normalized_rates,
    join_predictions_with_provenance,
    pair_event_online_predictions,
    select_predictions,
)
from .provenance_strata_analysis_reporting import (
    build_report,
    write_event_online_delta_plot,
    write_k_probability_plot,
    write_online_heatmap,
)

DEFAULT_FEATURE_VIEW_IDS = ("v2_temporal_mini_3h", "v2_temporal_full_3h")
DEFAULT_PARTITIONS = ("validation", "test")


@dataclass(frozen=True)
class ProvenanceStrataAnalysisConfig:
    """Inputs for the non-mutating five-strata analysis."""

    model_suite_run_dir: Path
    target_views_artifact_dir: Path
    output_root: Path | None = None
    profile_name: str = "temporal_event_online_3h"
    feature_view_ids: tuple[str, ...] = DEFAULT_FEATURE_VIEW_IDS
    partitions: tuple[str, ...] = DEFAULT_PARTITIONS


@dataclass(frozen=True)
class ProvenanceStrataAnalysisResult:
    run_id: str
    output_dir: Path
    provenance_row_count: int
    online_prediction_row_count: int
    event_prediction_row_count: int
    paired_prediction_row_count: int


def build_provenance_strata_analysis(
    config: ProvenanceStrataAnalysisConfig,
) -> ProvenanceStrataAnalysisResult:
    """Persist a traceable report using existing predictions only."""

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
    for path, description in (
        (model_manifest_path, "model run manifest"),
        (target_manifest_path, "target-view manifest"),
        (target_path, "target-view assignments"),
    ):
        if not path.exists():
            raise FileNotFoundError(f"{description} is missing: {path}")

    model_manifest = json.loads(model_manifest_path.read_text(encoding="utf-8"))
    target_manifest = json.loads(target_manifest_path.read_text(encoding="utf-8"))
    prediction_path = _resolve_prediction_path(model_run_dir, config.profile_name)
    predictions = pd.read_csv(prediction_path).convert_dtypes()
    targets = pd.read_parquet(target_path).convert_dtypes()

    provenance = build_provenance_frame(targets, target_view_id=Y_ONLINE)
    selected_online = select_predictions(
        predictions,
        target_view_id=Y_ONLINE,
        feature_view_ids=config.feature_view_ids,
        partitions=config.partitions,
    )
    selected_event = select_predictions(
        predictions,
        target_view_id=Y_EVENT,
        feature_view_ids=config.feature_view_ids,
        partitions=config.partitions,
    )
    online_joined = join_predictions_with_provenance(
        selected_online, provenance, prediction_source="online"
    )
    event_joined = join_predictions_with_provenance(
        selected_event, provenance, prediction_source="event"
    )
    _assert_aligned_target_scopes(online_joined, event_joined)
    paired = pair_event_online_predictions(selected_online, selected_event, provenance)

    online_counts = build_prediction_count_summary(online_joined)
    online_rates = build_row_normalized_rates(online_counts)
    online_probabilities = build_probability_summary(online_joined)
    event_counts = build_prediction_count_summary(event_joined)
    event_rates = build_row_normalized_rates(event_counts)
    event_probabilities = build_probability_summary(event_joined)
    k_decomposition = build_k_decomposition(online_joined)
    k_contrasts = build_k_contrasts(k_decomposition)
    comparator_deltas = build_event_online_probability_deltas(paired)
    transitions = build_prediction_transitions(paired)
    provenance_summary = build_provenance_summary(provenance)

    run_id, output_dir = create_run_directory(
        (config.output_root or model_run_dir.parent).resolve(),
        prefix="provenance_strata_analysis",
    )
    paths = _persist_tables(
        output_dir,
        provenance,
        online_joined,
        event_joined,
        paired,
        provenance_summary,
        online_counts,
        online_rates,
        online_probabilities,
        event_counts,
        event_rates,
        event_probabilities,
        k_decomposition,
        k_contrasts,
        comparator_deltas,
        transitions,
    )
    chart_paths = {
        "online_heatmap_test": output_dir / "online_provenance_heatmap_test.png",
        "k_probability_test": output_dir / "k_state_p_low_test.png",
        "event_online_delta_test": output_dir / "event_online_p_low_delta_test.png",
    }
    write_online_heatmap(online_rates, chart_paths["online_heatmap_test"])
    write_k_probability_plot(k_decomposition, chart_paths["k_probability_test"])
    write_event_online_delta_plot(comparator_deltas, chart_paths["event_online_delta_test"])

    manifest = _build_manifest(
        run_id=run_id,
        model_manifest=model_manifest,
        model_manifest_path=model_manifest_path,
        model_run_dir=model_run_dir,
        prediction_path=prediction_path,
        target_manifest=target_manifest,
        target_manifest_path=target_manifest_path,
        target_dir=target_dir,
        target_path=target_path,
        config=config,
        output_paths={**paths, **chart_paths},
        provenance_summary=provenance_summary,
        online_joined=online_joined,
        event_joined=event_joined,
        paired=paired,
        k_decomposition=k_decomposition,
    )
    write_json(output_dir / "run_metadata.json", manifest)
    write_text(output_dir / "README.md", _build_readme(manifest))
    write_text(
        output_dir / "provenance_strata_report.md",
        build_report(
            manifest,
            provenance_summary,
            online_counts,
            online_rates,
            online_probabilities,
            event_counts,
            event_rates,
            event_probabilities,
            k_decomposition,
            k_contrasts,
            comparator_deltas,
            transitions,
        ),
    )
    return ProvenanceStrataAnalysisResult(
        run_id=run_id,
        output_dir=output_dir,
        provenance_row_count=int(len(provenance)),
        online_prediction_row_count=int(len(online_joined)),
        event_prediction_row_count=int(len(event_joined)),
        paired_prediction_row_count=int(len(paired)),
    )


def _persist_tables(
    output_dir: Path,
    provenance: pd.DataFrame,
    online_joined: pd.DataFrame,
    event_joined: pd.DataFrame,
    paired: pd.DataFrame,
    provenance_summary: pd.DataFrame,
    online_counts: pd.DataFrame,
    online_rates: pd.DataFrame,
    online_probabilities: pd.DataFrame,
    event_counts: pd.DataFrame,
    event_rates: pd.DataFrame,
    event_probabilities: pd.DataFrame,
    k_decomposition: pd.DataFrame,
    k_contrasts: pd.DataFrame,
    comparator_deltas: pd.DataFrame,
    transitions: pd.DataFrame,
) -> dict[str, Path]:
    parquet_frames = {
        "provenance_assignments": provenance,
        "online_prediction_rows": online_joined,
        "event_prediction_rows": event_joined,
        "paired_event_online_prediction_rows": paired,
    }
    csv_frames = {
        "provenance_population_summary": provenance_summary,
        "online_provenance_confusion_counts": online_counts,
        "online_provenance_row_rates": online_rates,
        "online_provenance_probabilities": online_probabilities,
        "event_provenance_confusion_counts": event_counts,
        "event_provenance_row_rates": event_rates,
        "event_provenance_probabilities": event_probabilities,
        "k_specific_decomposition": k_decomposition,
        "k_specific_contrasts": k_contrasts,
        "event_online_probability_deltas": comparator_deltas,
        "event_online_prediction_transitions": transitions,
    }
    paths: dict[str, Path] = {}
    for name, frame in parquet_frames.items():
        path = output_dir / f"{name}.parquet"
        frame.to_parquet(path, index=False)
        paths[name] = path
    for name, frame in csv_frames.items():
        path = output_dir / f"{name}.csv"
        frame.to_csv(path, index=False)
        paths[name] = path
    return paths


def _build_manifest(
    *,
    run_id: str,
    model_manifest: dict[str, object],
    model_manifest_path: Path,
    model_run_dir: Path,
    prediction_path: Path,
    target_manifest: dict[str, object],
    target_manifest_path: Path,
    target_dir: Path,
    target_path: Path,
    config: ProvenanceStrataAnalysisConfig,
    output_paths: dict[str, Path],
    provenance_summary: pd.DataFrame,
    online_joined: pd.DataFrame,
    event_joined: pd.DataFrame,
    paired: pd.DataFrame,
    k_decomposition: pd.DataFrame,
) -> dict[str, object]:
    q_metadata = _load_q_metadata(target_manifest)
    return {
        "artifact_type": "PROVENANCE_STRATA_POSTHOC_ANALYSIS",
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
        "primary_target_view_id": Y_ONLINE,
        "retrospective_comparator_target_view_id": Y_EVENT,
        "feature_view_ids": list(config.feature_view_ids),
        "partitions": list(config.partitions),
        "operationalization_id": q_metadata["operationalization_id"],
        "selected_k": q_metadata["selected_k"],
        "q_value": q_metadata["q_value"],
        "q_comparison_operator": q_metadata["q_comparison_operator"],
        "model_output_ontology": ["LOW", "UNRES", "REF"],
        "provenance_strata": ["LOW", "U_K_succ", "U_K_fail", "U_A", "REF"],
        "provenance_definitions": {
            "LOW": "Y_online=LOW, M_t<=Q, d_t>=K",
            "U_K_succ": "Y_online=UNRES, M_t<=Q, d_t<K, UNRES_K, run_complete and L_r>=K",
            "U_K_fail": "Y_online=UNRES, M_t<=Q, d_t<K, UNRES_K, run_complete and L_r<K",
            "U_A": "Y_online=UNRES, M_t>Q, UNRES_A, aux_positive_count>0",
            "REF": "Y_online=REF",
        },
        "target_semantics_by_stratum": {
            "LOW": {"Y_online": "LOW", "Y_event": "LOW"},
            "U_K_succ": {"Y_online": "UNRES", "Y_event": "LOW"},
            "U_K_fail": {"Y_online": "UNRES", "Y_event": "UNRES"},
            "U_A": {"Y_online": "UNRES", "Y_event": "UNRES"},
            "REF": {"Y_online": "REF", "Y_event": "REF"},
        },
        "k_definition": "required_k from target lineage; current release is K=3",
        "future_values_used_for": "provenance stratification and retrospective event comparison only",
        "future_values_forbidden_in_model_inputs": True,
        "event_role": "retrospective semantic comparator, not independent ground truth",
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
        "output_files": {name: str(path) for name, path in output_paths.items()},
        "row_counts": {
            "provenance_rows": int(len(provenance_summary) and provenance_summary["row_count"].sum()),
            "online_prediction_rows": int(len(online_joined)),
            "event_prediction_rows": int(len(event_joined)),
            "paired_prediction_rows": int(len(paired)),
            "paired_unique_samples": int(paired["sample_id"].nunique()),
            "k_decomposition_rows": int(len(k_decomposition)),
        },
        "provenance_population_summary": _json_records(provenance_summary),
    }


def _assert_aligned_target_scopes(online: pd.DataFrame, event: pd.DataFrame) -> None:
    keys = ["feature_view_id", "partition", "fold_id", "sample_id"]
    online_keys = set(map(tuple, online.loc[:, keys].astype("string").itertuples(index=False, name=None)))
    event_keys = set(map(tuple, event.loc[:, keys].astype("string").itertuples(index=False, name=None)))
    if online_keys != event_keys:
        raise ValueError(
            f"Online/event prediction scopes are not aligned: online_only={len(online_keys - event_keys)}, event_only={len(event_keys - online_keys)}"
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


def _load_q_metadata(target_manifest: dict[str, object]) -> dict[str, object]:
    """Read the locked Q/K identifiers without changing the target artifact."""

    selected_k = target_manifest.get("selected_k")
    source_native_dir = target_manifest.get("source_native_release_dir")
    threshold_path = (
        Path(str(source_native_dir)) / "audit" / "threshold_registry.csv"
        if source_native_dir
        else Path()
    )
    q_value: object = None
    q_operator: object = None
    if threshold_path.exists():
        thresholds = pd.read_csv(threshold_path)
        q_rows = thresholds.loc[thresholds["threshold_id"].astype("string").str.contains("LOW_MOISTURE", na=False)]
        if len(q_rows) == 1:
            q_value = float(q_rows.iloc[0]["threshold_value"])
            q_operator = str(q_rows.iloc[0]["comparison_operator"])
    operationalization_id = "Q10-K3" if q_value == 59.96 and selected_k == 3 else None
    return {
        "operationalization_id": operationalization_id or target_manifest.get("operationalization_id") or "unknown",
        "selected_k": selected_k,
        "q_value": q_value,
        "q_comparison_operator": q_operator,
    }


def _build_readme(manifest: dict[str, object]) -> str:
    return f"""# Provenance-strata post-hoc analysis

This sibling artifact analyzes existing `{manifest['source_model_run_id']}`
predictions. It keeps the three model outputs `LOW/UNRES/REF` and adds five
lineage strata for audit: `LOW`, `U_K_succ`, `U_K_fail`, `U_A`, and `REF`.

No model weights were loaded, no new inference was run, no retraining occurred,
and no native labels or features were changed. Future run length is used only
after prediction for retrospective stratification. See
`provenance_strata_report.md` and `run_metadata.json`.
"""


__all__ = [
    "DEFAULT_FEATURE_VIEW_IDS",
    "DEFAULT_PARTITIONS",
    "ProvenanceStrataAnalysisConfig",
    "ProvenanceStrataAnalysisResult",
    "build_provenance_strata_analysis",
]
