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
    _validate_review_decision(decision, b1_manifest, config.expected_difference_contract_path)

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
    ).any():
        raise PhaseB2Error("Selected Q×K is absent from B1 fold support.")

    anchor = _read_table(config.anchor_safety_audit_path)
    distribution = _read_table(config.distribution_audit_path)
    _validate_anchor_safety(anchor, selected_q, selected_k)
    _validate_distribution(distribution, decision, selected_q, selected_k)

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
        "anchor_hash": file_sha256(config.anchor_safety_audit_path.resolve()),
        "distribution_hash": file_sha256(config.distribution_audit_path.resolve()),
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
        "expected_difference": file_sha256(config.expected_difference_contract_path.resolve()),
        "review_decision": decision_hash,
    }
    semantic_payload = {
        "schema_version": "phase_b2.semantic_contract.v1",
        "selected_primary_q": selected_q,
        "selected_primary_q_value": q_values[selected_q],
        "selected_primary_k": selected_k,
        "ontology_policy": decision["point_ontology_policy"],
        "resolver_policy": decision["resolver_policy"],
        "temporal_resolution_policy": decision["temporal_resolution_policy"],
        "same_y_policy": decision["same_y_policy"],
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
    op_rows = []
    for row in geometry.dropna(subset=["q_contract_id", "k"]).drop_duplicates(["q_contract_id", "k"]).to_dict("records"):
        q_id = str(row["q_contract_id"])
        k = int(row["k"])
        op_rows.append({
            "operationalization_id": f"{q_id}-K{k}",
            "q_contract_id": q_id,
            "persistence_contract_id": f"K_{k}",
            "selected_k": k,
            "authority_status": "PRIMARY_INTERNAL_AUTHORITY" if q_id == selected_q and k == selected_k else "RQ1_DIAGNOSTIC_ONLY",
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
    _write_yaml(staging / "ontology" / "temporal_anchor_ontology.yaml", decision.get("temporal_ontology", {
        "classes": ["TEMPORAL_REFERENCE_CONTEXT", "TEMPORAL_PERSISTENT_LOW", "TEMPORAL_UNRESOLVED"],
    }))
    _write_yaml(staging / "ontology" / "same_y_contract.yaml", decision["same_y_policy"])
    shutil.copy2(config.expected_difference_contract_path.resolve(), staging / "compatibility" / "expected_difference_contract.csv")

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
        "primary_operationalization_id": f"{selected_q}-K{selected_k}",
        "primary_q": selected_q,
        "primary_k": selected_k,
        "decision_pack_hash": inputs["b1_manifest"]["decision_pack_hash"],
        "anchor_safety_audit_hash": inputs["anchor_hash"],
        "distribution_audit_hash": inputs["distribution_hash"],
        "expected_difference_contract_hash": file_sha256(config.expected_difference_contract_path.resolve()),
        "freeze_timestamp_utc": freeze_timestamp,
        "parent_protocol_registry_contract_hash": inputs["registry"].run_manifest["registry_contract_hash"],
        "input_hashes": input_hashes,
    }
    write_json(staging / "run_metadata" / "run_manifest.json", manifest)
    write_yaml(staging / "phase_b_freeze.yaml", {
        "overall_status": "PASS",
        "semantic_contract_id": semantic_id,
        "semantic_contract_hash": semantic_hash,
        "primary_operationalization_id": f"{selected_q}-K{selected_k}",
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


def _validate_review_decision(decision: dict[str, Any], b1_manifest: dict[str, Any], expected_path: Path) -> None:
    required = {
        "decision_status", "decision_id", "reviewer_ids", "reviewed_at_utc",
        "reviewed_decision_pack_hash", "selected_primary_q", "selected_primary_k",
        "selected_primary_operationalization_id", "point_ontology_policy", "support_gate",
        "approved_continuity_contract_id", "approved_window_contract_id",
        "approved_derived_evidence_contract_id", "resolver_policy",
        "temporal_resolution_policy", "same_y_policy", "evidence_role_registry",
        "evidence_dependency_registry",
    }
    missing = sorted(required - set(decision))
    if missing:
        raise PhaseB2Error(f"Review decision is missing required fields: {missing}")
    if decision["decision_status"] != "APPROVED":
        raise PhaseB2Error("B2 requires decision_status=APPROVED.")
    if str(decision["reviewed_decision_pack_hash"]) != str(b1_manifest.get("decision_pack_hash")):
        raise PhaseB2Error("Review decision hash does not match B1 decision pack.")
    expected_op = f"{decision['selected_primary_q']}-K{int(decision['selected_primary_k'])}"
    if str(decision["selected_primary_operationalization_id"]) != expected_op:
        raise PhaseB2Error("selected_primary_operationalization_id does not match selected Q×K.")
    expected_hash = file_sha256(expected_path.resolve())
    declared = decision.get("expected_difference_contract_hash")
    if declared is not None and str(declared) != expected_hash:
        raise PhaseB2Error("Expected-difference contract hash mismatch.")
    gate = decision["support_gate"]
    required_gate = {
        "policy", "min_train_class_count", "min_validation_class_count",
        "min_test_class_count", "min_train_event_count", "min_validation_event_count",
        "min_test_event_count", "min_unique_cluster_count",
    }
    if not required_gate.issubset(gate):
        raise PhaseB2Error("Support gate must declare reviewer-owned minimum thresholds.")


def _validate_anchor_safety(frame: pd.DataFrame, selected_q: str, selected_k: int) -> None:
    required = {
        "q_contract_id", "k", "fold_policy_id", "fold_id", "split_role",
        "unique_anchor_count", "dependency_admissible_anchor_count",
        "purge_excluded_count", "boundary_excluded_count",
        "cross_split_anchor_count", "cross_deployment_anchor_count", "purge_applied",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise PhaseB2Error(f"Anchor safety audit is incomplete: {missing}")
    selected = frame.loc[frame["q_contract_id"].astype(str).eq(selected_q) & frame["k"].astype("Int64").eq(selected_k)]
    if selected.empty:
        raise PhaseB2Error("Anchor safety audit has no selected Q×K rows.")
    key = ["q_contract_id", "k", "fold_policy_id", "fold_id", "split_role"]
    if selected.duplicated(key).any():
        raise PhaseB2Error("Anchor safety audit contains duplicate Q×K×fold×split rows.")
    if not selected["purge_applied"].astype(bool).all():
        raise PhaseB2Error("Anchor safety audit does not prove purge was applied.")
    for column in ("cross_split_anchor_count", "cross_deployment_anchor_count"):
        if (pd.to_numeric(selected[column], errors="coerce").fillna(-1) > 0).any():
            raise PhaseB2Error(f"Anchor safety violation in {column}.")
    if (pd.to_numeric(selected["dependency_admissible_anchor_count"], errors="coerce") < 0).any():
        raise PhaseB2Error("Invalid dependency-admissible anchor count.")


def _validate_distribution(frame: pd.DataFrame, decision: dict[str, Any], selected_q: str, selected_k: int) -> None:
    required = {"q_contract_id", "k", "task_id", "fold_policy_id", "fold_id", "split_role", "class_label", "class_count", "event_count", "unique_cluster_count"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise PhaseB2Error(f"Distribution audit is incomplete: {missing}")
    selected = frame.loc[frame["q_contract_id"].astype(str).eq(selected_q) & frame["k"].astype("Int64").eq(selected_k)]
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
    if approved_derived not in set(derived["derived_evidence_id"].astype(str)):
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
