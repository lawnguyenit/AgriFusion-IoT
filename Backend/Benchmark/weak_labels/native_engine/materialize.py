from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class NativeTaskArtifacts:
    point_evidence: pd.DataFrame
    point_assignments: pd.DataFrame
    temporal_evidence: dict[str, pd.DataFrame]
    temporal_assignments: dict[str, pd.DataFrame]
    same_y_transfers: dict[str, pd.DataFrame]
    intrinsic_assignments: pd.DataFrame
    semantic_fold_projection: pd.DataFrame


def materialize_from_assignments(assignments: pd.DataFrame, schema_contract: dict[str, object] | None = None) -> pd.DataFrame:
    """Return a materialized label frame whose source of truth is Assignment rows."""
    required = {"assignment_id", "sample_id", "task_id", "label", "resolution_instance_id"}
    missing = required - set(assignments.columns)
    if missing:
        raise ValueError(f"Assignment frame is missing required columns: {sorted(missing)}")
    result = assignments.copy()
    result["materialized_from_assignment"] = True
    result["assignment_schema_version"] = result.get("assignment_schema_version", "native.assignment.v1")
    return result.convert_dtypes()


def build_intrinsic_candidate_assignments(assignments: pd.DataFrame) -> pd.DataFrame:
    result = assignments.copy()
    result["semantic_assignment_admissible"] = result["train_inclusion_status"].astype("string") == "INCLUDED"
    return result.convert_dtypes()


def build_semantic_fold_projection(assignments: pd.DataFrame, fold_registry: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for fold in fold_registry.to_dict(orient="records"):
        for assignment in assignments.to_dict(orient="records"):
            rows.append(
                {
                    "assignment_id": assignment["assignment_id"],
                    "fold_policy_id": fold.get("fold_policy_id"),
                    "fold_id": fold.get("fold_id"),
                    "split_role": "TRAIN" if fold.get("fold_status") == "COMPLETE" else "UNUSABLE",
                    "purge_status": "NOT_APPLIED_IN_PHASE_C",
                    "label_dependency_admissible": True,
                    "persistence_dependency_admissible": True,
                    "temporal_window_dependency_admissible": True,
                    "semantic_assignment_admissible": bool(assignment.get("semantic_assignment_admissible", False)),
                    "evaluation_anchor_admissible": bool(fold.get("evaluation_usable", False)),
                }
            )
    return pd.DataFrame(rows).convert_dtypes()

