from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from Backend.Benchmark.common.digests import file_sha256, stable_digest
from Backend.Benchmark.protocol_registry import load_protocol_registry
from Backend.Benchmark.weak_labels.contracts.native import (
    NativeContract,
    NativeContractError,
    NativeEngineConfig,
    NativeEngineResult,
    expected_difference_contract_hash,
)
from Backend.Benchmark.weak_labels.semantic.continuity.primitives import build_continuity_primitives, build_continuity_registry
from Backend.Benchmark.weak_labels.semantic.derived_evidence.transforms import build_derived_evidence
from Backend.Benchmark.weak_labels.infrastructure.input_boundary import load_e1_authorized_canonical
from Backend.Benchmark.weak_labels.provenance.materialize import (
    build_intrinsic_candidate_assignments,
    build_semantic_fold_projection,
    materialize_from_assignments,
)
from Backend.Benchmark.weak_labels.semantic.point.resolver import resolve_point_assignments
from Backend.Benchmark.weak_labels.provenance.engine_lineage import (
    build_label_source_dependency,
    build_rule_registry,
    build_threshold_registry,
    validate_referential_integrity,
)
from Backend.Benchmark.weak_labels.lifecycle.phase_c_native.publication import (
    copy_registry_with_native_stage,
    create_staging_directory,
    publish_staging_directory,
    write_artifact_catalog,
)
from Backend.Benchmark.weak_labels.semantic.evidence.rules import evaluate_point_rules
from Backend.Benchmark.weak_labels.semantic.continuity.runs import build_observed_low_runs
from Backend.Benchmark.weak_labels.semantic.same_y.projection import build_same_y_transfer_projection
from Backend.Benchmark.weak_labels.semantic.temporal.resolver import resolve_temporal_assignments
from Backend.Benchmark.weak_labels.semantic.continuity.windows import build_window_projections


def build_native_label_artifacts(config: NativeEngineConfig) -> NativeEngineResult:
    contract = NativeContract.load(config.semantic_contract_run_dir)
    for path in (
        config.canonical_evidence_schema_path,
        config.sensor_dependency_registry_path,
        config.segment_manifest_path,
        config.expected_difference_contract_path,
    ):
        if not path.resolve().exists():
            raise NativeContractError(f"Native engine input is missing: {path}")
    _validate_supporting_inputs(config)
    parent_registry = load_protocol_registry(config.protocol_registry_run_dir.resolve())
    _validate_parent_registry(parent_registry.run_manifest, contract)
    expected_hash = expected_difference_contract_hash(config.expected_difference_contract_path)
    if config.expected_difference_contract_hash is not None and expected_hash != config.expected_difference_contract_hash:
        raise NativeContractError("Expected-difference contract hash mismatch.")
    operationalization = contract.resolve_operationalization(config.operationalization_id)
    frame, input_metadata = load_e1_authorized_canonical(
        canonical_history_path=config.canonical_history_path,
        canonical_evidence_schema_path=config.canonical_evidence_schema_path,
        protocol_registry_run_dir=config.protocol_registry_run_dir,
        contract=contract,
    )
    frame = build_continuity_primitives(frame, contract)
    frame = build_derived_evidence(frame, contract)
    rule_states, rule_firings = evaluate_point_rules(frame, contract, operationalization)
    point_resolutions, point_assignments = resolve_point_assignments(frame, rule_states, rule_firings, contract, operationalization)
    run_frame = build_observed_low_runs(frame, point_assignments, contract, operationalization)
    frame = frame.merge(run_frame, on="record.id", how="left", validate="one_to_one")
    window_projections = build_window_projections(frame, point_assignments, contract, operationalization)
    temporal_outputs: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {}
    same_y_outputs: dict[str, pd.DataFrame] = {}
    for horizon, projection in window_projections.items():
        resolutions, assignments = resolve_temporal_assignments(
            frame,
            point_assignments,
            projection,
            run_frame,
            contract,
            operationalization,
            horizon,
        )
        temporal_outputs[horizon] = (resolutions, assignments)
        same_y_outputs[horizon] = build_same_y_transfer_projection(point_assignments, projection, contract, operationalization, horizon)
    all_resolutions = pd.concat([point_resolutions, *[value[0] for value in temporal_outputs.values()]], ignore_index=True).convert_dtypes()
    all_assignments = pd.concat([point_assignments, *[value[1] for value in temporal_outputs.values()]], ignore_index=True).convert_dtypes()
    intrinsic = build_intrinsic_candidate_assignments(all_assignments)
    fold_projection = build_semantic_fold_projection(point_assignments, parent_registry.e1_fold_registry)
    integrity = validate_referential_integrity(
        canonical=frame,
        rule_firings=rule_firings,
        resolutions=all_resolutions,
        assignments=all_assignments,
        same_y_transfers=list(same_y_outputs.values()),
    )
    run_id = f"native_engine_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}"
    staging = create_staging_directory(config.output_root, run_id)
    try:
        _write_artifacts(
            staging=staging,
            frame=frame,
            rule_firings=rule_firings,
            point_resolutions=point_resolutions,
            point_assignments=point_assignments,
            all_resolutions=all_resolutions,
            all_assignments=all_assignments,
            intrinsic=intrinsic,
            fold_projection=fold_projection,
            windows=window_projections,
            temporal_outputs=temporal_outputs,
            same_y_outputs=same_y_outputs,
            contract=contract,
            operationalization=operationalization,
            expected_difference_hash=expected_hash,
            input_metadata=input_metadata,
            integrity=integrity,
            config=config,
        )
        _write_manifest_hash(staging, contract, operationalization, expected_hash)
        write_artifact_catalog(staging)
        final_dir = publish_staging_directory(staging, config.output_root.resolve() / run_id, staging / "run_metadata" / "run_manifest.json")
    except Exception:
        (staging / "FAILED").write_text("native engine publication failed\n", encoding="utf-8")
        raise
    return NativeEngineResult(run_id, final_dir, "PASS", str(operationalization["operationalization_id"]), len(frame))


def load_native_contract(semantic_contract_run_dir: Path) -> NativeContract:
    return NativeContract.load(semantic_contract_run_dir)


def build_native_engine_registry(frozen_registry_run_dir: Path, native_engine_run_dir: Path) -> Path:
    """Create an additive registry only after a successful native publication."""
    native_engine_run_dir = native_engine_run_dir.resolve()
    marker = native_engine_run_dir / "publication_success_marker.json"
    if not marker.exists():
        raise NativeContractError("Native engine registry requires publication_success_marker.json.")
    parent = frozen_registry_run_dir.resolve()
    target = parent.parent / f"protocol_registry_native_engine_{native_engine_run_dir.name.removeprefix('native_engine_')}"
    return copy_registry_with_native_stage(parent, target, native_engine_run_dir)


def _validate_parent_registry(manifest: dict[str, object], contract: NativeContract) -> None:
    if not bool(manifest.get("semantic_contract_frozen", False)):
        raise NativeContractError("Native engine requires semantic_contract_frozen=true.")
    if bool(manifest.get("native_engine_implemented", False)):
        raise NativeContractError("Native engine input registry must be the pre-native frozen registry.")
    if bool(manifest.get("downstream_runners_unlocked", False)):
        raise NativeContractError("Native engine cannot run with downstream runners unlocked.")
    if manifest.get("semantic_contract_hash") not in {None, contract.semantic_contract_hash}:
        raise NativeContractError("Parent registry and semantic contract hashes do not match.")


def _validate_supporting_inputs(config: NativeEngineConfig) -> None:
    schema = pd.read_csv(config.canonical_evidence_schema_path.resolve())
    if schema.empty:
        raise NativeContractError("Canonical evidence schema cannot be empty.")
    dependency = pd.read_csv(config.sensor_dependency_registry_path.resolve())
    if dependency.empty:
        raise NativeContractError("Sensor dependency registry cannot be empty.")
    payload = json.loads(config.segment_manifest_path.resolve().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise NativeContractError("Segment manifest must contain a JSON object.")


def _write_artifacts(*, staging: Path, frame: pd.DataFrame, rule_firings: pd.DataFrame, point_resolutions: pd.DataFrame, point_assignments: pd.DataFrame, all_resolutions: pd.DataFrame, all_assignments: pd.DataFrame, intrinsic: pd.DataFrame, fold_projection: pd.DataFrame, windows: dict[str, pd.DataFrame], temporal_outputs: dict[str, tuple[pd.DataFrame, pd.DataFrame]], same_y_outputs: dict[str, pd.DataFrame], contract: NativeContract, operationalization: pd.Series, expected_difference_hash: str, input_metadata: dict[str, object], integrity: dict[str, int], config: NativeEngineConfig) -> None:
    (staging / "tasks" / "point").mkdir(parents=True, exist_ok=True)
    for directory in ("same_y", "temporal_anchor", "cohorts", "audit", "run_metadata"):
        (staging / directory).mkdir(parents=True, exist_ok=True)
    point_evidence = rule_firings.merge(frame[["record.id", "sample_time_utc", "environment_id"]], left_on="sample_id", right_on="record.id", how="left", validate="many_to_one")
    point_evidence.to_parquet(staging / "tasks" / "point" / "evidence.parquet", index=False)
    materialize_from_assignments(point_assignments).to_parquet(staging / "tasks" / "point" / "assignments_detailed.parquet", index=False)
    intrinsic.to_parquet(staging / "tasks" / "point" / "assignments_intrinsic_candidate.parquet", index=False)
    for horizon, projection in windows.items():
        (staging / "temporal_anchor" / f"horizon_{horizon}").mkdir(parents=True, exist_ok=True)
        projection.to_parquet(staging / "temporal_anchor" / f"horizon_{horizon}" / "evidence.parquet", index=False)
        temporal_outputs[horizon][1].to_parquet(staging / "temporal_anchor" / f"horizon_{horizon}" / "assignments.parquet", index=False)
        (staging / "same_y" / f"horizon_{horizon}").mkdir(parents=True, exist_ok=True)
        same_y_outputs[horizon].to_parquet(staging / "same_y" / f"horizon_{horizon}" / "label_transfer_projection.parquet", index=False)
    intrinsic.to_parquet(staging / "cohorts" / "intrinsic_eligibility.parquet", index=False)
    fold_projection.to_parquet(staging / "cohorts" / "semantic_fold_projection_manifest.parquet", index=False)
    rule_firings.to_parquet(staging / "audit" / "rule_firings.parquet", index=False)
    all_resolutions.to_parquet(staging / "audit" / "resolutions.parquet", index=False)
    all_assignments.to_parquet(staging / "audit" / "assignments.parquet", index=False)
    build_continuity_registry(frame).to_parquet(staging / "audit" / "continuity_registry.parquet", index=False)
    build_rule_registry(rule_firings).to_csv(staging / "audit" / "rule_registry.csv", index=False)
    build_threshold_registry(rule_firings).to_csv(staging / "audit" / "threshold_registry.csv", index=False)
    build_label_source_dependency(contract).to_csv(staging / "audit" / "label_source_dependency.csv", index=False)
    metadata = {
        "pipeline": "weak_labels_native_engine",
        "phase": "PHASE_C_NATIVE_ENGINE",
        "semantic_contract_id": contract.semantic_contract_id,
        "semantic_contract_hash": contract.semantic_contract_hash,
        "operationalization_id": str(operationalization["operationalization_id"]),
        "expected_difference_contract_hash": expected_difference_hash,
        "input_metadata": input_metadata,
        "integrity": integrity,
        "e2_sensitive_rows_loaded": 0,
        "e3_sensitive_rows_loaded": 0,
        "model_training_performed": False,
        "downstream_runners_unlocked": False,
        "engine_mode": config.engine_mode,
    }
    (staging / "run_metadata" / "native_engine_validation.yaml").write_text(json.dumps(metadata, indent=2, ensure_ascii=True), encoding="utf-8")
    (staging / "run_metadata" / "run_manifest.json").write_text(json.dumps({**metadata, "native_engine_run_hash": stable_digest(metadata)}, indent=2, ensure_ascii=True), encoding="utf-8")


def _write_manifest_hash(staging: Path, contract: NativeContract, operationalization: pd.Series, expected_hash: str) -> None:
    manifest_path = staging / "run_metadata" / "run_manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["expected_difference_contract_hash"] = expected_hash
    payload["native_engine_run_hash"] = stable_digest({"semantic_contract_hash": contract.semantic_contract_hash, "operationalization_id": str(operationalization["operationalization_id"]), "expected_difference_contract_hash": expected_hash})
    manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True), encoding="utf-8")
