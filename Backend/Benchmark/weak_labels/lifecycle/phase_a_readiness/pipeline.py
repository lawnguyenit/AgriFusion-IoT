from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from Backend.Benchmark.common.digests import file_sha256
from Backend.Benchmark.common.provenance import resolve_code_commit
from Backend.Benchmark.protocol_registry import authorize_operation, load_protocol_registry
from Backend.Benchmark.shared.artifacts import create_run_directory, write_json, write_yaml
from Backend.Benchmark.weak_labels.lifecycle.phase_a_readiness.canonical import load_canonical_audit_inputs
from Backend.Benchmark.weak_labels.lifecycle.phase_a_readiness.continuity import (
    attach_observed_low_runs,
    build_causal_dependency_audit,
    build_continuity_audit,
)
from Backend.Benchmark.weak_labels.lifecycle.phase_a_readiness.contracts import (
    PhaseAReadinessConfig,
    PhaseAReadinessResult,
)
from Backend.Benchmark.weak_labels.lifecycle.phase_a_readiness.evidence import (
    build_candidate_evidence,
    build_candidate_resolution_report,
    build_evidence_inventory,
    build_rule_applicability,
)
from Backend.Benchmark.weak_labels.lifecycle.phase_a_readiness.gate import build_readiness_payload
from Backend.Benchmark.weak_labels.lifecycle.phase_a_readiness.persistence import (
    build_artifact_catalog,
    persist_readiness_artifacts,
    write_artifact_guide,
)
from Backend.Benchmark.weak_labels.lifecycle.phase_a_readiness.thresholds import build_threshold_diagnostics


def build_phase_a_readiness(config: PhaseAReadinessConfig) -> PhaseAReadinessResult:
    _validate_config(config)
    registry = load_protocol_registry(config.protocol_registry_run_dir)
    authorization_audit = _build_authorization_audit(registry, config.protocol_stage_id)
    _assert_e2_e3_sealed(authorization_audit)
    (
        _structural,
        e1_df,
        canonical_integrity,
        membership_audit,
        duplicate_audit,
        canonical_input_manifest,
    ) = load_canonical_audit_inputs(
        config.canonical_history_path,
        config.canonical_manifest_path,
        registry,
    )
    continuity_df, window_metrics = build_continuity_audit(
        e1_df,
        min_gap_minutes=config.strict_min_gap_minutes,
        max_gap_minutes=config.strict_max_gap_minutes,
        window_horizons_hours=config.window_horizons_hours,
    )
    applicability = build_rule_applicability(continuity_df)
    threshold_registry, threshold_sensitivity, cohort_records, threshold_provenance = (
        build_threshold_diagnostics(
            applicability,
            registry,
            baseline_run_dir=config.baseline_weak_label_run_dirs[0],
        )
    )
    evidence = attach_observed_low_runs(
        build_candidate_evidence(
            applicability,
            low_q10=_threshold_value(
                threshold_registry, "LOW_MOISTURE_Q10_E1_DISCOVERY_CANDIDATE"
            ),
            ec_q95=_threshold_value(
                threshold_registry, "EC_SHIFT_Q95_E1_DISCOVERY_CANDIDATE"
            ),
        )
    )
    dependency_audit = build_causal_dependency_audit(
        evidence,
        registry,
        window_horizons_hours=config.window_horizons_hours,
        persistence_candidates=config.persistence_candidates,
    )
    unique_inventory, fold_inventory, evidence_dependencies = build_evidence_inventory(
        evidence, registry, dependency_audit
    )
    candidate_report = build_candidate_resolution_report(evidence)
    baseline_hash_audit = _build_baseline_hash_audit(
        config.baseline_weak_label_run_dirs
    )
    legacy_findings = _build_legacy_findings(
        config.baseline_weak_label_run_dirs[0]
    )

    run_id, output_dir = create_run_directory(
        config.output_root.resolve(), prefix="phase_a_readiness"
    )
    persist_readiness_artifacts(
        output_dir=output_dir,
        registry_run_dir=registry.run_dir,
        authorization_audit=authorization_audit,
        canonical_integrity=canonical_integrity,
        membership_audit=membership_audit,
        duplicate_audit=duplicate_audit,
        canonical_input_manifest=canonical_input_manifest,
        continuity_df=continuity_df,
        window_metrics=window_metrics,
        dependency_audit=dependency_audit,
        applicability=applicability,
        threshold_registry=threshold_registry,
        threshold_sensitivity=threshold_sensitivity,
        cohort_records=cohort_records,
        threshold_provenance=threshold_provenance,
        evidence=evidence,
        unique_inventory=unique_inventory,
        fold_inventory=fold_inventory,
        evidence_dependencies=evidence_dependencies,
        candidate_report=candidate_report,
        baseline_hash_audit=baseline_hash_audit,
        legacy_findings=legacy_findings,
    )
    readiness = build_readiness_payload(
        registry=registry,
        canonical_integrity=canonical_integrity,
        duplicate_audit=duplicate_audit,
        threshold_registry=threshold_registry,
        threshold_provenance=threshold_provenance,
        unique_inventory=unique_inventory,
        evidence=evidence,
        dependency_audit=dependency_audit,
        baseline_hash_audit=baseline_hash_audit,
    )
    write_yaml(output_dir / "phase_a_readiness.yaml", readiness)
    write_json(
        output_dir / "run_metadata" / "run_manifest.json",
        _run_manifest(config, registry, run_id),
    )
    write_artifact_guide(output_dir)
    build_artifact_catalog(output_dir).to_csv(
        output_dir / "run_metadata" / "artifact_catalog.csv", index=False
    )
    return PhaseAReadinessResult(
        run_id=run_id,
        output_dir=output_dir,
        overall_status=str(readiness["phase_a_readiness"]["overall_status"]),
        e1_record_count=len(e1_df),
    )


def _validate_config(config: PhaseAReadinessConfig) -> None:
    if config.protocol_stage_id != "PHASE_A_AUDIT":
        raise ValueError("Phase A readiness only accepts protocol_stage_id=PHASE_A_AUDIT.")
    baseline_ids = {path.resolve().name for path in config.baseline_weak_label_run_dirs}
    required = {"weak_labels_20260730_125309", "weak_labels_20260730_125309_001"}
    if not required.issubset(baseline_ids):
        raise ValueError(
            "Phase A readiness requires both locked weak-label baseline runs: "
            f"{sorted(required)}"
        )


def _assert_e2_e3_sealed(authorization_audit: pd.DataFrame) -> None:
    exposed = authorization_audit.loc[
        (authorization_audit["operation"] == "inspect_sensitive")
        & authorization_audit["environment_id"].isin(
            ["E2", "E3_TARGET_PREEXPOSED"]
        )
        & authorization_audit["allowed"].fillna(False).astype(bool)
    ]
    if not exposed.empty:
        raise PermissionError(
            "Phase A visibility policy unexpectedly exposes sensitive E2/E3 data."
        )


def _threshold_value(registry: pd.DataFrame, threshold_id: str) -> float:
    rows = registry.loc[
        registry["threshold_id"].astype("string") == threshold_id,
        "threshold_value",
    ]
    if len(rows) != 1:
        raise ValueError(f"Threshold registry row is not unique: {threshold_id}")
    return float(rows.iloc[0])


def _build_authorization_audit(registry, stage_id: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for environment_id in (
        "E1",
        "E2",
        "E3_TARGET_PREEXPOSED",
        "E4_FUTURE_TARGET",
    ):
        for operation in (
            "inspect_structural",
            "inspect_sensitive",
            "fit",
            "tune",
            "evaluate",
        ):
            rows.append(
                authorize_operation(
                    registry, stage_id, environment_id, operation
                ).__dict__
            )
    return pd.DataFrame(rows).convert_dtypes()


def _build_baseline_hash_audit(run_dirs: tuple[Path, ...]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for run_dir in run_dirs:
        resolved = run_dir.resolve()
        manifest = json.loads(
            (resolved / "run_metadata" / "run_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        for relative_path, expected_hash in manifest.get(
            "output_hashes", {}
        ).items():
            normalized = Path(str(relative_path).replace("\\", "/"))
            path = resolved / normalized
            actual_hash = file_sha256(path) if path.exists() else "MISSING"
            rows.append(
                {
                    "baseline_run_id": resolved.name,
                    "relative_path": normalized.as_posix(),
                    "expected_hash": expected_hash,
                    "actual_hash": actual_hash,
                    "status": "PASS"
                    if actual_hash == expected_hash
                    else "FAIL",
                }
            )
    return pd.DataFrame(rows).convert_dtypes()


def _build_legacy_findings(baseline_run_dir: Path) -> pd.DataFrame:
    assignment = pd.read_parquet(
        baseline_run_dir.resolve() / "audit" / "label_assignment.parquet"
    )
    point = assignment.loc[
        assignment["label_task_id"].astype("string") == "v0_v1_point_detailed"
    ]
    affected = point.loc[
        point["technical_valid"].fillna(False).astype(bool)
        & point["exclusion_reason"].astype("string").eq("fully_evaluable")
        & point["assignment_status"].astype("string").eq("technical_invalid")
    ]
    return pd.DataFrame(
        [
            {
                "finding_id": "LEGACY_POINT_ASSIGNMENT_FULLY_EVALUABLE_MARKED_INVALID",
                "status": "CONFIRMED_NOT_REPAIRED_IN_PHASE_A",
                "baseline_run_id": baseline_run_dir.resolve().name,
                "affected_record_count": affected["sample_id"]
                .astype("string")
                .nunique(),
                "observed_contract": (
                    "technical_valid=true and exclusion_reason=fully_evaluable "
                    "but assignment_status=technical_invalid"
                ),
                "phase_a_action": (
                    "REPORT_ONLY_DO_NOT_USE_AS_APPLICABILITY_AUTHORITY"
                ),
            },
            {
                "finding_id": "E3_PREEXISTING_UNGOVERNED_EXPOSURE",
                "status": "CONFIRMED",
                "baseline_run_id": baseline_run_dir.resolve().name,
                "affected_record_count": pd.NA,
                "observed_contract": (
                    "Historical weak labels and evaluation artifacts include E3."
                ),
                "phase_a_action": (
                    "CLAIM_ONLY_PROTOCOL_LOCKED_TRANSPORT_REEVALUATION"
                ),
            },
        ]
    ).convert_dtypes()


def _run_manifest(config, registry, run_id: str) -> dict[str, object]:
    return {
        "pipeline": "weak_labels_phase_a_readiness",
        "run_id": run_id,
        "phase": "PHASE_A_AUDIT_ONLY",
        "protocol_registry_run_dir": str(registry.run_dir),
        "protocol_registry_contract_hash": registry.run_manifest[
            "registry_contract_hash"
        ],
        "canonical_history_path": str(config.canonical_history_path.resolve()),
        "canonical_history_hash": file_sha256(
            config.canonical_history_path.resolve()
        ),
        "baseline_weak_label_run_dirs": [
            str(path.resolve()) for path in config.baseline_weak_label_run_dirs
        ],
        "strict_policy": {
            "policy_id": "STRICT_15M_PM2_V1",
            "min_gap_minutes": config.strict_min_gap_minutes,
            "max_gap_minutes": config.strict_max_gap_minutes,
        },
        "window_horizons_hours": list(config.window_horizons_hours),
        "persistence_candidates": list(config.persistence_candidates),
        "label_behavior_modified": False,
        "model_training_performed": False,
        "candidate_outputs_consumable_by_label_engine": False,
        "code_commit": resolve_code_commit(Path(__file__).resolve().parents[4]),
    }
