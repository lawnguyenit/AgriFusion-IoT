from __future__ import annotations

from pathlib import Path

import pandas as pd

from Backend.Benchmark.common.digests import file_sha256
from Backend.Benchmark.shared.artifacts import write_json, write_text, write_yaml


def persist_readiness_artifacts(**artifacts: object) -> None:
    output_dir = Path(artifacts["output_dir"])
    registry_run_dir = Path(artifacts["registry_run_dir"])
    write_json(
        output_dir / "protocol" / "registry_link.json",
        {
            "protocol_registry_run_dir": str(registry_run_dir),
            "registry_manifest_hash": file_sha256(
                registry_run_dir / "run_metadata" / "run_manifest.json"
            ),
            "linked_stage_id": "PHASE_A_AUDIT",
        },
    )
    _write_frame(
        artifacts["authorization_audit"],
        output_dir / "protocol" / "authorization_audit.csv",
    )
    write_yaml(
        output_dir / "canonical_integrity" / "canonical_input_manifest.yaml",
        artifacts["canonical_input_manifest"],
    )
    _write_frame(
        artifacts["canonical_integrity"],
        output_dir / "canonical_integrity" / "canonical_integrity_audit.parquet",
    )
    _write_frame(
        artifacts["membership_audit"],
        output_dir / "canonical_integrity" / "environment_membership_audit.csv",
    )
    _write_frame(
        artifacts["duplicate_audit"],
        output_dir / "canonical_integrity" / "duplicate_record_audit.csv",
    )
    _write_continuity_artifacts(output_dir, artifacts)
    _write_applicability_artifact(output_dir, artifacts["applicability"])
    _write_threshold_artifacts(output_dir, artifacts)
    _write_evidence_artifacts(output_dir, artifacts)
    _write_frame(
        artifacts["baseline_hash_audit"],
        output_dir / "legacy_compatibility" / "baseline_hash_audit.csv",
    )
    _write_frame(
        artifacts["legacy_findings"],
        output_dir / "legacy_compatibility" / "legacy_contract_findings.csv",
    )


def build_artifact_catalog(output_dir: Path) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.name == "artifact_catalog.csv":
            continue
        relative = path.relative_to(output_dir)
        rows.append(
            {
                "relative_path": relative.as_posix(),
                "artifact_group": relative.parts[0],
                "file_hash": file_sha256(path),
                "authority_role": "CANDIDATE_AUDIT_ONLY"
                if relative.parts[0]
                in {"candidate_resolution", "evidence_inventory", "threshold_diagnostics"}
                else "PHASE_A_AUDIT",
                "contains_e2_e3_sensitive_payload": False,
            }
        )
    return pd.DataFrame(rows).convert_dtypes()


def write_artifact_guide(output_dir: Path) -> None:
    write_text(
        output_dir / "ARTIFACT_GUIDE.md",
        """# Phase A Readiness Artifacts

This run is audit-only. It links an upstream protocol registry, evaluates
canonical integrity and E1 candidate evidence, writes structural commitments
for sealed E2/E3 membership, and stops before changing labels or training
models.

Start with `phase_a_readiness.yaml`, then inspect
`run_metadata/artifact_catalog.csv`. Candidate resolution and threshold files
are not label authority and must not be consumed by the weak-label engine.
""",
    )


def _write_continuity_artifacts(output_dir: Path, artifacts: dict[str, object]) -> None:
    continuity_columns = [
        "record.id",
        "sample_time",
        "deployment_segment_id",
        "deployment_boundary_reason",
        "delta_from_previous_min",
        "cadence_deviation_min",
        "record.missing_slot_count",
        "strictly_consecutive_from_previous",
        "strict_continuity_id",
        "strict_break_reason",
        "strict_policy_candidate_id",
    ]
    _write_frame(
        artifacts["continuity_df"].loc[:, continuity_columns],
        output_dir / "continuity" / "strict_continuity_audit.parquet",
    )
    _write_frame(
        artifacts["window_metrics"],
        output_dir / "continuity" / "window_continuity_audit.parquet",
    )
    _write_frame(
        artifacts["dependency_audit"],
        output_dir / "continuity" / "evaluation_dependency_interval_audit.parquet",
    )


def _write_applicability_artifact(output_dir: Path, applicability: pd.DataFrame) -> None:
    columns = [
        "record.id",
        "sample_time",
        "time_integrity_ok",
        "sht_applicable",
        "soil_sensor_applicable",
        "sht_valid",
        "soil_sensor_valid",
        "soil_moisture_evaluable",
        "vpd_evaluable",
        "moisture_delta_evaluable",
        "ec_delta_evaluable",
        "low_rule_applicability",
        "thermal_rule_applicability",
        "rise_rule_applicability",
        "ec_shift_rule_applicability",
        "low_target_eligibility",
        "full_point_ontology_eligibility",
    ]
    _write_frame(
        applicability.loc[:, columns],
        output_dir / "technical_applicability" / "rule_applicability.parquet",
    )


def _write_threshold_artifacts(output_dir: Path, artifacts: dict[str, object]) -> None:
    _write_frame(
        artifacts["threshold_registry"],
        output_dir / "threshold_diagnostics" / "threshold_registry.csv",
    )
    _write_frame(
        artifacts["threshold_sensitivity"],
        output_dir / "threshold_diagnostics" / "threshold_sensitivity.csv",
    )
    _write_frame(
        artifacts["cohort_records"],
        output_dir / "threshold_diagnostics" / "threshold_fit_cohort_records.parquet",
    )
    write_json(
        output_dir / "threshold_diagnostics" / "legacy_reference_provenance.json",
        artifacts["threshold_provenance"],
    )


def _write_evidence_artifacts(output_dir: Path, artifacts: dict[str, object]) -> None:
    evidence_columns = [
        "record.id",
        "sample_time",
        "strict_continuity_id",
        "observed_low_run_id",
        "observed_low_run_length_ending_at_anchor",
        "low_flag",
        "thermal_flag",
        "moisture_rise_flag",
        "ec_shift_flag",
        "candidate_resolution",
        "candidate_resolution_policy_id",
        "evidence_contract_id",
        "low_threshold_candidate_id",
        "ec_shift_threshold_candidate_id",
        "thermal_threshold_id",
        "rise_threshold_id",
        "strict_policy_candidate_id",
    ]
    _write_frame(
        artifacts["evidence"].loc[:, evidence_columns],
        output_dir / "evidence_inventory" / "e1_primitive_evidence.parquet",
    )
    _write_frame(
        artifacts["unique_inventory"],
        output_dir / "evidence_inventory" / "point_evidence_combination_inventory_unique.csv",
    )
    _write_frame(
        artifacts["fold_inventory"],
        output_dir
        / "evidence_inventory"
        / "point_evidence_combination_inventory_fold_projection.csv",
    )
    _write_frame(
        artifacts["evidence_dependencies"],
        output_dir / "evidence_inventory" / "evidence_dependency_registry.csv",
    )
    _write_frame(
        artifacts["candidate_report"],
        output_dir / "candidate_resolution" / "candidate_resolution_report.csv",
    )


def _write_frame(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".parquet":
        frame.to_parquet(path, index=False)
    else:
        frame.to_csv(path, index=False)
