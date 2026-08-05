"""Create a human-readable Phase B2 review input without making decisions."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from Backend.Benchmark.common.digests import file_sha256
from Backend.Benchmark.weak_labels.lifecycle.phase_b_contract.candidate_contracts import (
    build_candidate_contract_bundle,
)


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
    candidate_dir = b1_dir / "contracts" / "candidates"
    phase_a_path = manifest.get("phase_a_run_dir")
    if phase_a_path:
        candidate_contracts = build_candidate_contract_bundle(
            Path(str(phase_a_path)), b1_dir, candidate_dir
        )
        candidate_support = yaml.safe_load(
            Path(candidate_contracts["paths"]["support_profiles"]).read_text(encoding="utf-8")
        )
    else:
        # Synthetic/unit-test B1 fixtures may not carry lineage. Keep the
        # template usable, but do not invent candidate contracts.
        candidate_contracts = {"status": "MISSING_PHASE_A_LINEAGE", "paths": {}}
        candidate_support = {}
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
        "candidate_contracts": candidate_contracts,
        "human_review": {
            "selection_profile": "APPROVE_OR_EDIT_PRIMARY_AND_DIAGNOSTIC_QK",
            "semantic_policy_bundle": "APPROVE_OR_REJECT_CANDIDATE_POLICY",
            "support_profile": "APPROVE_OR_EDIT_OBSERVED_SUPPORT_FLOORS",
            "expected_difference_contract": "SUPPLY_PRECOMMITTED_HASH",
        },
        "point_ontology_policy": {
            "candidate_policy_id": "POINT_ONTOLOGY_FULL_CONTEXT_V1",
            "approval": "REQUIRED_CONFIRMATION",
            "source": "candidate_contracts.semantic_policies",
        },
        "temporal_ontology": {
            "candidate_policy_id": "TEMPORAL_ONTOLOGY_PERSISTENCE_V1",
            "approval": "REQUIRED_CONFIRMATION",
            "source": "candidate_contracts.semantic_policies",
        },
        "support_gate": {
            "profile_id": candidate_support.get("profile_id"),
            "approval": "REQUIRED_CONFIRMATION",
            "source": "candidate_contracts.support_profiles",
            "overrides": None,
            "observed_primary_support": observed_support,
        },
        "resolver_policy": {
            "candidate_policy_id": "POINT_RESOLVER_FULL_CONTEXT_V1",
            "approval": "REQUIRED_CONFIRMATION",
            "source": "candidate_contracts.semantic_policies",
        },
        "temporal_resolution_policy": {
            "candidate_policy_id": "TEMPORAL_RESOLVER_PERSISTENCE_V1",
            "approval": "REQUIRED_CONFIRMATION",
            "source": "candidate_contracts.semantic_policies",
        },
        "same_y_policy": {
            "candidate_policy_id": "SAME_Y_TRANSFER_V1",
            "approval": "REQUIRED_CONFIRMATION",
            "source": "candidate_contracts.semantic_policies",
        },
        # The following block is intentionally a compact reference.  The
        # observed numbers remain queryable in the candidate support profile;
        # they are not copied here as reviewer-owned literals.
        "candidate_thresholds": copy.deepcopy(candidate_contracts.get("threshold_candidates", {})),
        "candidate_support_profile": {
            "profile_id": candidate_support.get("profile_id"),
            "path": candidate_contracts.get("paths", {}).get("support_profiles"),
            "authority_status": "CANDIDATE_ONLY",
        },
        "approved_continuity_contract_id": candidate_contracts.get("continuity_contract_id"),
        "approved_window_contract_id": candidate_contracts.get("window_contract_id"),
        "approved_derived_evidence_contract_id": candidate_contracts.get("derived_evidence_contract_id"),
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


def build_phase_b2_review_package(
    b1_decision_pack_dir: Path,
    selection_config_path: Path,
    output_dir: Path,
) -> Path:
    """Create the bounded, human-facing B2 review package.

    The package deliberately has four files at most:
    ``review_decision.yaml`` (human choices), ``selection_profile.yaml``
    (Q/K/fold), ``candidate_inputs.yaml`` (Phase A/B1 references and observed
    values), and ``README.md`` (how the pieces connect). The existing single
    YAML builder remains available as a compatibility API.
    """

    package = output_dir.resolve()
    package.mkdir(parents=True, exist_ok=True)
    full_path = package / ".review_decision_full.yaml"
    build_phase_b2_review_template(b1_decision_pack_dir, selection_config_path, full_path)
    payload = yaml.safe_load(full_path.read_text(encoding="utf-8"))
    selection = yaml.safe_load(Path(selection_config_path).resolve().read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(selection, dict):
        raise ValueError("Generated review package inputs must be YAML mappings.")

    review = dict(payload)
    review["iteration_mode"] = "BASELINE_ITERATION"
    review["decision_status"] = "BASELINE_APPROVED"
    review["approval_source"] = "USER_BASELINE_CONFIGURATION"
    review["expected_difference_contract_hash"] = None
    candidate_contracts = dict(review.get("candidate_contracts", {}))
    candidate_thresholds = review.pop("candidate_thresholds", {})
    support_gate = dict(review.get("support_gate", {}))
    observed_support = support_gate.pop("observed_primary_support", {})
    review["support_gate"] = support_gate
    review["package_layout"] = {
        "candidate_inputs": "candidate_inputs.yaml",
        "selection_profile": "selection_profile.yaml",
        "human_decision": "review_decision.yaml",
    }

    selection_output = package / "selection_profile.yaml"
    selection_payload = dict(selection)
    selection_payload["source_path"] = str(Path(selection_config_path).resolve())
    selection_payload["source_hash"] = file_sha256(Path(selection_config_path).resolve())
    selection_payload["fold_usage"] = {
        "primary": "Use the selected primary fold policy for authority checks.",
        "diagnostics": "Use each diagnostic fold policy only for comparison; do not promote automatically.",
        "boundary_policy": "FIXED; no automatic boundary shift in B2.",
    }
    selection_output.write_text(
        yaml.safe_dump(selection_payload, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )

    candidate_inputs = {
        "source_phase_a": {
            "run_id": candidate_contracts.get("source_phase_a_run_id"),
            "run_dir": candidate_contracts.get("source_phase_a_run_dir"),
            "threshold_registry_hash": candidate_contracts.get("source_threshold_registry_hash"),
        },
        "source_b1": {
            "run_id": candidate_contracts.get("source_b1_run_id"),
            "run_dir": candidate_contracts.get("source_b1_run_dir"),
            "distribution_hash": candidate_contracts.get("source_distribution_hash"),
        },
        "candidate_contract_manifest": {
            "path": candidate_contracts.get("candidate_manifest_path"),
            "sha256": candidate_contracts.get("candidate_manifest_hash"),
        },
        "candidate_contracts": {
            "derived_evidence": candidate_contracts.get("paths", {}).get("derived_evidence"),
            "continuity": candidate_contracts.get("paths", {}).get("continuity"),
            "window": candidate_contracts.get("paths", {}).get("window"),
            "support_profiles": candidate_contracts.get("paths", {}).get("support_profiles"),
            "semantic_policies": candidate_contracts.get("paths", {}).get("semantic_policies"),
        },
        "threshold_candidates": candidate_thresholds,
        "observed_primary_support": observed_support,
        "authority_status": "CANDIDATE_ONLY",
    }
    (package / "candidate_inputs.yaml").write_text(
        yaml.safe_dump(candidate_inputs, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )

    review["selection_profile_path"] = str(selection_output)
    review["selection_profile_hash"] = file_sha256(selection_output)
    (package / "review_decision.yaml").write_text(
        yaml.safe_dump(review, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    (package / "README.md").write_text(
        """# Phase B2 review package

- `review_decision.yaml`: human-owned approval, ontology/resolver choice, support approval, and expected-difference commitment.
- `selection_profile.yaml`: primary and diagnostic Q-K-fold selections and fold-use rules.
- `candidate_inputs.yaml`: generated Phase A/B1 paths, hashes, thresholds, and observed support for inspection.

Candidate contracts remain in the B1 run. B2 reads them by the recorded path/hash and fails closed if they are missing or changed.

The generated package is `BASELINE_ITERATION` for the currently approved first run. Use `support_gate.overrides` only when a deliberate deviation from the observed recommendation is required. A later reviewed/differential run can change the mode to `REVIEWED_FREEZE` and provide explicit approvals.
""",
        encoding="utf-8",
    )
    full_path.unlink(missing_ok=True)
    return package


def _summarize_support(path: Path, primary: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return {"status": "MISSING", "path": str(path)}
    frame = pd.read_parquet(path).convert_dtypes()
    q = str(primary["q"])
    k = int(primary["k"])
    fold = str(primary["fold_policy_id"])
    mask = (
        frame["q_contract_id"].astype(str).eq(q)
        & frame["fold_policy_id"].astype(str).eq(fold)
    )
    if "k" in frame.columns:
        task_names = frame["task_id"].astype(str).str.upper()
        mask &= (
            (task_names.eq("POINT") & frame["k"].isna())
            | (~task_names.eq("POINT") & frame["k"].astype("Int64").eq(k))
        )
    selected = frame.loc[mask]
    if selected.empty:
        return {"status": "NO_PRIMARY_ROWS", "path": str(path)}
    result: dict[str, Any] = {"status": "OBSERVED", "path": str(path), "rows": int(len(selected))}
    for (task, split), group in selected.groupby(["task_id", "split_role"], dropna=False):
        task_name = str(task).upper()
        if task_name == "POINT":
            group = group.loc[group["class_label"].astype(str).isin(
                ["REFERENCE", "LOW", "UNRESOLVED_ENVIRONMENTAL"]
            )]
        elif task_name == "TEMPORAL":
            group = group.loc[group["class_label"].astype(str).eq("TEMPORAL_PERSISTENT_LOW")]
        elif task_name == "SAME_Y":
            group = group.loc[group["class_label"].astype(str).eq("ELIGIBLE")]
        if group.empty:
            continue
        key = f"{task}:{split}"
        result[key] = {
            "class_count_min": int(pd.to_numeric(group["class_count"], errors="coerce").min()),
            "event_count_min": int(pd.to_numeric(group["event_count"], errors="coerce").min()),
            "unique_cluster_count_min": int(pd.to_numeric(group["unique_cluster_count"], errors="coerce").min()),
        }
    return result
