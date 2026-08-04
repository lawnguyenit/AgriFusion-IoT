from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from Backend.Benchmark.common.digests import dataframe_digest, file_sha256, population_digest, stable_digest
from Backend.Benchmark.protocol_registry import load_protocol_registry
from Backend.Benchmark.shared.artifacts import create_run_directory, write_json, write_yaml
from Backend.Benchmark.weak_labels.lifecycle.phase_b_contract.contracts import PhaseBConfig, PhaseBResult
from Backend.Benchmark.weak_labels.lifecycle.phase_b_contract.anchor_audit import (
    aggregate_fold_support_for_b2,
    build_qk_anchor_safety_audits,
)
from Backend.Benchmark.weak_labels.lifecycle.phase_b_contract.distribution_audit import (
    build_qk_distribution_audit,
)
from Backend.Benchmark.weak_labels.lifecycle.phase_b_contract.geometry import build_qk_geometry
from Backend.Benchmark.weak_labels.lifecycle.phase_b_contract.resolution import build_point_contract_replay
from Backend.Benchmark.weak_labels.lifecycle.phase_b_contract.threshold_audit import (
    build_candidate_threshold_audit,
    load_phase_a_threshold_inputs,
)


def build_phase_b_decision_pack(config: PhaseBConfig) -> PhaseBResult:
    phase_a = config.phase_a_run_dir.resolve()
    registry = load_protocol_registry(config.protocol_registry_run_dir.resolve())
    _validate_phase_a_inputs(phase_a, registry)
    threshold_inputs = load_phase_a_threshold_inputs(phase_a)
    output_root = config.output_root.resolve()
    run_id, output_dir = create_run_directory(output_root, prefix="phase_b_decision_pack")
    applicability = pd.read_parquet(phase_a / "technical_applicability" / "rule_applicability.parquet")
    primitive = pd.read_parquet(phase_a / "evidence_inventory" / "e1_primitive_evidence.parquet")
    replay, matrix, counts = build_point_contract_replay(applicability, primitive)
    threshold_audit, boundary_cases, threshold_status = build_candidate_threshold_audit(
        primitive, applicability, threshold_inputs
    )
    geometry, _raw_support = build_qk_geometry(
        config.canonical_history_path.resolve(),
        phase_a,
        threshold_inputs.q_values,
        protocol_registry_run_dir=config.protocol_registry_run_dir.resolve(),
    )
    anchor_safety, anchor_detail, boundary_audit = build_qk_anchor_safety_audits(
        config.canonical_history_path.resolve(),
        phase_a,
        config.protocol_registry_run_dir.resolve(),
        threshold_inputs.q_values,
    )
    fold_support = aggregate_fold_support_for_b2(anchor_safety)
    distribution_audit = build_qk_distribution_audit(
        config.canonical_history_path.resolve(),
        phase_a,
        config.protocol_registry_run_dir.resolve(),
        threshold_inputs.q_values,
        anchor_detail,
    )
    _write_decision_pack(
        output_dir,
        replay,
        matrix,
        counts,
        geometry,
        fold_support,
        anchor_safety,
        anchor_detail,
        boundary_audit,
        distribution_audit,
        threshold_audit,
        boundary_cases,
        threshold_status,
        threshold_inputs,
        phase_a,
        registry,
        config,
    )
    status = "SEMANTIC_REVIEW_REQUIRED"
    write_yaml(
        output_dir / "phase_b1_status.yaml",
        {
            "phase": "PHASE_B1_DECISION_PACK",
            "status": status,
            "primary_selection_status": "REVIEW_REQUIRED",
            "selected_primary_operationalization": None,
            "authority_status": "CANDIDATE_ONLY",
            "review_required": True,
            "model_scores_used": False,
            "labels_materialized": False,
            "frozen_contract_created": False,
            "model_training_performed": False,
            "candidate_pack_completeness": "COMPLETE",
            "anchor_safety_audit_present": True,
            "distribution_audit_present": True,
            "boundary_adjustment": "AUDIT_ONLY_REVIEW_REQUIRED",
            "boundary_changes_applied": False,
            "material_boundary_shift_threshold_percent": 4.0,
            "ready_for_b2_review": True,
        },
    )
    return PhaseBResult(run_id, output_dir, status, True)


def build_frozen_protocol_registry(base_registry_run_dir: Path, semantic_contract_run_dir: Path) -> Path:
    """Create an additive CONTRACT_FROZEN registry from a frozen contract."""
    contract_manifest = load_semantic_contract(semantic_contract_run_dir)
    freeze_path = semantic_contract_run_dir.resolve() / "provenance" / "freeze_activity.json"
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    return _write_frozen_registry(
        base_registry_run_dir.resolve(),
        semantic_contract_run_dir.resolve(),
        None,
        str(freeze["freeze_timestamp_utc"]),
        str(contract_manifest["run_id"]),
    )


def load_semantic_contract(semantic_contract_run_dir: Path) -> dict[str, object]:
    manifest_path = semantic_contract_run_dir.resolve() / "run_metadata" / "run_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing semantic contract manifest: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _validate_phase_a_inputs(phase_a: Path, registry) -> None:
    readiness_path = phase_a / "phase_a_readiness.yaml"
    if not readiness_path.exists():
        raise FileNotFoundError(f"Missing Phase A readiness gate: {readiness_path}")
    readiness = yaml.safe_load(readiness_path.read_text(encoding="utf-8"))
    readiness_payload = readiness.get("phase_a_readiness", readiness)
    if readiness_payload.get("overall_status") != "PASS":
        raise PermissionError("Phase B requires a PASS Phase A readiness run.")
    if not bool(registry.run_manifest.get("phase_a_only", False)):
        raise ValueError("Phase B input registry must be the Phase A parent registry.")
    required = [
        phase_a / "technical_applicability" / "rule_applicability.parquet",
        phase_a / "evidence_inventory" / "e1_primitive_evidence.parquet",
        phase_a / "threshold_diagnostics" / "threshold_registry.csv",
        phase_a / "threshold_diagnostics" / "threshold_sensitivity.csv",
        phase_a / "threshold_diagnostics" / "threshold_fit_cohort_records.parquet",
        phase_a / "run_metadata" / "run_manifest.json",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Phase A artifacts missing: {missing}")


def _write_decision_pack(
    output_dir,
    replay,
    matrix,
    counts,
    geometry,
    fold_support,
    anchor_safety,
    anchor_detail,
    boundary_audit,
    distribution_audit,
    threshold_audit,
    boundary_cases,
    threshold_status,
    threshold_inputs,
    phase_a,
    registry,
    config,
) -> None:
    for directory in ("resolution", "operationalization", "thresholds", "run_metadata"):
        (output_dir / directory).mkdir(parents=True, exist_ok=True)
    paths = {
        "point_contract_replay": output_dir / "resolution" / "point_contract_replay.parquet",
        "compatibility_matrix": output_dir / "resolution" / "point_compatibility_matrix.csv",
        "resolution_counts": output_dir / "resolution" / "point_resolution_snapshot.csv",
        "k_geometry": output_dir / "operationalization" / "qk_geometry.parquet",
        "k_registry": output_dir / "operationalization" / "k_regime_registry.csv",
        "fold_support": output_dir / "operationalization" / "qk_fold_support.csv",
        "anchor_safety": output_dir / "operationalization" / "qk_anchor_safety_audit.parquet",
        "anchor_detail": output_dir / "operationalization" / "anchor_dependency_audit.parquet",
        "boundary_audit": output_dir / "operationalization" / "qk_boundary_audit.parquet",
        "distribution_audit": output_dir / "operationalization" / "qk_distribution_audit.parquet",
    }
    replay.to_parquet(paths["point_contract_replay"], index=False)
    matrix.to_csv(paths["compatibility_matrix"], index=False)
    counts.to_csv(paths["resolution_counts"], index=False)
    geometry.to_parquet(paths["k_geometry"], index=False)
    _build_k_registry(geometry).to_csv(paths["k_registry"], index=False)
    # qk_fold_support is now interval-safe support. The old run-end projection
    # is intentionally not published as an authority artifact.
    fold_support.to_csv(paths["fold_support"], index=False)
    anchor_safety.to_parquet(paths["anchor_safety"], index=False)
    anchor_detail.to_parquet(paths["anchor_detail"], index=False)
    boundary_audit.to_parquet(paths["boundary_audit"], index=False)
    distribution_audit.to_parquet(paths["distribution_audit"], index=False)
    threshold_audit.to_csv(output_dir / "thresholds" / "candidate_threshold_audit.csv", index=False)
    boundary_cases.to_parquet(output_dir / "thresholds" / "threshold_boundary_cases.parquet", index=False)
    write_yaml(
        output_dir / "thresholds" / "threshold_provenance_check.yaml",
        {
            **threshold_status,
            "threshold_registry_hash": threshold_inputs.threshold_registry_hash,
            "threshold_sensitivity_hash": threshold_inputs.threshold_sensitivity_hash,
            "fit_cohort_hash": threshold_inputs.fit_cohort_hash,
            "fit_cohort_id": threshold_inputs.fit_cohort_id,
            "authority_status": "CANDIDATE_ONLY",
        },
    )
    write_yaml(
        output_dir / "kill_criteria_report.yaml",
        {
            "candidate_operationalizations": sorted(
                set(geometry.loc[geometry["operationalization_id"].notna(), "operationalization_id"].astype(str))
            ),
            "primary_selection_status": "REVIEW_REQUIRED",
            "threshold_degeneracy": threshold_status["ec_shift_viability"],
            "compatibility_unhandled_states": 0,
            "compatibility_structurally_unreachable_states": int((matrix["reachability_status"] == "STRUCTURALLY_UNREACHABLE").sum()),
            "compatibility_unobserved_states": int((matrix["reachability_status"] == "UNOBSERVED_IN_E1").sum()),
            "continuity_sensitivity_documented": True,
            "anchor_safety_complete": True,
            "distribution_audit_complete": True,
            "boundary_adjustment_status": "AUDIT_ONLY_REVIEW_REQUIRED",
            "boundary_changes_applied": False,
            "material_boundary_shift_threshold_percent": 4.0,
            "model_scores_used": False,
            "authority_status": "CANDIDATE_ONLY",
        },
    )
    phase_a_manifest = json.loads((phase_a / "run_metadata" / "run_manifest.json").read_text(encoding="utf-8"))
    decision_pack_hash = stable_digest(
        {
            "phase_a_run_id": phase_a_manifest["run_id"],
            "phase_a_hash": file_sha256(phase_a / "phase_a_readiness.yaml"),
            "registry_contract_hash": registry.run_manifest["registry_contract_hash"],
            "point_counts": counts.to_dict(orient="records"),
            "k_geometry": geometry.to_dict(orient="records"),
            "fold_support": fold_support.to_dict(orient="records"),
            "anchor_safety": anchor_safety.to_dict(orient="records"),
            "boundary_audit": boundary_audit.to_dict(orient="records"),
            "distribution_audit": distribution_audit.to_dict(orient="records"),
        }
    )
    write_json(
        output_dir / "run_metadata" / "run_manifest.json",
        {
            "pipeline": "weak_labels_phase_b_decision_pack",
            "run_id": output_dir.name,
            "phase": "PHASE_B1_DECISION_PACK",
            "phase_a_run_dir": str(phase_a),
            "phase_a_readiness_hash": file_sha256(phase_a / "phase_a_readiness.yaml"),
            "protocol_registry_run_dir": str(registry.run_dir),
            "protocol_registry_contract_hash": registry.run_manifest["registry_contract_hash"],
            "canonical_history_path": str(config.canonical_history_path.resolve()),
            "canonical_history_hash": file_sha256(config.canonical_history_path.resolve()),
            "decision_pack_hash": decision_pack_hash,
            "phase_a_threshold_registry_hash": threshold_inputs.threshold_registry_hash,
            "phase_a_threshold_sensitivity_hash": threshold_inputs.threshold_sensitivity_hash,
            "phase_a_fit_cohort_hash": threshold_inputs.fit_cohort_hash,
            "phase_a_fit_cohort_id": threshold_inputs.fit_cohort_id,
            "anchor_safety_hash": dataframe_digest(
                anchor_safety,
                columns=list(anchor_safety.columns),
                sort_columns=[
                    "q_contract_id",
                    "persistence_k",
                    "fold_policy_id",
                    "fold_id",
                    "split_role",
                    "window_horizon_hours",
                ],
            ),
            "fold_support_hash": dataframe_digest(
                fold_support,
                columns=list(fold_support.columns),
                sort_columns=[
                    "q_contract_id",
                    "persistence_k",
                    "fold_policy_id",
                    "fold_id",
                    "split_role",
                ],
            ),
            "boundary_audit_hash": dataframe_digest(
                boundary_audit,
                columns=list(boundary_audit.columns),
                sort_columns=["q_contract_id", "fold_policy_id", "fold_id", "boundary_name"],
            ),
            "distribution_audit_hash": dataframe_digest(
                distribution_audit,
                columns=list(distribution_audit.columns),
                sort_columns=[
                    "q_contract_id",
                    "task_id",
                    "fold_policy_id",
                    "fold_id",
                    "split_role",
                    "class_name",
                ],
            ),
            "candidate_operationalizations": sorted(
                set(geometry.loc[geometry["operationalization_id"].notna(), "operationalization_id"].astype(str))
            ),
            "primary_selection_status": "REVIEW_REQUIRED",
            "selected_primary_operationalization": None,
            "authority_status": "CANDIDATE_ONLY",
            "candidate_pack_completeness": "COMPLETE",
            "anchor_safety_audit_present": True,
            "distribution_audit_present": True,
            "boundary_adjustment": "AUDIT_ONLY_REVIEW_REQUIRED",
            "boundary_changes_applied": False,
            "material_boundary_shift_threshold_percent": 4.0,
            "ready_for_b2_review": True,
            "labels_materialized": False,
            "frozen_contract_created": False,
            "model_training_performed": False,
        },
    )
    _write_artifact_catalog(output_dir)


def _build_k_registry(geometry: pd.DataFrame) -> pd.DataFrame:
    base = geometry.loc[geometry["regime_role"].isna()].drop(columns=["support_status", "selection_reason"], errors="ignore").copy()
    role_rows = geometry.loc[geometry["regime_role"].notna()].copy()
    if role_rows.empty:
        base["regime_roles"] = pd.NA
        base["support_status"] = "UNCLASSIFIED"
        return base
    role_map = role_rows.dropna(subset=["k"]).groupby(["q_contract_id", "k"])["regime_role"].agg(lambda values: "|".join(str(value) for value in values if pd.notna(value))).reset_index(name="regime_roles")
    result = base.merge(role_map, on=["q_contract_id", "k"], how="left")
    result["support_status"] = result["regime_roles"].fillna("GEOMETRY_ONLY")
    return result


def _write_frozen_contract(output_dir, decision_pack_dir, review_path, phase_a, registry, config, selected_q, selected_k, threshold_inputs, freeze_timestamp):
    raise RuntimeError("The old hard-coded freeze writer is removed from the active B2 path; use freeze_phase_b_contract.")
    for directory in ("ontology", "evidence", "thresholds", "continuity", "operationalization", "resolution", "compatibility", "provenance", "run_metadata"):
        (output_dir / directory).mkdir(parents=True, exist_ok=True)
    decision_manifest = json.loads((decision_pack_dir / "run_metadata" / "run_manifest.json").read_text(encoding="utf-8"))
    decision_hash = decision_manifest["decision_pack_hash"]
    canonical = pd.read_csv(config.canonical_history_path.resolve(), low_memory=False)
    sample = pd.to_datetime(canonical["record.sample_time_local"], errors="coerce", utc=True)
    environment = pd.Series("UNASSIGNED", index=canonical.index, dtype="string")
    for environment_row in registry.environment_manifest.itertuples(index=False):
        start = pd.to_datetime(environment_row.start_time, utc=True)
        end = pd.to_datetime(environment_row.end_time, utc=True)
        environment.loc[(sample >= start) & (sample < end)] = str(environment_row.environment_id)
    commitment = pd.DataFrame({
        "record_id": canonical["record.id"].astype("string"),
        "environment_id": environment,
        "sample_time_utc": sample,
        "upload_time_utc": pd.to_datetime(canonical.get("record.upload_time_local"), errors="coerce", utc=True),
        "source_path": canonical.get("record.source_path", pd.Series(pd.NA, index=canonical.index)).astype("string"),
    }).convert_dtypes()
    commitment["canonical_record_hash"] = commitment.apply(lambda row: stable_digest(row.to_dict()), axis=1)
    commitment.to_parquet(output_dir / "provenance" / "freeze_record_commitment.parquet", index=False)
    snapshot_hash = dataframe_digest(commitment, columns=list(commitment.columns), sort_columns=["record_id"])
    id_hash = population_digest(commitment["record_id"])
    semantic_payload = {
        "q_primary": selected_q,
        "q_primary_value": dict(threshold_inputs.q_values)[selected_q],
        "k_primary": selected_k,
        "q_family": [q_id for q_id, _ in threshold_inputs.q_values],
        "point_resolution": "CONTEXT_INCOMPLETE_OUTSIDE_PRIMARY_TRAIN",
        "temporal_semantics": "ANCHOR_CONDITIONED",
        "strict_policy": "STRICT_15M_PM2_V1",
        "window_policy": {"coverage": 0.75, "max_gap_minutes": 30},
        "decision_pack_hash": decision_hash,
    }
    contract_hash = stable_digest(semantic_payload)
    write_yaml(output_dir / "ontology" / "point_ontology.yaml", {"classes": ["reference_context_point", "low_relative_moisture_point", "unresolved_environmental_evidence_point"], "outside_train": ["point_not_evaluable", "point_context_incomplete"]})
    write_yaml(output_dir / "ontology" / "temporal_anchor_ontology.yaml", {"classes": ["reference_context_at_anchor", "persistent_low_relative_moisture_at_anchor", "unresolved_environmental_evidence_at_anchor"], "outside_train": ["window_ineligible", "point_context_incomplete_transfer"]})
    write_yaml(output_dir / "ontology" / "same_y_contract.yaml", {"representation_only": True, "target_source": "point_assignment", "new_ontology": False})
    pd.DataFrame(
        [
            {"evidence_id": "low_flag", "role": "TARGET_DEFINING_DIRECT", "scientific_status": "DISCOVERY_FIXED"},
            {"evidence_id": "thermal_flag", "role": "AUXILIARY_CONTEXT", "scientific_status": "FIXED_CONTEXT_HEURISTIC"},
            {"evidence_id": "moisture_rise_flag", "role": "AUXILIARY_TRANSITION", "scientific_status": "FIXED_CONTEXT_HEURISTIC"},
            {"evidence_id": "ec_shift_flag", "role": "AUXILIARY_PROXY", "scientific_status": "TELEMETRY_PROXY"},
        ]
    ).to_csv(output_dir / "evidence" / "evidence_role_registry.csv", index=False)
    pd.DataFrame(
        [
            {"source_id": "moisture_rise_flag", "depends_on": "strict_previous_observation", "dependency_type": "APPLICABILITY"},
            {"source_id": "ec_shift_flag", "depends_on": "strict_previous_observation", "dependency_type": "APPLICABILITY"},
            {"source_id": "moisture_rise_flag", "depends_on": "ec_shift_flag", "dependency_type": "CORRELATED_PROXY"},
        ]
    ).to_csv(output_dir / "evidence" / "evidence_dependency_registry.csv", index=False)
    q_registry = threshold_inputs.registry.copy()
    q_registry["contract_freeze_id"] = output_dir.name
    q_registry.to_csv(output_dir / "thresholds" / "frozen_threshold_registry.csv", index=False)
    pd.DataFrame([{"q_contract_id": q_id, "q_value": value, "role": "PRIMARY" if q_id == selected_q else "SENSITIVITY"} for q_id, value in threshold_inputs.q_values]).to_csv(output_dir / "operationalization" / "q_operationalization_registry.csv", index=False)
    pd.DataFrame([{"contract_id": "K_PRIMARY", "selected_k": selected_k, "semantics": "OBSERVATION_COUNT", "elapsed_time_audit_only": True}, {"contract_id": "K_GEOMETRY_SCAN", "selected_k": "DATA_SUPPORTED", "semantics": "EVENT_SURVIVAL_DIAGNOSTIC", "elapsed_time_audit_only": True}]).to_csv(output_dir / "operationalization" / "persistence_operationalization_registry.csv", index=False)
    write_yaml(output_dir / "continuity" / "strict_continuity_contract.yaml", {"policy_id": "STRICT_15M_PM2_V1", "allowed_gap_minutes": [13, 17], "elapsed_time_audit_only": True})
    write_yaml(output_dir / "continuity" / "window_continuity_contract.yaml", {"coverage_ratio": 0.75, "max_internal_gap_minutes": 30, "full_history_span_available_required": True})
    write_yaml(output_dir / "continuity" / "deployment_continuity_contract.yaml", {"hard_boundary": True, "cross_deployment_windows": False, "future_observed_run_state_used_for_eligibility": False})
    write_yaml(output_dir / "operationalization" / "primary_contract.yaml", {"q_contract_id": selected_q, "q_value": dict(threshold_inputs.q_values)[selected_q], "k_primary": selected_k, "model_score_used_for_selection": False})
    write_yaml(output_dir / "resolution" / "point_resolution_contract.yaml", {"context_incomplete_outside_primary_train": True, "low_precedence": "LOW_WINS_AND_PRESERVES_TAGS", "unresolved_requires_observed_auxiliary_positive": True})
    write_yaml(output_dir / "resolution" / "temporal_anchor_resolution_contract.yaml", {"anchor_conditioned": True, "window_is_evidence_domain": True, "point_context_incomplete_transfer_outside_train": True})
    pd.DataFrame([{"legacy_label": "normal_point", "contract_label": "reference_context_point"}, {"legacy_label": "low_relative_moisture_point", "contract_label": "low_relative_moisture_point"}, {"legacy_label": "unknown_environment_point", "contract_label": "unresolved_environmental_evidence_point"}]).to_csv(output_dir / "compatibility" / "legacy_label_mapping.csv", index=False)
    shutil.copy2(decision_pack_dir / "resolution" / "point_compatibility_matrix.csv", output_dir / "resolution" / "point_compatibility_matrix.csv")
    shutil.copy2(decision_pack_dir / "operationalization" / "k_regime_registry.csv", output_dir / "operationalization" / "frozen_k_regime_registry.csv")
    write_json(output_dir / "provenance" / "freeze_activity.json", {"freeze_timestamp_utc": freeze_timestamp, "freeze_canonical_snapshot_hash": snapshot_hash, "freeze_record_id_set_hash": id_hash, "freeze_record_count": int(len(commitment)), "freeze_max_sample_time": str(sample.max()), "freeze_max_upload_time": str(commitment["upload_time_utc"].max()), "review_decision_path": str(review_path.resolve())})
    write_json(output_dir / "run_metadata" / "run_manifest.json", {"pipeline": "weak_labels_semantic_contract", "run_id": output_dir.name, "phase": "PHASE_B2_CONTRACT_FROZEN", "semantic_contract_hash": contract_hash, "decision_pack_hash": decision_hash, "parent_protocol_registry_contract_hash": registry.run_manifest["registry_contract_hash"], "freeze_timestamp_utc": freeze_timestamp, "freeze_record_id_set_hash": id_hash, "freeze_canonical_snapshot_hash": snapshot_hash, "primary_q": selected_q, "primary_k": selected_k, "labels_materialized": False, "model_training_performed": False, "downstream_runners_unlocked": False})
    write_yaml(output_dir / "phase_b_freeze.yaml", {"overall_status": "PASS", "semantic_contract_hash": contract_hash, "primary_q": selected_q, "primary_k": selected_k, "e2_e3_sealed": True, "e3_claim": "PROTOCOL_LOCKED_TRANSPORT_REEVALUATION", "e4_materialized": False})
    _write_artifact_catalog(output_dir)


def _write_frozen_registry(parent_dir, contract_dir, config, freeze_timestamp, contract_run_id):
    destination_root = parent_dir.parent
    run_id, run_dir = create_run_directory(destination_root, prefix="protocol_registry_frozen")
    for source in parent_dir.iterdir():
        if source.name == "run_metadata":
            continue
        target = run_dir / source.name
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
    metadata = run_dir / "run_metadata"
    metadata.mkdir(parents=True, exist_ok=True)
    parent_manifest = json.loads((parent_dir / "run_metadata" / "run_manifest.json").read_text(encoding="utf-8"))
    semantic_hash = load_semantic_contract(contract_dir)["semantic_contract_hash"]
    frozen_registry_hash = stable_digest({"parent_registry_contract_hash": parent_manifest["registry_contract_hash"], "semantic_contract_hash": semantic_hash, "freeze_timestamp_utc": freeze_timestamp})
    write_json(metadata / "run_manifest.json", {**parent_manifest, "pipeline": "protocol_registry", "run_id": run_id, "protocol_registry_version": "2026-07-31.phase-b.v1", "registry_contract_hash": frozen_registry_hash, "phase_a_only": False, "semantic_contract_frozen": True, "native_engine_implemented": False, "downstream_runners_unlocked": False, "current_stage": "CONTRACT_FROZEN", "semantic_contract_run_dir": str(contract_dir), "semantic_contract_hash": semantic_hash, "freeze_timestamp_utc": freeze_timestamp, "e4_materialized": False, "parent_registry_run_dir": str(parent_dir), "parent_registry_contract_hash": parent_manifest["registry_contract_hash"]})
    _write_artifact_catalog(run_dir)
    return run_dir


def _write_artifact_catalog(run_dir: Path) -> None:
    rows = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file() or path.name == "artifact_catalog.csv":
            continue
        rows.append({"artifact_path": str(path.relative_to(run_dir)), "sha256": file_sha256(path), "size_bytes": path.stat().st_size})
    pd.DataFrame(rows).to_csv(run_dir / "run_metadata" / "artifact_catalog.csv", index=False)
