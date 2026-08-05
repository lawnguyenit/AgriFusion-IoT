"""Create a human-readable Phase B2 review input without making decisions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from Backend.Benchmark.common.digests import file_sha256


def build_phase_b2_review_template(
    b1_decision_pack_dir: Path,
    selection_config_path: Path,
    output_path: Path,
) -> Path:
    """Write a review template populated with B1 lineage and observations.

    The file is intentionally not a valid approval: ``decision_status`` is
    ``PENDING_REVIEW`` and reviewer-owned thresholds/contracts are null. The
    reviewer confirms or edits these fields before B2 can freeze anything.
    """

    b1_dir = b1_decision_pack_dir.resolve()
    selection_path = selection_config_path.resolve()
    manifest_path = b1_dir / "run_metadata" / "run_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing B1 manifest: {manifest_path}")
    if not selection_path.exists():
        raise FileNotFoundError(f"Missing selection profile: {selection_path}")

    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    selection = yaml.safe_load(selection_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(selection, dict):
        raise ValueError("B1 manifest and selection profile must be mappings.")
    primary = selection.get("primary")
    diagnostics = selection.get("diagnostics")
    if not isinstance(primary, dict) or not isinstance(diagnostics, list):
        raise ValueError("Selection profile must contain primary and diagnostics.")

    distribution_path = b1_dir / "operationalization" / "qk_distribution_audit.parquet"
    observed_support = _summarize_support(distribution_path, primary)
    payload: dict[str, Any] = {
        "decision_status": "PENDING_REVIEW",
        "decision_id": None,
        "reviewer_ids": [],
        "reviewed_at_utc": None,
        "reviewed_decision_pack_hash": manifest.get("decision_pack_hash"),
        "selection_profile_path": str(selection_path),
        "selection_profile_hash": file_sha256(selection_path),
        "selected_primary_q": primary.get("q"),
        "selected_primary_k": int(primary.get("k")),
        "selected_primary_operationalization_id": f"{primary.get('q')}-K{int(primary.get('k'))}",
        "selected_primary_fold_policy_id": primary.get("fold_policy_id"),
        "diagnostic_operationalizations": [
            {
                "operationalization_id": f"{item.get('q')}-K{int(item.get('k'))}",
                "fold_policy_id": item.get("fold_policy_id"),
            }
            for item in diagnostics
        ],
        "point_ontology_policy": {
            "primary_train_eligible": [
                "REFERENCE",
                "LOW",
                "UNRESOLVED_ENVIRONMENTAL",
            ],
            "outside_primary_train": [
                "POINT_CONTEXT_INCOMPLETE",
                "POINT_NOT_EVALUABLE",
            ],
            "review_status": "REQUIRED_CONFIRMATION",
        },
        "temporal_ontology": {
            "primary_train_eligible": ["TEMPORAL_PERSISTENT_LOW"],
            "outside_primary_train": [
                "TEMPORAL_WINDOW_INELIGIBLE",
                "TEMPORAL_POINT_UNRESOLVED_TRANSFER",
                "TEMPORAL_POINT_CONTEXT_INCOMPLETE_TRANSFER",
            ],
            "review_status": "REQUIRED_CONFIRMATION",
        },
        "support_gate": {
            "policy": "REVIEWER_DECLARED_TASK_THRESHOLDS",
            "task_support": {
                "POINT": _empty_point_gate(),
                "TEMPORAL": _empty_temporal_gate(),
                "SAME_Y": _empty_same_y_gate(),
            },
            "observed_primary_support": observed_support,
        },
        "approved_continuity_contract_id": None,
        "approved_window_contract_id": None,
        "approved_derived_evidence_contract_id": None,
        "resolver_policy": {
            "review_status": "REQUIRED_CONFIRMATION",
            "low_positive": "LOW",
            "low_negative_auxiliary_positive": "UNRESOLVED_ENVIRONMENTAL",
            "low_negative_auxiliary_missing": "POINT_CONTEXT_INCOMPLETE",
            "low_negative_all_required_negative": "REFERENCE",
        },
        "temporal_resolution_policy": {"review_status": "REQUIRED_CONFIRMATION"},
        "same_y_policy": {
            "representation_only": True,
            "target_source": "point_assignment",
            "review_status": "REQUIRED_CONFIRMATION",
        },
        "evidence_role_registry": [],
        "evidence_dependency_registry": [],
        "expected_difference_contract_hash": None,
        "e3_evaluation_claim": "PROTOCOL_LOCKED_TRANSPORT_REEVALUATION",
        "template_status": "NOT_AUTHORITY_REVIEW_REQUIRED",
    }
    output = output_path.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return output


def _empty_point_gate() -> dict[str, Any]:
    return {
        "min_train_class_count": None,
        "min_validation_class_count": None,
        "min_test_class_count": None,
    }


def _empty_temporal_gate() -> dict[str, Any]:
    return {
        "min_train_class_count": None,
        "min_validation_class_count": None,
        "min_test_class_count": None,
        "min_train_event_count": None,
        "min_validation_event_count": None,
        "min_test_event_count": None,
        "min_unique_cluster_count": None,
    }


def _empty_same_y_gate() -> dict[str, Any]:
    return {
        "min_train_class_count": None,
        "min_validation_class_count": None,
        "min_test_class_count": None,
        "min_unique_cluster_count": None,
    }


def _summarize_support(path: Path, primary: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return {"status": "MISSING", "path": str(path)}
    frame = pd.read_parquet(path).convert_dtypes()
    q = str(primary["q"])
    k = int(primary["k"])
    fold = str(primary["fold_policy_id"])
    selected = frame.loc[
        frame["q_contract_id"].astype(str).eq(q)
        & frame["fold_policy_id"].astype(str).eq(fold)
        & (frame["k"].isna() | frame["k"].astype("Int64").eq(k))
    ]
    if selected.empty:
        return {"status": "NO_PRIMARY_ROWS", "path": str(path)}
    result: dict[str, Any] = {"status": "OBSERVED", "path": str(path), "rows": int(len(selected))}
    for (task, split), group in selected.groupby(["task_id", "split_role"], dropna=False):
        key = f"{task}:{split}"
        result[key] = {
            "class_count_min": int(pd.to_numeric(group["class_count"], errors="coerce").min()),
            "event_count_min": int(pd.to_numeric(group["event_count"], errors="coerce").min()),
            "unique_cluster_count_min": int(pd.to_numeric(group["unique_cluster_count"], errors="coerce").min()),
        }
    return result
