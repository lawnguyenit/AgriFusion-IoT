"""Create a provenance-only split of temporal UNRES origins.

This module is deliberately not a label engine.  It reads a published native
release and its audit ledger, derives an origin field for the already
materialized temporal UNRES label, and writes a sibling analysis artifact.
The native release, model inputs, weights, and benchmark manifests are never
mutated by this analysis.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from Backend.Benchmark.shared.artifacts import create_run_directory, write_json, write_text

from .unres_origin_contract import (
    AUXILIARY_POINT_LABEL,
    LOW_POINT_LABEL,
    NOT_UNRES,
    TEMPORAL_UNRES_LABEL,
    UNRES_A,
    UNRES_K,
)
from .unres_origin_reporting import build_readme, build_report, count_payload, summarise_scope


@dataclass(frozen=True)
class UnresOriginSplitConfig:
    """Inputs for the audit-only derived artifact."""

    release_dir: Path
    output_root: Path
    protocol_run_dir: Path | None = None
    horizon_id: str = "3h"


@dataclass(frozen=True)
class UnresOriginSplitResult:
    run_id: str
    output_dir: Path
    native_row_count: int
    native_unres_k_count: int
    native_unres_a_count: int


def derive_unres_origin_rows(
    *,
    temporal_assignments: pd.DataFrame,
    temporal_resolutions: pd.DataFrame,
    point_resolutions: pd.DataFrame,
    rule_firings: pd.DataFrame,
    temporal_evidence: pd.DataFrame,
) -> pd.DataFrame:
    """Derive mutually exclusive origins for the materialized temporal UNRES.

    The source label remains in ``temporal_label``.  ``unres_origin`` is an
    analysis-only field with values ``UNRES_K``, ``UNRES_A``, or ``NOT_UNRES``.
    The function fails closed when the audit evidence cannot prove either
    requested formula.
    """

    _require_columns(
        temporal_assignments,
        {
            "sample_id",
            "label",
            "source_label",
            "horizon_id",
        },
        "temporal assignments",
    )
    _require_columns(
        temporal_resolutions,
        {"sample_id", "task_id", "horizon_id", "resolved_label", "support_depth_at_anchor", "required_k"},
        "temporal resolutions",
    )
    _require_columns(point_resolutions, {"sample_id", "task_id", "resolved_label", "resolution_code"}, "point resolutions")
    _require_columns(
        rule_firings,
        {"sample_id", "task_id", "rule_id", "evidence_state", "evidence_value", "threshold_value", "comparison_operator"},
        "rule firings",
    )
    _require_columns(temporal_evidence, {"sample_id", "horizon_id", "representation_history_status"}, "temporal evidence")

    temporal = temporal_assignments.loc[:, ["sample_id", "label", "source_label", "horizon_id"]].copy()
    temporal = temporal.rename(columns={"label": "temporal_label", "source_label": "point_source_label"})
    temporal["sample_id"] = temporal["sample_id"].astype("string")
    temporal["horizon_id"] = temporal["horizon_id"].astype("string")

    temporal_resolution = temporal_resolutions.loc[
        temporal_resolutions["task_id"].astype("string").eq("TEMPORAL_ANCHOR"),
        ["sample_id", "horizon_id", "resolved_label", "support_depth_at_anchor", "required_k"],
    ].copy()
    temporal_resolution = temporal_resolution.rename(columns={"resolved_label": "temporal_resolved_label"})
    temporal_resolution["sample_id"] = temporal_resolution["sample_id"].astype("string")
    temporal_resolution["horizon_id"] = temporal_resolution["horizon_id"].astype("string")
    temporal_resolution = temporal_resolution.drop_duplicates(["sample_id", "horizon_id"], keep=False)
    if temporal_resolution.empty:
        raise ValueError("Temporal resolution audit has no unique TEMPORAL_ANCHOR rows.")

    point = point_resolutions.loc[
        point_resolutions["task_id"].astype("string").eq("POINT"),
        ["sample_id", "resolved_label", "resolution_code"],
    ].copy()
    point = point.rename(columns={"resolved_label": "point_label", "resolution_code": "point_resolution_code"})
    point["sample_id"] = point["sample_id"].astype("string")
    point = point.drop_duplicates("sample_id", keep=False)
    if point.empty:
        raise ValueError("Point resolution audit has no unique POINT rows.")

    firings = rule_firings.loc[rule_firings["task_id"].astype("string").eq("POINT")].copy()
    firings["sample_id"] = firings["sample_id"].astype("string")
    low = firings.loc[firings["rule_id"].astype("string").eq("LOW_RELATIVE_MOISTURE")].copy()
    if low["sample_id"].duplicated().any():
        raise ValueError("Point rule audit has duplicate LOW_RELATIVE_MOISTURE firings per sample.")
    low = low.loc[
        :, ["sample_id", "evidence_state", "evidence_value", "threshold_value", "comparison_operator"]
    ].rename(
        columns={
            "evidence_state": "low_rule_state",
            "evidence_value": "moisture_value",
            "threshold_value": "q_threshold",
            "comparison_operator": "q_comparator",
        }
    )

    auxiliary = firings.loc[
        firings["rule_id"].astype("string").isin(["THERMAL_CONTEXT", "MOISTURE_RISE", "EC_SHIFT"])
        & firings["evidence_state"].astype("string").eq("POSITIVE"),
        ["sample_id", "rule_id"],
    ].copy()
    aux_positive = (
        auxiliary.groupby("sample_id", dropna=False)["rule_id"]
        .agg(lambda values: "|".join(sorted({str(value) for value in values})))
        .rename("aux_positive_rule_ids")
        .reset_index()
    )
    aux_positive["aux_positive_count"] = aux_positive["aux_positive_rule_ids"].map(
        lambda value: len(str(value).split("|")) if str(value) else 0
    )

    evidence = temporal_evidence.loc[:, ["sample_id", "horizon_id", "representation_history_status"]].copy()
    evidence["sample_id"] = evidence["sample_id"].astype("string")
    evidence["horizon_id"] = evidence["horizon_id"].astype("string")
    evidence = evidence.drop_duplicates(["sample_id", "horizon_id"], keep=False)

    joined = (
        temporal.merge(temporal_resolution, on=["sample_id", "horizon_id"], how="left", validate="one_to_one")
        .merge(point, on="sample_id", how="left", validate="one_to_one")
        .merge(low, on="sample_id", how="left", validate="one_to_one")
        .merge(aux_positive, on="sample_id", how="left", validate="one_to_one")
        .merge(evidence, on=["sample_id", "horizon_id"], how="left", validate="one_to_one")
    )
    joined["aux_positive_rule_ids"] = joined["aux_positive_rule_ids"].fillna("").astype("string")
    joined["aux_positive_count"] = pd.to_numeric(joined["aux_positive_count"], errors="coerce").fillna(0).astype("Int64")
    joined["support_depth_at_anchor"] = pd.to_numeric(joined["support_depth_at_anchor"], errors="coerce").astype("Int64")
    joined["required_k"] = pd.to_numeric(joined["required_k"], errors="coerce").astype("Int64")
    joined["moisture_value"] = pd.to_numeric(joined["moisture_value"], errors="coerce")
    joined["q_threshold"] = pd.to_numeric(joined["q_threshold"], errors="coerce")
    joined["low_rule_state"] = joined["low_rule_state"].astype("string")
    joined["temporal_label"] = joined["temporal_label"].astype("string")
    joined["point_source_label"] = joined["point_source_label"].astype("string")

    joined["m_relation_to_q"] = "UNKNOWN"
    joined.loc[joined["moisture_value"] <= joined["q_threshold"], "m_relation_to_q"] = "M_t<=Q"
    joined.loc[joined["moisture_value"] > joined["q_threshold"], "m_relation_to_q"] = "M_t>Q"
    joined["candidate_status"] = joined["low_rule_state"].map(
        {"POSITIVE": "LOW_CANDIDATE", "NEGATIVE": "NOT_LOW_CANDIDATE"}
    ).fillna("NOT_EVALUABLE")

    is_unres = joined["temporal_label"].eq(TEMPORAL_UNRES_LABEL)
    unres_k = (
        is_unres
        & joined["point_source_label"].eq(LOW_POINT_LABEL)
        & joined["low_rule_state"].eq("POSITIVE")
        & joined["support_depth_at_anchor"].lt(joined["required_k"])
    )
    unres_a = (
        is_unres
        & joined["point_source_label"].eq(AUXILIARY_POINT_LABEL)
        & joined["low_rule_state"].eq("NEGATIVE")
        & joined["aux_positive_count"].gt(0)
    )
    joined["unres_origin"] = NOT_UNRES
    joined.loc[unres_k, "unres_origin"] = UNRES_K
    joined.loc[unres_a, "unres_origin"] = UNRES_A
    joined["origin_formula"] = "N/A"
    joined.loc[unres_k, "origin_formula"] = "M_t <= Q and d_t < K"
    joined.loc[unres_a, "origin_formula"] = "M_t > Q and E_aux+"

    unresolved_unclassified = joined.loc[is_unres & joined["unres_origin"].eq(NOT_UNRES)]
    if not unresolved_unclassified.empty:
        sample_ids = unresolved_unclassified["sample_id"].astype("string").head(10).tolist()
        raise ValueError(f"Temporal UNRES rows have an unclassified origin; examples: {sample_ids}")

    invalid_k = joined.loc[unres_k & ((joined["m_relation_to_q"] != "M_t<=Q") | joined["support_depth_at_anchor"].ge(joined["required_k"]))]
    if not invalid_k.empty:
        raise ValueError("UNRES_K rows failed the explicit M_t<=Q and d_t<K proof.")
    invalid_a = joined.loc[unres_a & ((joined["m_relation_to_q"] != "M_t>Q") | joined["aux_positive_count"].le(0))]
    if not invalid_a.empty:
        raise ValueError("UNRES_A rows failed the explicit M_t>Q and E_aux+ proof.")

    output_columns = [
        "sample_id",
        "horizon_id",
        "temporal_label",
        "unres_origin",
        "origin_formula",
        "point_source_label",
        "point_label",
        "point_resolution_code",
        "candidate_status",
        "m_relation_to_q",
        "moisture_value",
        "q_threshold",
        "q_comparator",
        "support_depth_at_anchor",
        "required_k",
        "aux_positive_rule_ids",
        "aux_positive_count",
        "representation_history_status",
    ]
    return joined.loc[:, output_columns].sort_values(["horizon_id", "sample_id"], kind="stable").reset_index(drop=True).convert_dtypes()


def build_unres_origin_split(config: UnresOriginSplitConfig) -> UnresOriginSplitResult:
    """Build a sibling, audit-only artifact for the temporal UNRES origins."""

    release_dir = config.release_dir.resolve()
    if not release_dir.is_dir():
        raise FileNotFoundError(f"Native release directory does not exist: {release_dir}")
    horizon = str(config.horizon_id)
    temporal_dir = release_dir / "tasks" / "temporal" / f"horizon_{horizon}"
    temporal_assignments_path = temporal_dir / "assignments.parquet"
    temporal_evidence_path = temporal_dir / "evidence.parquet"
    temporal_resolutions_path = release_dir / "audit" / "resolutions.parquet"
    point_resolutions_path = release_dir / "audit" / "resolutions.parquet"
    rule_firings_path = release_dir / "audit" / "rule_firings.parquet"
    for path in (
        temporal_assignments_path,
        temporal_evidence_path,
        temporal_resolutions_path,
        point_resolutions_path,
        rule_firings_path,
    ):
        if not path.exists():
            raise FileNotFoundError(f"Required native audit input is missing: {path}")

    temporal_assignments = pd.read_parquet(temporal_assignments_path).convert_dtypes()
    temporal_assignments = temporal_assignments.loc[temporal_assignments["horizon_id"].astype("string").eq(horizon)].copy()
    temporal_resolutions = pd.read_parquet(temporal_resolutions_path).convert_dtypes()
    temporal_resolutions = temporal_resolutions.loc[
        temporal_resolutions["task_id"].astype("string").eq("TEMPORAL_ANCHOR")
        & temporal_resolutions["horizon_id"].astype("string").eq(horizon)
    ].copy()
    point_resolutions = pd.read_parquet(point_resolutions_path).convert_dtypes()
    point_resolutions = point_resolutions.loc[point_resolutions["task_id"].astype("string").eq("POINT")].copy()
    rule_firings = pd.read_parquet(rule_firings_path).convert_dtypes()
    temporal_evidence = pd.read_parquet(temporal_evidence_path).convert_dtypes()
    temporal_evidence = temporal_evidence.loc[temporal_evidence["horizon_id"].astype("string").eq(horizon)].copy()

    rows = derive_unres_origin_rows(
        temporal_assignments=temporal_assignments,
        temporal_resolutions=temporal_resolutions,
        point_resolutions=point_resolutions,
        rule_firings=rule_firings,
        temporal_evidence=temporal_evidence,
    )
    q_values = rows["q_threshold"].dropna().unique()
    k_values = rows["required_k"].dropna().astype(int).unique()
    if len(q_values) != 1 or len(k_values) != 1:
        raise ValueError(f"Expected one Q and K authority in the release, found Q={q_values.tolist()} K={k_values.tolist()}")

    run_id, output_dir = create_run_directory(config.output_root.resolve(), prefix="temporal_unres_origin_split")
    metadata_dir = output_dir / "run_metadata"
    rows_path = output_dir / "unres_origin_assignments.parquet"
    summary_path = output_dir / "unres_origin_summary.csv"
    protocol_scope_path = output_dir / "protocol_scope_assignments.parquet"
    report_path = output_dir / "unres_origin_report.md"
    rows.to_parquet(rows_path, index=False)

    summary_frames: list[pd.DataFrame] = []
    native_summary = summarise_scope(rows, scope="native_release", partition="NATIVE_RELEASE")
    summary_frames.append(native_summary)
    protocol_summary: pd.DataFrame | None = None
    protocol_scope: pd.DataFrame | None = None
    if config.protocol_run_dir is not None:
        protocol_scope = _load_protocol_scope(rows, config.protocol_run_dir.resolve(), horizon)
        protocol_scope.to_parquet(protocol_scope_path, index=False)
        protocol_summary = summarise_scope(protocol_scope, scope="protocol_temporal_3h", partition_column="partition")
        summary_frames.append(protocol_summary)
    summary = pd.concat(summary_frames, ignore_index=True).convert_dtypes()
    summary.to_csv(summary_path, index=False)

    source_paths = {
        "temporal_assignments": temporal_assignments_path,
        "temporal_evidence": temporal_evidence_path,
        "audit_resolutions": temporal_resolutions_path,
        "audit_rule_firings": rule_firings_path,
        "label_release_manifest": release_dir / "run_metadata" / "label_release_manifest.json",
    }
    manifest = {
        "artifact_type": "DERIVED_TEMPORAL_UNRES_ORIGIN_ANALYSIS",
        "artifact_status": "DERIVED_ANALYSIS_ONLY",
        "authority_status": "CANDIDATE_REFERENCE_ONLY",
        "run_id": run_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_release_dir": str(release_dir),
        "source_release_id": release_dir.name,
        "horizon_id": horizon,
        "q_threshold": float(q_values[0]),
        "q_comparator": str(rows["q_comparator"].dropna().unique()[0]),
        "selected_k": int(k_values[0]),
        "protocol_run_dir": str(config.protocol_run_dir.resolve()) if config.protocol_run_dir is not None else None,
        "model_training_executed": False,
        "model_testing_executed": False,
        "native_label_mutated": False,
        "definitions": {
            UNRES_K: "temporal_label=UNRES and M_t<=Q and support_depth_at_anchor<required_k",
            UNRES_A: "temporal_label=UNRES and M_t>Q and at least one positive auxiliary rule",
            "unres_label": TEMPORAL_UNRES_LABEL,
            "q_comparator": "<=",
            "k_semantics": "support depth in strict consecutive observations",
        },
        "source_files": {
            key: {"path": str(path), "sha256": _sha256(path)} for key, path in source_paths.items()
        },
        "output_files": {
            "assignments": str(rows_path),
            "summary": str(summary_path),
            "report": str(report_path),
        },
        "native_counts": count_payload(rows),
        "protocol_counts": count_payload(protocol_scope) if protocol_scope is not None else None,
    }
    write_json(metadata_dir / "run_manifest.json", manifest)
    write_text(output_dir / "README.md", build_readme(manifest, report_path.name))
    write_text(report_path, build_report(manifest, rows, summary, protocol_scope))
    return UnresOriginSplitResult(
        run_id=run_id,
        output_dir=output_dir,
        native_row_count=len(rows),
        native_unres_k_count=int(rows["unres_origin"].eq(UNRES_K).sum()),
        native_unres_a_count=int(rows["unres_origin"].eq(UNRES_A).sum()),
    )


def _load_protocol_scope(rows: pd.DataFrame, protocol_run_dir: Path, horizon: str) -> pd.DataFrame:
    manifest_path = protocol_run_dir / "primary_protocol" / "runner" / "task_training_manifest.parquet"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Protocol task-training manifest is missing: {manifest_path}")
    manifest = pd.read_parquet(manifest_path, columns=["sample_id", "feature_view_id", "partition", "final_trainability"]).convert_dtypes()
    view_id = f"v2_temporal_mini_{horizon}"
    scope = manifest.loc[manifest["feature_view_id"].astype("string").eq(view_id)].copy()
    if scope.empty:
        raise ValueError(f"Protocol manifest has no temporal scope view: {view_id}")
    scope["sample_id"] = scope["sample_id"].astype("string")
    scope = scope.drop_duplicates("sample_id", keep=False)
    if scope.empty:
        raise ValueError("Protocol temporal scope does not have unique sample IDs.")
    selected = rows.merge(scope, on="sample_id", how="inner", validate="one_to_one")
    if len(selected) != len(scope):
        missing = sorted(set(scope["sample_id"]) - set(selected["sample_id"]))[:10]
        raise ValueError(f"Protocol temporal scope contains rows absent from native release: {missing}")
    return selected


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

