from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from Backend.Benchmark.common.digests import file_sha256, stable_digest
from Backend.Benchmark.protocol_registry import load_protocol_registry
from Backend.Benchmark.shared.artifacts import write_json, write_yaml
from Backend.Benchmark.weak_labels.contracts.native import NativeContract
from Backend.Benchmark.weak_labels.lifecycle.phase_b_contract.contracts import (
    PhaseB2Config,
    PhaseB2Error,
    PhaseB2Result,
)


_Q_PATTERN = re.compile(r"LOW_MOISTURE_(Q\d+)_")


def freeze_phase_b_contract(config: PhaseB2Config) -> PhaseB2Result:
    """Validate reviewed B1 evidence and atomically publish a Phase B2 contract."""

    output_root = config.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    run_id = _allocate_run_id(output_root)
    staging = output_root / ".staging" / run_id
    staging.mkdir(parents=True, exist_ok=False)
    try:
        inputs = _preflight(config)
        _write_contract(staging, config, inputs, run_id)
        _validate_published_contract(staging)
        final_dir = output_root / run_id
        os.replace(staging, final_dir)
        _reverify_and_mark(final_dir)
        from Backend.Benchmark.weak_labels.lifecycle.phase_b_contract.pipeline import (
            build_frozen_protocol_registry,
        )

        frozen_registry = build_frozen_protocol_registry(
            config.protocol_registry_run_dir.resolve(), final_dir
        )
        return PhaseB2Result(run_id, final_dir, "CONTRACT_FROZEN", frozen_registry)
    except PhaseB2Error as exc:
        _write_blocked(staging, run_id, str(exc))
        return PhaseB2Result(run_id, None, "CONTRACT_FREEZE_BLOCKED", reason=str(exc))
    except (FileNotFoundError, KeyError, ValueError, yaml.YAMLError) as exc:
        _write_blocked(staging, run_id, str(exc))
        return PhaseB2Result(run_id, None, "CONTRACT_FREEZE_BLOCKED", reason=str(exc))
    except Exception:
        _write_blocked(staging, run_id, "UNEXPECTED_B2_FAILURE")
        raise


def load_frozen_semantic_contract(contract_run_dir: Path) -> NativeContract:
    """Load and validate a published Phase B2 contract."""

    return NativeContract.load(contract_run_dir.resolve())


def freeze_semantic_contract(config: PhaseB2Config) -> PhaseB2Result:
    """Compatibility alias for the canonical Phase B2 freeze API."""

    return freeze_phase_b_contract(config)


def _preflight(config: PhaseB2Config) -> dict[str, Any]:
    phase_a = config.phase_a_run_dir.resolve()
    b1 = config.phase_b1_decision_pack_dir.resolve()
    registry = load_protocol_registry(config.protocol_registry_run_dir.resolve())
    if not bool(registry.run_manifest.get("phase_a_only", False)):
        raise PhaseB2Error("B2 requires the Phase A parent protocol registry.")

    phase_a_manifest = _read_json(phase_a / "run_metadata" / "run_manifest.json")
    readiness = _read_yaml(phase_a / "phase_a_readiness.yaml")
    readiness_payload = readiness.get("phase_a_readiness", readiness)
    if readiness_payload.get("overall_status") != "PASS":
        raise PhaseB2Error("Phase A readiness is not PASS.")

    b1_manifest = _read_json(b1 / "run_metadata" / "run_manifest.json")
    if b1_manifest.get("phase") != "PHASE_B1_DECISION_PACK":
        raise PhaseB2Error("The supplied B1 directory is not a decision pack.")
    if b1_manifest.get("primary_selection_status") != "REVIEW_REQUIRED":
        raise PhaseB2Error("B1 selection status is not REVIEW_REQUIRED.")
    if b1_manifest.get("labels_materialized") is not False:
        raise PhaseB2Error("B1 must not contain materialized labels.")

    decision = _read_yaml(config.review_decision_path.resolve())
    decision = _expand_candidate_review_decision(decision, config)
    _validate_review_decision(decision, b1_manifest, config.expected_difference_contract_path)
    selection = _load_selection(config.selection_config_path, decision)
    declared_selection_hash = decision.get("selection_profile_hash")
    if not declared_selection_hash:
        raise PhaseB2Error("Review decision must record selection_profile_hash.")
    actual_selection_hash = file_sha256(config.selection_config_path.resolve())
    if str(declared_selection_hash) != actual_selection_hash:
        raise PhaseB2Error("Selection profile hash mismatch.")

    required_b1 = {
        "geometry": b1 / "operationalization" / "qk_geometry.parquet",
        "fold_support": b1 / "operationalization" / "qk_fold_support.csv",
        "matrix": b1 / "resolution" / "point_compatibility_matrix.csv",
    }
    for name, path in required_b1.items():
        if not path.exists():
            raise PhaseB2Error(f"B1 artifact is missing: {name} ({path})")
    geometry = pd.read_parquet(required_b1["geometry"])
    fold_support = pd.read_csv(required_b1["fold_support"])
    matrix = pd.read_csv(required_b1["matrix"])
    if len(matrix) != 81:
        raise PhaseB2Error(f"B1 compatibility matrix must contain 81 rows; got {len(matrix)}.")

    threshold_registry = pd.read_csv(
        phase_a / "threshold_diagnostics" / "threshold_registry.csv"
    ).convert_dtypes()
    q_values = _load_q_values(threshold_registry)
    selected_q = str(decision["selected_primary_q"])
    selected_k = int(decision["selected_primary_k"])
    if selected_q != selection["primary"]["q"] or selected_k != int(selection["primary"]["k"]):
        raise PhaseB2Error("Selection profile primary Q×K does not match review decision.")
    if selected_q not in q_values:
        raise PhaseB2Error(f"Selected Q is absent from Phase A threshold registry: {selected_q}")
    selected_rows = geometry.loc[
        geometry["q_contract_id"].astype(str).eq(selected_q)
        & geometry["k"].astype("Int64").eq(selected_k)
    ]
    if selected_rows.empty:
        raise PhaseB2Error("Selected Q×K is absent from B1 geometry.")
    if not (
        fold_support.get("q_contract_id", pd.Series(dtype=object)).astype(str).eq(selected_q)
        & fold_support.get("k", pd.Series(dtype=object)).astype("Int64").eq(selected_k)
        & fold_support.get("fold_policy_id", pd.Series(dtype=object)).astype(str).eq(selection["primary"]["fold_policy_id"])
    ).any():
        raise PhaseB2Error("Selected Q×K×primary-fold is absent from B1 fold support.")

    _validate_candidate_selection(geometry, fold_support, selection)

    anchor = _read_table(config.anchor_safety_audit_path)
    distribution = _read_table(config.distribution_audit_path)
    _validate_anchor_safety(anchor, selected_q, selected_k, selection["primary"]["fold_policy_id"])
    _validate_distribution_task_specific(
        distribution,
        decision,
        selected_q,
        selected_k,
        selection["primary"]["fold_policy_id"],
    )

    derived = _read_table(config.derived_evidence_contract_path)
    _validate_derived_contract(derived)
    continuity = _read_contract_mapping(config.continuity_contract_path)
    window = _read_contract_mapping(config.window_contract_path)
    _validate_continuity(continuity)
    _validate_window(window)
    _validate_approved_contract_ids(decision, continuity, window, derived)

    return {
        "registry": registry,
        "phase_a_manifest": phase_a_manifest,
        "b1_manifest": b1_manifest,
        "decision": decision,
        "geometry": geometry,
        "matrix": matrix,
        "threshold_registry": threshold_registry,
        "q_values": q_values,
        "derived": derived,
        "continuity": continuity,
        "window": window,
        "selected_q": selected_q,
        "selected_k": selected_k,
        "selection": selection,
        "anchor_hash": file_sha256(config.anchor_safety_audit_path.resolve()),
        "distribution_hash": file_sha256(config.distribution_audit_path.resolve()),
    }


def _expand_candidate_review_decision(
    decision: dict[str, Any], config: PhaseB2Config
) -> dict[str, Any]:
    """Resolve compact review references into the candidate values they name.

    The review YAML is intentionally small: Phase A/B1 own measured values and
    candidate policies, while the reviewer approves or rejects those candidates.
    B2 expands the references in memory and freezes the expanded values; it
    never invents a fallback when the referenced artifact is missing.
    """

    expanded = dict(decision)
    candidates = expanded.get("candidate_contracts")
    if not isinstance(candidates, dict):
        return expanded

    paths = candidates.get("paths")
    if not isinstance(paths, dict):
        return expanded

    # Accept an already-expanded decision from the migration period. New
    # templates use references; older reviewed files may already contain the
    # resolved policy bodies and task thresholds.
    if (
        isinstance(expanded.get("support_gate"), dict)
        and isinstance(expanded["support_gate"].get("task_support"), dict)
        and isinstance(expanded.get("point_ontology_policy"), dict)
        and "primary_train_eligible" in expanded["point_ontology_policy"]
    ):
        return expanded

    candidate_manifest_path = Path(str(candidates.get("candidate_manifest_path", ""))).resolve()
    if candidate_manifest_path.exists():
        declared_manifest_hash = candidates.get("candidate_manifest_hash")
        if declared_manifest_hash and str(declared_manifest_hash) != file_sha256(candidate_manifest_path):
            raise PhaseB2Error("Candidate contract manifest hash mismatch.")
        candidate_manifest = _read_yaml(candidate_manifest_path)
        if candidate_manifest.get("source_b1_run_id") != config.phase_b1_decision_pack_dir.resolve().name:
            raise PhaseB2Error("Candidate contracts do not belong to the supplied B1 decision pack.")
        if candidate_manifest.get("source_phase_a_run_id"):
            phase_a_manifest = _read_json(config.phase_a_run_dir.resolve() / "run_metadata" / "run_manifest.json")
            if candidate_manifest["source_phase_a_run_id"] != phase_a_manifest.get("run_id"):
                raise PhaseB2Error("Candidate contracts do not belong to the supplied Phase A run.")

    semantic_path = Path(str(paths.get("semantic_policies", ""))).resolve()
    support_path = Path(str(paths.get("support_profiles", ""))).resolve()
    if not semantic_path.exists() or not support_path.exists():
        raise PhaseB2Error("Compact review references missing candidate contract artifacts.")

    semantic = _read_yaml(semantic_path)
    support = _read_yaml(support_path)
    if not isinstance(semantic, dict) or semantic.get("authority_status") != "CANDIDATE_ONLY":
        raise PhaseB2Error("Semantic candidate bundle is not a candidate-only artifact.")
    if not isinstance(support, dict) or support.get("authority_status") != "CANDIDATE_ONLY":
        raise PhaseB2Error("Support candidate bundle is not a candidate-only artifact.")

    # A compact policy reference must be explicitly approved; otherwise a
    # reviewer could accidentally freeze a candidate by omission.
    baseline_mode = str(expanded.get("iteration_mode", "")) == "BASELINE_ITERATION"
    policy_map = {
        "point_ontology_policy": ("point_ontology_policy_id", "point_ontology_policy"),
        "temporal_ontology": ("temporal_ontology_policy_id", "temporal_ontology"),
        "resolver_policy": ("resolver_policy_id", "resolver_policy"),
        "temporal_resolution_policy": ("temporal_resolution_policy_id", "temporal_resolution_policy"),
        "same_y_policy": ("same_y_policy_id", "same_y_policy"),
    }
    for field, (id_field, body_field) in policy_map.items():
        current = expanded.get(field)
        if not isinstance(current, dict):
            raise PhaseB2Error(f"Compact review is missing {field}.")
        if current.get("approval") != "APPROVE_CANDIDATE" and not (
            baseline_mode and current.get("approval") == "REQUIRED_CONFIRMATION"
        ):
            raise PhaseB2Error(f"Reviewer must explicitly approve candidate {field}.")
        policy_id = current.get("candidate_policy_id")
        if policy_id != semantic.get(id_field):
            raise PhaseB2Error(f"{field} references an unknown candidate policy.")
        body = semantic.get(body_field)
        if not isinstance(body, dict):
            raise PhaseB2Error(f"Candidate semantic policy body is missing: {body_field}.")
        expanded[field] = {
            **body,
            "policy_id": policy_id,
            "approval": "APPROVE_CANDIDATE" if baseline_mode else current["approval"],
        }

    support_gate = expanded.get("support_gate")
    if not isinstance(support_gate, dict):
        raise PhaseB2Error("Compact review is missing support_gate.")
    if support_gate.get("approval") != "APPROVE_CANDIDATE" and not (
        baseline_mode and support_gate.get("approval") == "REQUIRED_CONFIRMATION"
    ):
        raise PhaseB2Error("Reviewer must explicitly approve the candidate support profile.")
    if support_gate.get("profile_id") != support.get("profile_id"):
        raise PhaseB2Error("Support profile reference does not match its candidate artifact.")
    observed = support.get("support")
    if not isinstance(observed, dict):
        raise PhaseB2Error("Support candidate artifact has no support measurements.")
    task_support = _support_thresholds_from_candidate(observed)
    overrides = support_gate.get("overrides")
    if overrides is not None:
        if not isinstance(overrides, dict):
            raise PhaseB2Error("Support-gate overrides must be a task mapping or null.")
        for task_name, values in overrides.items():
            if task_name not in task_support or not isinstance(values, dict):
                raise PhaseB2Error(f"Unsupported support-gate override task: {task_name}")
            for field, value in values.items():
                if field not in task_support[task_name] or isinstance(value, bool):
                    raise PhaseB2Error(f"Unsupported support-gate override: {task_name}.{field}")
                try:
                    numeric = int(value)
                except (TypeError, ValueError) as exc:
                    raise PhaseB2Error(f"Support-gate override must be numeric: {task_name}.{field}") from exc
                if numeric < 0:
                    raise PhaseB2Error(f"Support-gate override must be non-negative: {task_name}.{field}")
                task_support[task_name][field] = numeric
    expanded["support_gate"] = {
        "policy": "REVIEWER_APPROVED_B1_CANDIDATE_PROFILE",
        "profile_id": support_gate["profile_id"],
        "task_support": task_support,
        "observed_primary_support": support_gate.get("observed_primary_support", {}),
    }
    return expanded


def _support_thresholds_from_candidate(support: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Translate B1's observed candidate floors to the internal B2 gate shape."""

    point = support.get("POINT", {})
    temporal = support.get("TEMPORAL", {})
    same_y = support.get("SAME_Y", {})
    try:
        point_floor = int(point["recommended_floor"])
        temporal_class = int(temporal["recommended_floor_class_count"])
        temporal_event = int(temporal["recommended_floor_event_count"])
        temporal_cluster = int(temporal["recommended_floor_cluster_count"])
        same_y_class = int(same_y["recommended_floor_class_count"])
        same_y_cluster = int(same_y["recommended_floor_cluster_count"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PhaseB2Error("Candidate support profile lacks recommended floors.") from exc
    return {
        "POINT": {
            "min_train_class_count": point_floor,
            "min_validation_class_count": point_floor,
            "min_test_class_count": point_floor,
        },
        "TEMPORAL": {
            "min_train_class_count": temporal_class,
            "min_validation_class_count": temporal_class,
            "min_test_class_count": temporal_class,
            "min_train_event_count": temporal_event,
            "min_validation_event_count": temporal_event,
            "min_test_event_count": temporal_event,
            "min_unique_cluster_count": temporal_cluster,
        },
        "SAME_Y": {
            "min_train_class_count": same_y_class,
            "min_validation_class_count": same_y_class,
            "min_test_class_count": same_y_class,
            "min_unique_cluster_count": same_y_cluster,
        },
    }


def _write_contract(staging: Path, config: PhaseB2Config, inputs: dict[str, Any], run_id: str) -> None:
    for directory in (
        "ontology",
        "evidence",
        "thresholds",
        "continuity",
        "operationalization",
        "resolution",
        "compatibility",
        "provenance",
        "run_metadata",
    ):
        (staging / directory).mkdir(parents=True, exist_ok=True)

    decision = inputs["decision"]
    selected_q = inputs["selected_q"]
    selected_k = inputs["selected_k"]
    selection = inputs["selection"]
    q_values = inputs["q_values"]
    decision_hash = file_sha256(config.review_decision_path.resolve())
    input_hashes = {
        "phase_a_readiness": file_sha256(config.phase_a_run_dir.resolve() / "phase_a_readiness.yaml"),
        "phase_a_threshold_registry": file_sha256(config.phase_a_run_dir.resolve() / "threshold_diagnostics" / "threshold_registry.csv"),
        "b1_decision_pack": str(inputs["b1_manifest"]["decision_pack_hash"]),
        "anchor_safety": inputs["anchor_hash"],
        "distribution": inputs["distribution_hash"],
        "derived_evidence": file_sha256(config.derived_evidence_contract_path.resolve()),
        "continuity": file_sha256(config.continuity_contract_path.resolve()),
        "window": file_sha256(config.window_contract_path.resolve()),
        "expected_difference": (
            file_sha256(config.expected_difference_contract_path.resolve())
            if config.expected_difference_contract_path is not None
            and config.expected_difference_contract_path.resolve().exists()
            else None
        ),
        "review_decision": decision_hash,
    }
    if config.selection_config_path is not None:
        input_hashes["selection_config"] = file_sha256(config.selection_config_path.resolve())
    semantic_payload = {
        "schema_version": "phase_b2.semantic_contract.v1",
        "selected_primary_q": selected_q,
        "selected_primary_q_value": q_values[selected_q],
        "selected_primary_k": selected_k,
        "ontology_policy": decision["point_ontology_policy"],
        "resolver_policy": decision["resolver_policy"],
        "temporal_resolution_policy": decision["temporal_resolution_policy"],
        "same_y_policy": decision["same_y_policy"],
        "selection": selection,
        "input_hashes": input_hashes,
    }
    semantic_hash = stable_digest(semantic_payload)
    semantic_id = f"SEMANTIC_CONTRACT_{semantic_hash[:16]}"
    freeze_timestamp = datetime.now(timezone.utc).isoformat()

    threshold_registry = inputs["threshold_registry"].copy()
    threshold_registry["contract_freeze_id"] = semantic_id
    threshold_registry["authority_status"] = threshold_registry["threshold_id"].astype(str).map(
        lambda value: "PRIMARY_INTERNAL_AUTHORITY" if value.endswith(f"{selected_q}_E1_DISCOVERY_CANDIDATE") else "RQ1_DIAGNOSTIC_ONLY"
    )
    threshold_registry.to_csv(staging / "thresholds" / "frozen_threshold_registry.csv", index=False)

    q_rows = []
    for q_id, value in q_values.items():
        q_rows.append({
            "q_contract_id": q_id,
            "threshold_value": value,
            "authority_status": "PRIMARY_INTERNAL_AUTHORITY" if q_id == selected_q else "RQ1_DIAGNOSTIC_ONLY",
        })
    pd.DataFrame(q_rows).to_csv(staging / "operationalization" / "q_operationalization_registry.csv", index=False)

    geometry = inputs["geometry"]
    selected_specs = [selection["primary"], *selection["diagnostics"]]
    op_rows = []
    for spec in selected_specs:
        q_id = str(spec["q"])
        k = int(spec["k"])
        fold_policy_id = str(spec["fold_policy_id"])
        op_rows.append({
            "operationalization_id": f"{q_id}-K{k}",
            "q_contract_id": q_id,
            "persistence_contract_id": f"K_{k}",
            "selected_k": k,
            "fold_policy_id": fold_policy_id,
            "selection_role": "PRIMARY" if spec is selection["primary"] else "DIAGNOSTIC",
            "authority_status": "PRIMARY_INTERNAL_AUTHORITY" if spec is selection["primary"] else "RQ1_DIAGNOSTIC_ONLY",
        })
    pd.DataFrame(op_rows).to_csv(staging / "operationalization" / "operationalization_registry.csv", index=False)
    k_rows = [{"contract_id": f"K_{k}", "selected_k": k, "semantics": "OBSERVATION_COUNT", "elapsed_time_audit_only": True} for k in sorted({int(v) for v in geometry["k"].dropna()})]
    pd.DataFrame(k_rows).to_csv(staging / "operationalization" / "persistence_operationalization_registry.csv", index=False)

    inputs["matrix"].to_csv(staging / "resolution" / "point_compatibility_matrix.csv", index=False)
    _write_yaml(staging / "resolution" / "point_resolution_contract.yaml", decision["resolver_policy"])
    _write_yaml(staging / "resolution" / "temporal_resolution_contract.yaml", decision["temporal_resolution_policy"])
    _write_yaml(staging / "continuity" / "window_continuity_contract.yaml", inputs["window"])
    _write_yaml(staging / "continuity" / "strict_continuity_contract.yaml", inputs["continuity"]["strict_continuity"])
    _write_yaml(staging / "continuity" / "deployment_continuity_contract.yaml", inputs["continuity"]["deployment_continuity"])
    inputs["derived"].to_csv(staging / "evidence" / "derived_evidence_contract_registry.csv", index=False)
    pd.DataFrame(decision["evidence_role_registry"]).to_csv(staging / "evidence" / "evidence_role_registry.csv", index=False)
    pd.DataFrame(decision["evidence_dependency_registry"]).to_csv(staging / "evidence" / "evidence_dependency_registry.csv", index=False)

    _write_yaml(staging / "ontology" / "point_ontology.yaml", {
        "classes": ["REFERENCE", "LOW", "UNRESOLVED_ENVIRONMENTAL"],
        "primary_train_eligible": ["REFERENCE", "LOW", "UNRESOLVED_ENVIRONMENTAL"],
        "outside_primary_train": ["POINT_CONTEXT_INCOMPLETE", "POINT_NOT_EVALUABLE"],
        "policy": decision["point_ontology_policy"],
    })
    _write_yaml(staging / "ontology" / "temporal_anchor_ontology.yaml", decision["temporal_ontology"])
    _write_yaml(staging / "ontology" / "same_y_contract.yaml", decision["same_y_policy"])
    if config.expected_difference_contract_path is not None and config.expected_difference_contract_path.resolve().exists():
        shutil.copy2(
            config.expected_difference_contract_path.resolve(),
            staging / "compatibility" / "expected_difference_contract.csv",
        )

    commitment = _build_freeze_commitment(config.canonical_history_path.resolve())
    commitment.to_parquet(staging / "provenance" / "freeze_record_commitment.parquet", index=False)
    commitment_hash = stable_digest(commitment.to_dict("records"))
    write_json(staging / "provenance" / "freeze_activity.json", {
        "freeze_timestamp_utc": freeze_timestamp,
        "freeze_record_count": int(len(commitment)),
        "freeze_record_set_hash": commitment_hash,
        "review_decision_id": decision["decision_id"],
        "review_decision_hash": decision_hash,
    })
    manifest = {
        "pipeline": "weak_labels_semantic_contract",
        "run_id": run_id,
        "phase": "PHASE_B2_CONTRACT_FROZEN",
        "semantic_contract_id": semantic_id,
        "semantic_contract_hash": semantic_hash,
        "semantic_contract_frozen": True,
        "native_engine_implemented": False,
        "downstream_runners_unlocked": False,
        "labels_materialized": False,
        "model_training_performed": False,
        "current_stage": "CONTRACT_FROZEN",
        "selection_profile_id": selection["profile_id"],
        "primary_operationalization_id": f"{selected_q}-K{selected_k}",
        "primary_fold_policy_id": selection["primary"]["fold_policy_id"],
        "diagnostic_operationalizations": [
            {"operationalization_id": f"{item['q']}-K{int(item['k'])}", "fold_policy_id": item["fold_policy_id"]}
            for item in selection["diagnostics"]
        ],
        "primary_q": selected_q,
        "primary_k": selected_k,
        "decision_pack_hash": inputs["b1_manifest"]["decision_pack_hash"],
        "anchor_safety_audit_hash": inputs["anchor_hash"],
        "distribution_audit_hash": inputs["distribution_hash"],
        "expected_difference_contract_hash": (
            file_sha256(config.expected_difference_contract_path.resolve())
            if config.expected_difference_contract_path is not None
            and config.expected_difference_contract_path.resolve().exists()
            else None
        ),
        "freeze_timestamp_utc": freeze_timestamp,
        "parent_protocol_registry_contract_hash": inputs["registry"].run_manifest["registry_contract_hash"],
        "input_hashes": input_hashes,
    }
    write_json(staging / "run_metadata" / "run_manifest.json", manifest)
    write_yaml(staging / "phase_b_freeze.yaml", {
        "overall_status": "PASS",
        "semantic_contract_id": semantic_id,
        "semantic_contract_hash": semantic_hash,
        "selection_profile_id": selection["profile_id"],
        "primary_operationalization_id": f"{selected_q}-K{selected_k}",
        "primary_fold_policy_id": selection["primary"]["fold_policy_id"],
        "diagnostic_operationalizations": [
            {"operationalization_id": f"{item['q']}-K{int(item['k'])}", "fold_policy_id": item["fold_policy_id"]}
            for item in selection["diagnostics"]
        ],
        "e3_claim": decision.get("e3_evaluation_claim", "PROTOCOL_LOCKED_TRANSPORT_REEVALUATION"),
        "e4_materialized": False,
    })
    _write_b2_artifact_catalog(staging)


def _validate_published_contract(path: Path) -> None:
    NativeContract.load(path)


def _reverify_and_mark(final_dir: Path) -> None:
    manifest_path = final_dir / "run_metadata" / "run_manifest.json"
    manifest = _read_json(manifest_path)
    catalog = _write_b2_artifact_catalog(final_dir)
    write_json(final_dir / "run_metadata" / "publication_success_marker.json", {
        "publication_status": "SUCCESS",
        "run_id": final_dir.name,
        "manifest_hash": file_sha256(manifest_path),
        "artifact_count": int(len(catalog)),
        "semantic_contract_hash": manifest["semantic_contract_hash"],
    })


def _write_blocked(staging: Path, run_id: str, reason: str) -> None:
    staging.mkdir(parents=True, exist_ok=True)
    write_yaml(staging / "phase_b2_status.yaml", {
        "overall_status": "CONTRACT_FREEZE_BLOCKED",
        "run_id": run_id,
        "reason": reason,
        "labels_materialized": False,
        "model_training_performed": False,
        "downstream_runners_unlocked": False,
    })


def _write_b2_artifact_catalog(run_dir: Path) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file() or path.name == "artifact_catalog.csv":
            continue
        rows.append({
            "artifact_path": str(path.relative_to(run_dir)).replace("\\", "/"),
            "sha256": file_sha256(path),
            "size_bytes": path.stat().st_size,
        })
    catalog = pd.DataFrame(rows).convert_dtypes()
    target = run_dir / "run_metadata" / "artifact_catalog.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    catalog.to_csv(target, index=False)
    return catalog


def _validate_review_decision(
    decision: dict[str, Any], b1_manifest: dict[str, Any], expected_path: Path | None
) -> None:
    required = {
        "decision_status", "decision_id", "reviewer_ids", "reviewed_at_utc",
        "reviewed_decision_pack_hash", "selected_primary_q", "selected_primary_k",
        "selected_primary_operationalization_id", "point_ontology_policy", "support_gate",
        "approved_continuity_contract_id", "approved_window_contract_id",
        "approved_derived_evidence_contract_id", "resolver_policy",
        "temporal_resolution_policy", "temporal_ontology", "same_y_policy",
        "evidence_role_registry", "evidence_dependency_registry",
        "expected_difference_contract_hash", "e3_evaluation_claim",
    }
    missing = sorted(required - set(decision))
    if missing:
        raise PhaseB2Error(f"Review decision is missing required fields: {missing}")
    iteration_mode = str(decision.get("iteration_mode", "REVIEWED_FREEZE"))
    if iteration_mode == "BASELINE_ITERATION":
        if decision["decision_status"] not in {"BASELINE_APPROVED", "APPROVED"}:
            raise PhaseB2Error(
                "BASELINE_ITERATION requires decision_status=BASELINE_APPROVED or APPROVED."
            )
    elif decision["decision_status"] != "APPROVED":
        raise PhaseB2Error("B2 requires decision_status=APPROVED.")
    if str(decision["reviewed_decision_pack_hash"]) != str(b1_manifest.get("decision_pack_hash")):
        raise PhaseB2Error("Review decision hash does not match B1 decision pack.")
    expected_op = f"{decision['selected_primary_q']}-K{int(decision['selected_primary_k'])}"
    if str(decision["selected_primary_operationalization_id"]) != expected_op:
        raise PhaseB2Error("selected_primary_operationalization_id does not match selected Q×K.")
    declared = decision.get("expected_difference_contract_hash")
    if expected_path is None or not expected_path.resolve().exists():
        if iteration_mode != "BASELINE_ITERATION" or declared not in (None, ""):
            raise PhaseB2Error("Expected-difference contract is required for this B2 mode.")
    else:
        expected_hash = file_sha256(expected_path.resolve())
        if str(declared) != expected_hash:
            raise PhaseB2Error("Expected-difference contract hash mismatch.")
    gate = decision["support_gate"]
    if not isinstance(gate, dict) or not isinstance(gate.get("task_support"), dict):
        raise PhaseB2Error("Support gate must declare task-specific reviewer-owned thresholds.")
    _validate_task_support_gate(gate["task_support"])
    for name in ("point_ontology_policy", "temporal_ontology"):
        policy = decision[name]
        if not isinstance(policy, dict) or not policy.get("primary_train_eligible"):
            raise PhaseB2Error(f"{name} must declare primary_train_eligible classes.")
        if not isinstance(policy.get("outside_primary_train"), list):
            raise PhaseB2Error(f"{name} must declare outside_primary_train classes.")


def _validate_task_support_gate(task_support: dict[str, Any]) -> None:
    required_tasks = {"POINT", "TEMPORAL", "SAME_Y"}
    if set(task_support) != required_tasks:
        raise PhaseB2Error(
            f"Support gate must declare exactly POINT, TEMPORAL and SAME_Y; got {sorted(task_support)}."
        )
    required_by_task = {
        "POINT": {"min_train_class_count", "min_validation_class_count", "min_test_class_count"},
        "TEMPORAL": {
            "min_train_class_count", "min_validation_class_count", "min_test_class_count",
            "min_train_event_count", "min_validation_event_count", "min_test_event_count",
            "min_unique_cluster_count",
        },
        "SAME_Y": {
            "min_train_class_count", "min_validation_class_count", "min_test_class_count",
            "min_unique_cluster_count",
        },
    }
    for task, required in required_by_task.items():
        gate = task_support[task]
        if not isinstance(gate, dict) or not required.issubset(gate):
            raise PhaseB2Error(f"Support gate is incomplete for {task}: {sorted(required - set(gate or {}))}")
        for name in required:
            value = gate[name]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) < 0:
                raise PhaseB2Error(f"Support threshold {task}.{name} must be a non-negative number.")


def _load_selection(path: Path, decision: dict[str, Any]) -> dict[str, Any]:
    """Load one explicit Q×K×fold profile for this B2 run.

    A profile is deliberately a small, reviewable YAML. It does not contain
    semantic policy; it only selects which candidate geometry is primary and
    which candidates are retained as diagnostics. This makes repeated thesis
    or reviewer runs reproducible without changing engine code.
    """
    if path is None:
        raise PhaseB2Error("B2 requires a separate selection profile YAML.")
    payload = _read_yaml(path.resolve())
    if not isinstance(payload, dict):
        raise PhaseB2Error("B2 requires an explicit selection profile YAML or review_decision.selection.")
    primary = payload.get("primary")
    diagnostics = payload.get("diagnostics")
    profile_id = str(payload.get("profile_id", ""))
    if not profile_id:
        raise PhaseB2Error("Selection profile must declare profile_id.")
    if not isinstance(primary, dict) or not isinstance(diagnostics, list):
        raise PhaseB2Error("Selection profile must contain primary mapping and diagnostics list.")
    normalized_primary = _normalize_selection_item(primary, "primary")
    normalized_diagnostics = [_normalize_selection_item(item, f"diagnostic[{idx}]") for idx, item in enumerate(diagnostics)]
    keys = {(item["q"], int(item["k"])) for item in [normalized_primary, *normalized_diagnostics]}
    if len(keys) != len(normalized_diagnostics) + 1:
        raise PhaseB2Error("Selection profile contains duplicate Q×K operationalizations.")
    if any(item["q"] == normalized_primary["q"] and int(item["k"]) == int(normalized_primary["k"]) for item in normalized_diagnostics):
        raise PhaseB2Error("Primary Q×K must not also be listed as diagnostic.")
    return {"profile_id": profile_id, "primary": normalized_primary, "diagnostics": normalized_diagnostics}


def _normalize_selection_item(item: Any, label: str) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise PhaseB2Error(f"Selection {label} must be a mapping.")
    required = {"q", "k", "fold_policy_id"}
    missing = sorted(required - set(item))
    if missing:
        raise PhaseB2Error(f"Selection {label} is missing: {missing}")
    q = str(item["q"])
    if q not in {"Q05", "Q10", "Q15", "Q20"}:
        raise PhaseB2Error(f"Selection {label} has unsupported Q: {q}")
    try:
        k = int(item["k"])
    except (TypeError, ValueError) as exc:
        raise PhaseB2Error(f"Selection {label} has invalid K: {item['k']!r}") from exc
    if k < 1:
        raise PhaseB2Error(f"Selection {label} requires K >= 1.")
    fold_policy_id = str(item["fold_policy_id"])
    if not fold_policy_id:
        raise PhaseB2Error(f"Selection {label} requires fold_policy_id.")
    return {"q": q, "k": k, "fold_policy_id": fold_policy_id}


def _validate_candidate_selection(geometry: pd.DataFrame, fold_support: pd.DataFrame, selection: dict[str, Any]) -> None:
    """Ensure every selected primary/diagnostic item exists in B1 evidence."""
    for role, item in [("primary", selection["primary"]), *[("diagnostic", value) for value in selection["diagnostics"]]]:
        q = item["q"]
        k = int(item["k"])
        geometry_rows = geometry.loc[
            geometry["q_contract_id"].astype(str).eq(q)
            & geometry["k"].astype("Int64").eq(k)
        ]
        if geometry_rows.empty:
            raise PhaseB2Error(f"Selected {role} Q×K is absent from B1 geometry: {q}-K{k}.")
        support_rows = fold_support.loc[
            fold_support["q_contract_id"].astype(str).eq(q)
            & fold_support["k"].astype("Int64").eq(k)
            & fold_support["fold_policy_id"].astype(str).eq(item["fold_policy_id"])
        ]
        if support_rows.empty:
            raise PhaseB2Error(f"Selected {role} Q×K×fold is absent from B1 fold support: {q}-K{k}/{item['fold_policy_id']}.")


def _validate_anchor_safety(frame: pd.DataFrame, selected_q: str, selected_k: int, fold_policy_id: str | None = None) -> None:
    required = {
        "q_contract_id", "k", "fold_policy_id", "fold_id", "split_role",
        "unique_anchor_count", "dependency_admissible_anchor_count",
        "purge_excluded_count", "boundary_excluded_count",
        "cross_split_anchor_count", "cross_deployment_anchor_count",
        "semantic_cross_split_anchor_count", "semantic_cross_deployment_anchor_count",
        "semantic_admissible_anchor_count", "evaluation_admissible_anchor_count",
        "purge_applied",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise PhaseB2Error(f"Anchor safety audit is incomplete: {missing}")
    selected = frame.loc[frame["q_contract_id"].astype(str).eq(selected_q) & frame["k"].astype("Int64").eq(selected_k)]
    if fold_policy_id is not None and "fold_policy_id" in frame.columns:
        selected = selected.loc[selected["fold_policy_id"].astype(str).eq(fold_policy_id)]
    if selected.empty:
        raise PhaseB2Error("Anchor safety audit has no selected Q×K rows.")
    key = ["q_contract_id", "k", "fold_policy_id", "fold_id", "split_role"]
    if "window_horizon_hours" in selected.columns:
        # The audit legitimately has one row per temporal horizon. A duplicate
        # means the same Q-K-fold-split-horizon was emitted twice, not that 3h
        # and 8h should be merged.
        key.append("window_horizon_hours")
    if selected.duplicated(key).any():
        raise PhaseB2Error("Anchor safety audit contains duplicate Q×K×fold×split rows.")
    if not selected["purge_applied"].astype(bool).all():
        raise PhaseB2Error("Anchor safety audit does not prove purge was applied.")
    # Feature-history crossings are diagnostic for downstream evaluation and
    # must not invalidate the semantic label contract.  B2 blocks only label
    # dependency crossings (persistence/deployment), which can change the
    # meaning of an anchor or leak label evidence across a split.
    for column in ("semantic_cross_split_anchor_count", "semantic_cross_deployment_anchor_count"):
        if (pd.to_numeric(selected[column], errors="coerce").fillna(-1) > 0).any():
            raise PhaseB2Error(f"Anchor safety violation in {column}.")
    semantic_count = pd.to_numeric(selected["semantic_admissible_anchor_count"], errors="coerce")
    unique_count = pd.to_numeric(selected["unique_anchor_count"], errors="coerce")
    if semantic_count.isna().any() or (semantic_count < 0).any() or (semantic_count > unique_count).any():
        raise PhaseB2Error("Invalid semantic-admissible anchor count.")
    evaluation_count = pd.to_numeric(selected["evaluation_admissible_anchor_count"], errors="coerce")
    if evaluation_count.isna().any() or (evaluation_count < 0).any() or (evaluation_count > unique_count).any():
        raise PhaseB2Error("Invalid evaluation-admissible anchor count.")
    if (pd.to_numeric(selected["dependency_admissible_anchor_count"], errors="coerce") < 0).any():
        raise PhaseB2Error("Invalid dependency-admissible anchor count.")


def _validate_distribution_legacy(frame: pd.DataFrame, decision: dict[str, Any], selected_q: str, selected_k: int, fold_policy_id: str | None = None) -> None:
    """Retained only for historical test compatibility; never used by B2."""
    required = {"q_contract_id", "k", "task_id", "fold_policy_id", "fold_id", "split_role", "class_label", "class_count", "event_count", "unique_cluster_count"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise PhaseB2Error(f"Distribution audit is incomplete: {missing}")
    selected = frame.loc[frame["q_contract_id"].astype(str).eq(selected_q) & frame["k"].astype("Int64").eq(selected_k)]
    if fold_policy_id is not None and "fold_policy_id" in frame.columns:
        selected = selected.loc[selected["fold_policy_id"].astype(str).eq(fold_policy_id)]
    if selected.empty:
        raise PhaseB2Error("Distribution audit has no selected Q×K rows.")
    gate = decision["support_gate"]
    for split, threshold_key in (("train", "min_train_class_count"), ("validation", "min_validation_class_count"), ("test", "min_test_class_count")):
        rows = selected.loc[selected["split_role"].astype(str).str.lower().eq(split)]
        if rows.empty or (pd.to_numeric(rows["class_count"], errors="coerce") < int(gate[threshold_key])).any():
            raise PhaseB2Error(f"Distribution support gate failed for {split}.")
    for split, threshold_key in (("train", "min_train_event_count"), ("validation", "min_validation_event_count"), ("test", "min_test_event_count")):
        rows = selected.loc[selected["split_role"].astype(str).str.lower().eq(split)]
        if (pd.to_numeric(rows["event_count"], errors="coerce") < int(gate[threshold_key])).any():
            raise PhaseB2Error(f"Event support gate failed for {split}.")
    if (pd.to_numeric(selected["unique_cluster_count"], errors="coerce") < int(gate["min_unique_cluster_count"])).any():
        raise PhaseB2Error("Unique-cluster support gate failed.")


def _validate_distribution_task_specific(
    frame: pd.DataFrame,
    decision: dict[str, Any],
    selected_q: str,
    selected_k: int,
    fold_policy_id: str,
) -> None:
    """Validate primary support independently for Point, Temporal and Same-Y."""
    required = {
        "q_contract_id", "k", "task_id", "horizon_id", "fold_policy_id", "fold_id",
        "split_role", "class_label", "class_count", "event_count", "unique_cluster_count",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise PhaseB2Error(f"Distribution audit is incomplete: {missing}")

    task = frame["task_id"].astype(str).str.upper()
    k_values = pd.to_numeric(frame["k"], errors="coerce").astype("Int64")
    selected = frame.loc[
        frame["q_contract_id"].astype(str).eq(selected_q)
        & frame["fold_policy_id"].astype(str).eq(fold_policy_id)
        & (
            ((task == "POINT") & k_values.isna())
            | ((task != "POINT") & k_values.eq(selected_k))
        )
    ]
    if selected.empty:
        raise PhaseB2Error("Distribution audit has no selected primary rows.")
    duplicate_key = ["task_id", "horizon_id", "fold_id", "split_role", "class_label"]
    if selected.duplicated(duplicate_key).any():
        raise PhaseB2Error("Distribution audit contains duplicate task/horizon/fold/class rows.")

    task_gates = decision["support_gate"]["task_support"]
    for task_name in ("POINT", "TEMPORAL", "SAME_Y"):
        task_rows = selected.loc[selected["task_id"].astype(str).str.upper().eq(task_name)]
        if task_rows.empty:
            raise PhaseB2Error(f"Distribution audit has no primary rows for task {task_name}.")
        if task_name == "POINT":
            eligible = set(decision["point_ontology_policy"]["primary_train_eligible"])
            task_rows = task_rows.loc[task_rows["class_label"].astype(str).isin(eligible)]
        elif task_name == "TEMPORAL":
            eligible = set(decision["temporal_ontology"]["primary_train_eligible"])
            task_rows = task_rows.loc[task_rows["class_label"].astype(str).isin(eligible)]
        if task_rows.empty:
            raise PhaseB2Error(f"Distribution audit has no primary-eligible rows for task {task_name}.")
        gate = task_gates[task_name]
        for split, threshold_key in (
            ("train", "min_train_class_count"),
            ("validation", "min_validation_class_count"),
            ("test", "min_test_class_count"),
        ):
            rows = task_rows.loc[task_rows["split_role"].astype(str).str.lower().eq(split)]
            if rows.empty or (pd.to_numeric(rows["class_count"], errors="coerce") < int(gate[threshold_key])).any():
                raise PhaseB2Error(f"{task_name} class support gate failed for {split}.")
        if task_name == "TEMPORAL":
            for split, threshold_key in (
                ("train", "min_train_event_count"),
                ("validation", "min_validation_event_count"),
                ("test", "min_test_event_count"),
            ):
                rows = task_rows.loc[task_rows["split_role"].astype(str).str.lower().eq(split)]
                if (pd.to_numeric(rows["event_count"], errors="coerce") < int(gate[threshold_key])).any():
                    raise PhaseB2Error(f"TEMPORAL event support gate failed for {split}.")
        if task_name != "POINT":
            if (pd.to_numeric(task_rows["unique_cluster_count"], errors="coerce") < int(gate["min_unique_cluster_count"])).any():
                raise PhaseB2Error(f"{task_name} unique-cluster support gate failed.")


def _validate_derived_contract(frame: pd.DataFrame) -> None:
    required = {
        "derived_evidence_id", "transform_id", "transform_version", "source_field_ids", "source_units",
        "output_unit", "formula_expression_or_formula_id", "previous_observation_policy",
        "absolute_value_applied", "clipping_policy", "null_policy", "infinity_policy",
        "rounding_policy", "comparison_precision", "code_reference_hash",
    }
    missing = sorted(required - set(frame.columns))
    if missing or frame.empty:
        raise PhaseB2Error(f"Derived-evidence contract is incomplete: {missing}")


def _validate_approved_contract_ids(
    decision: dict[str, Any],
    continuity: dict[str, Any],
    window: dict[str, Any],
    derived: pd.DataFrame,
) -> None:
    continuity_id = continuity.get("contract_id", continuity.get("continuity_contract_id"))
    window_id = window.get("contract_id", window.get("window_contract_id"))
    if continuity_id != decision["approved_continuity_contract_id"]:
        raise PhaseB2Error("Approved continuity contract ID does not match its artifact.")
    if window_id != decision["approved_window_contract_id"]:
        raise PhaseB2Error("Approved window contract ID does not match its artifact.")
    approved_derived = str(decision["approved_derived_evidence_contract_id"])
    derived_ids = (
        set(derived["contract_id"].astype(str))
        if "contract_id" in derived.columns
        else set(derived["derived_evidence_id"].astype(str))
    )
    if approved_derived not in derived_ids:
        raise PhaseB2Error("Approved derived-evidence contract ID is absent from its artifact.")


def _validate_continuity(payload: dict[str, Any]) -> None:
    if not payload.get("contract_id", payload.get("continuity_contract_id")):
        raise PhaseB2Error("Continuity contract must declare contract_id.")
    if not isinstance(payload.get("strict_continuity"), dict) or not isinstance(payload.get("deployment_continuity"), dict):
        raise PhaseB2Error("Continuity contract must contain strict_continuity and deployment_continuity mappings.")


def _validate_window(payload: dict[str, Any]) -> None:
    if not payload.get("contract_id", payload.get("window_contract_id")):
        raise PhaseB2Error("Window contract must declare contract_id.")
    required = {"window_interval", "timestamp_authority", "nominal_cadence_minutes", "expected_slot_formula", "anchor_inclusion", "slot_assignment", "duplicate_slot_policy", "coverage", "max_internal_gap", "tie_order"}
    missing = sorted(required - set(payload))
    if missing:
        raise PhaseB2Error(f"Window contract is incomplete: {missing}")


def _load_q_values(frame: pd.DataFrame) -> dict[str, float]:
    result: dict[str, float] = {}
    for row in frame.to_dict("records"):
        match = _Q_PATTERN.search(str(row.get("threshold_id", "")))
        if match:
            result[match.group(1)] = float(row["threshold_value"])
    if set(result) != {"Q05", "Q10", "Q15", "Q20"}:
        raise PhaseB2Error("Phase A threshold registry must contain Q05/Q10/Q15/Q20.")
    return result


def _build_freeze_commitment(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, low_memory=False)
    required = {"record.id"}
    if not required.issubset(frame.columns):
        raise PhaseB2Error("Canonical history is missing record.id.")
    sample_col = next((c for c in ("record.sample_time_local", "sample_time", "record.sample_time") if c in frame.columns), None)
    if sample_col is None:
        raise PhaseB2Error("Canonical history has no sample-time field.")
    result = pd.DataFrame({
        "record_id": frame["record.id"].astype("string"),
        "sample_time_utc": pd.to_datetime(frame[sample_col], errors="coerce", utc=True),
    })
    if result["record_id"].duplicated().any() or result["sample_time_utc"].isna().any():
        raise PhaseB2Error("Canonical freeze commitment has duplicate IDs or malformed timestamps.")
    return result.convert_dtypes()


def _read_table(path: Path) -> pd.DataFrame:
    path = path.resolve()
    if not path.exists():
        raise PhaseB2Error(f"Required B2 audit artifact is missing: {path}")
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path).convert_dtypes()
    return pd.read_csv(path).convert_dtypes()


def _read_contract_mapping(path: Path) -> dict[str, Any]:
    if not path.resolve().exists():
        raise PhaseB2Error(f"Required B2 contract artifact is missing: {path}")
    if path.suffix.lower() in {".yaml", ".yml"}:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    elif path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        raise PhaseB2Error(f"Contract mapping must be YAML or JSON: {path}")
    if not isinstance(payload, dict):
        raise PhaseB2Error(f"Contract mapping must be an object: {path}")
    return payload


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=True, allow_unicode=True), encoding="utf-8")


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise PhaseB2Error(f"Missing YAML artifact: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PhaseB2Error(f"YAML artifact must be an object: {path}")
    return payload


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise PhaseB2Error(f"Missing JSON artifact: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PhaseB2Error(f"JSON artifact must be an object: {path}")
    return payload


def _allocate_run_id(output_root: Path) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base = f"semantic_contract_{stamp}"
    for index in range(1000):
        run_id = base if index == 0 else f"{base}_{index:03d}"
        if not (output_root / run_id).exists() and not (output_root / ".staging" / run_id).exists():
            return run_id
    raise FileExistsError("Unable to allocate a B2 run directory.")
