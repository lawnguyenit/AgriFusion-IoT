from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .audit import (
    SUPPORT_PROFILE_ID,
    audit_candidate_support,
    summarize_entity_estimability,
    summarize_entity_support,
)


def run_external_support_audit(
    *, labels_path: Path, registry_path: Path, splits_path: Path, output_root: Path
) -> Path:
    labels = pd.read_parquet(labels_path)
    registry = pd.read_csv(registry_path)
    splits = pd.read_parquet(splits_path)
    audit = audit_candidate_support(labels=labels, registry=registry, splits=splits)
    entity_support = summarize_entity_support(labels=labels, registry=registry, splits=splits)
    entity_estimability = summarize_entity_estimability(entity_support)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_id = f"external_support_{stamp}"
    output_dir = output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    audit_path = output_dir / "candidate_support_gate.csv"
    audit.to_csv(audit_path, index=False)
    entity_support_path = output_dir / "candidate_entity_support.csv"
    entity_support.to_csv(entity_support_path, index=False)
    candidate_summary = summarize_candidate_gate_rows(audit)
    summary_path = output_dir / "candidate_gate_summary.csv"
    candidate_summary.to_csv(summary_path, index=False)
    entity_estimability_path = output_dir / "candidate_entity_estimability.csv"
    entity_estimability.to_csv(entity_estimability_path, index=False)
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "support_profile_id": SUPPORT_PROFILE_ID,
        "profile_authority": "USER_APPROVED_EXTERNAL_MAPPING_OF_B2_TEMPORAL_FLOORS",
        "gate_definition": {
            "minimum_per_class_per_partition": 20,
            "minimum_persistent_events_per_partition": 5,
            "minimum_distinct_persistent_episode_clusters_per_partition": 5,
            "episode_cluster_key": "entity_id + contiguous persistent episode",
        },
        "support_layers": {
            "B2_A_aggregate_model_run_support": "candidate_support_gate.csv; B2 floors determine aggregate fit support",
            "B2_E_entity_claim_estimability": "candidate_entity_estimability.csv; reports mathematical two-class discrimination and per-entity class/event/episode support adequacy separately; descriptive, never blocks aggregate diagnostic fitting",
        },
        "entity_support_floors": {
            "minimum_positive_rows": 20,
            "minimum_negative_rows": 20,
            "minimum_persistent_events": 5,
            "minimum_distinct_persistent_episode_clusters": 5,
            "legacy_entity_claim_estimability_status": "compatibility alias for mathematical two-class discrimination; use entity_support_adequacy_status for evidence sufficiency",
        },
        "input_artifacts": {
            "labels": {"path": str(labels_path.resolve()), "sha256": _sha256(labels_path)},
            "registry": {"path": str(registry_path.resolve()), "sha256": _sha256(registry_path)},
            "splits": {"path": str(splits_path.resolve()), "sha256": _sha256(splits_path)},
        },
        "candidate_count": int(len(candidate_summary)),
        "entity_support_path": str(entity_support_path.resolve()),
        "entity_support_sha256": _sha256(entity_support_path),
        "entity_estimability_path": str(entity_estimability_path.resolve()),
        "entity_estimability_sha256": _sha256(entity_estimability_path),
        "passing_candidate_count": int(candidate_summary["all_partitions_pass"].sum()),
        "model_fit_performed": False,
    }
    (output_dir / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_dir


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def summarize_candidate_gate_rows(audit: pd.DataFrame) -> pd.DataFrame:
    """Aggregate partition gates with a true integer failure count."""
    required = {"target_id", "q_id", "threshold_scope", "tail_share", "tau_minutes", "support_gate_pass"}
    if not required.issubset(audit.columns):
        raise ValueError(f"Support rows are missing summary fields: {sorted(required - set(audit.columns))}")
    summary = (
        audit.groupby(["target_id", "q_id", "threshold_scope", "tail_share", "tau_minutes"], dropna=False)
        .agg(
            all_partitions_pass=("support_gate_pass", "all"),
            failing_partition_count=("support_gate_pass", lambda values: int((~values.astype(bool)).sum())),
        )
        .reset_index()
    )
    summary["failing_partition_count"] = summary["failing_partition_count"].astype("int64")
    summary["all_partitions_pass"] = summary["all_partitions_pass"].astype("boolean")
    return summary
