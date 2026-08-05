"""Build reviewable candidate contracts from Phase A/B1 artifacts.

These artifacts are measurements/candidates, not frozen authority.  They keep
technical values queryable so a reviewer approves an ID instead of retyping
formulas and thresholds in ``review_decision.yaml``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from Backend.Benchmark.common.digests import file_sha256


DERIVED_CONTRACT_ID = "DERIVED_EVIDENCE_CANDIDATE_V1"
CONTINUITY_CONTRACT_ID = "STRICT_15M_PM2_V1"
WINDOW_CONTRACT_ID = "WINDOW_3H8H_OBSERVED_COVERAGE_CANDIDATE_V1"
SUPPORT_PROFILE_ID = "SUPPORT_PROFILE_OBSERVED_MIN_7D_V1"
SEMANTIC_POLICY_ID = "SEMANTIC_POLICY_CANDIDATE_V1"


def build_candidate_contract_bundle(
    phase_a_run_dir: Path,
    b1_decision_pack_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Materialize candidate contract files and return their provenance."""

    phase_a = phase_a_run_dir.resolve()
    b1 = b1_decision_pack_dir.resolve()
    output = output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    threshold_path = phase_a / "threshold_diagnostics" / "threshold_registry.csv"
    phase_a_manifest_path = phase_a / "run_metadata" / "run_manifest.json"
    distribution_path = b1 / "operationalization" / "qk_distribution_audit.parquet"
    for path in (threshold_path, phase_a_manifest_path, distribution_path):
        if not path.exists():
            raise FileNotFoundError(f"Candidate contract source is missing: {path}")

    thresholds = pd.read_csv(threshold_path).convert_dtypes()
    phase_a_manifest = json.loads(phase_a_manifest_path.read_text(encoding="utf-8"))
    derived_path = output / "derived_evidence_contract_registry.csv"
    _write_derived_contract(thresholds, derived_path)
    continuity_path = output / "continuity_contract.yaml"
    _write_continuity_contract(phase_a_manifest, continuity_path)
    window_path = output / "window_contract.yaml"
    _write_window_contract(phase_a_manifest, window_path)
    support_path = output / "support_profiles.yaml"
    _write_support_profiles(distribution_path, support_path)
    semantic_policy_path = output / "semantic_policy_candidates.yaml"
    _write_semantic_policy_candidates(semantic_policy_path)
    threshold_candidates = {}
    for row in thresholds.itertuples(index=False):
        value = pd.to_numeric(pd.Series([row.threshold_value]), errors="coerce").iloc[0]
        if pd.isna(value):
            continue
        threshold_candidates[str(row.threshold_id)] = {
            "value": float(value),
            "unit": str(row.threshold_unit),
            "source": "PHASE_A_THRESHOLD_REGISTRY",
        }
    manifest_path = output / "candidate_contract_manifest.yaml"
    provenance = {
        "derived_evidence_contract_id": DERIVED_CONTRACT_ID,
        "continuity_contract_id": CONTINUITY_CONTRACT_ID,
        "window_contract_id": WINDOW_CONTRACT_ID,
        "support_profile_id": SUPPORT_PROFILE_ID,
        "semantic_policy_id": SEMANTIC_POLICY_ID,
        "source_phase_a_run_id": phase_a_manifest.get("run_id"),
        "source_phase_a_run_dir": str(phase_a),
        "source_b1_run_id": b1.name,
        "source_b1_run_dir": str(b1),
        "source_threshold_registry_hash": file_sha256(threshold_path),
        "source_distribution_hash": file_sha256(distribution_path),
        "paths": {
            "derived_evidence": str(derived_path),
            "continuity": str(continuity_path),
            "window": str(window_path),
            "support_profiles": str(support_path),
            "semantic_policies": str(semantic_policy_path),
        },
        "threshold_candidates": threshold_candidates,
    }
    provenance["candidate_manifest_path"] = str(manifest_path)
    (manifest_path).write_text(
        yaml.safe_dump(provenance, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    provenance["candidate_manifest_hash"] = file_sha256(manifest_path)
    return provenance


def _write_derived_contract(thresholds: pd.DataFrame, path: Path) -> None:
    values = thresholds.set_index("threshold_id")["threshold_value"].to_dict()
    units = thresholds.set_index("threshold_id")["threshold_unit"].astype(str).to_dict()
    rows = [
        {
            "contract_id": DERIVED_CONTRACT_ID,
            "derived_evidence_id": "VPD_MAGNUS_V1",
            "transform_id": "VPD_MAGNUS_V1",
            "transform_version": "1",
            "source_field_ids": "sht.temp_c|sht.humidity_pct",
            "source_units": "degC|percent",
            "output_unit": "kPa",
            "formula_expression_or_formula_id": "VPD_MAGNUS",
            "previous_observation_policy": "NOT_REQUIRED",
            "absolute_value_applied": False,
            "clipping_policy": "CLIP_0_100",
            "null_policy": "NOT_EVALUABLE",
            "infinity_policy": "NOT_EVALUABLE",
            "rounding_policy": "NONE",
            "comparison_precision": "FULL_FLOAT",
            "code_reference_hash": str(thresholds.loc[thresholds["threshold_id"].astype(str).eq("THERMAL_VPD_FIXED_2_5_REFERENCE"), "code_hash"].iloc[0]),
            "threshold_id": "THERMAL_VPD_FIXED_2_5_REFERENCE",
            "threshold_value": float(values["THERMAL_VPD_FIXED_2_5_REFERENCE"]),
            "threshold_unit": units["THERMAL_VPD_FIXED_2_5_REFERENCE"],
            "comparator": ">=",
        },
        {
            "contract_id": DERIVED_CONTRACT_ID,
            "derived_evidence_id": "MOISTURE_RISE_V1",
            "transform_id": "MOISTURE_RISE_V1",
            "transform_version": "1",
            "source_field_ids": "npk.soil_moisture_pct|strict_previous",
            "source_units": "percent|percent",
            "output_unit": "percentage_points",
            "formula_expression_or_formula_id": "CURRENT_MINUS_STRICT_PREVIOUS",
            "previous_observation_policy": "STRICT_PREVIOUS_ONLY",
            "absolute_value_applied": False,
            "clipping_policy": "NONE",
            "null_policy": "NOT_EVALUABLE",
            "infinity_policy": "NOT_EVALUABLE",
            "rounding_policy": "NONE",
            "comparison_precision": "FULL_FLOAT",
            "code_reference_hash": str(thresholds.loc[thresholds["threshold_id"].astype(str).eq("MOISTURE_RISE_FIXED_5PP_REFERENCE"), "code_hash"].iloc[0]),
            "threshold_id": "MOISTURE_RISE_FIXED_5PP_REFERENCE",
            "threshold_value": float(values["MOISTURE_RISE_FIXED_5PP_REFERENCE"]),
            "threshold_unit": units["MOISTURE_RISE_FIXED_5PP_REFERENCE"],
            "comparator": ">=",
        },
        {
            "contract_id": DERIVED_CONTRACT_ID,
            "derived_evidence_id": "EC_SHIFT_ABS_V1",
            "transform_id": "EC_SHIFT_ABS_V1",
            "transform_version": "1",
            "source_field_ids": "npk.ec|strict_previous",
            "source_units": "canonical_ec_unit|canonical_ec_unit",
            "output_unit": "canonical_ec_unit",
            "formula_expression_or_formula_id": "ABS_CURRENT_MINUS_STRICT_PREVIOUS",
            "previous_observation_policy": "STRICT_PREVIOUS_ONLY",
            "absolute_value_applied": True,
            "clipping_policy": "NONE",
            "null_policy": "NOT_EVALUABLE",
            "infinity_policy": "NOT_EVALUABLE",
            "rounding_policy": "NONE",
            "comparison_precision": "FULL_FLOAT",
            "code_reference_hash": str(thresholds.loc[thresholds["threshold_id"].astype(str).eq("EC_SHIFT_Q95_E1_DISCOVERY_CANDIDATE"), "code_hash"].iloc[0]),
            "threshold_id": "EC_SHIFT_Q95_E1_DISCOVERY_CANDIDATE",
            "threshold_value": float(values["EC_SHIFT_Q95_E1_DISCOVERY_CANDIDATE"]),
            "threshold_unit": units["EC_SHIFT_Q95_E1_DISCOVERY_CANDIDATE"],
            "comparator": ">=",
        },
    ]
    pd.DataFrame(rows).to_csv(path, index=False)


def _write_continuity_contract(manifest: dict[str, Any], path: Path) -> None:
    strict = manifest.get("strict_policy", {})
    payload = {
        "contract_id": CONTINUITY_CONTRACT_ID,
        "authority_status": "CANDIDATE_ONLY",
        "source_phase_a_run_id": manifest.get("run_id"),
        "strict_continuity": {
            "policy_id": strict.get("policy_id", CONTINUITY_CONTRACT_ID),
            "min_gap_minutes": strict.get("min_gap_minutes"),
            "max_gap_minutes": strict.get("max_gap_minutes"),
            "allowed_gap_minutes": [strict.get("min_gap_minutes"), strict.get("max_gap_minutes")],
            "missing_slot_policy": "RESET",
            "k_semantics": "OBSERVATION_COUNT",
            "elapsed_duration_gate": False,
        },
        "deployment_continuity": {
            "boundary_sources": ["deployment", "position", "interruption", "manifest"],
            "cross_deployment_anchor_policy": "NOT_EVALUABLE",
        },
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _write_window_contract(manifest: dict[str, Any], path: Path) -> None:
    horizons = [int(value) for value in manifest.get("window_horizons_hours", [3, 8])]
    payload = {
        "contract_id": WINDOW_CONTRACT_ID,
        "authority_status": "CANDIDATE_ONLY",
        "source_phase_a_run_id": manifest.get("run_id"),
        "horizons_hours": horizons,
        "window_interval": {"left_boundary": "CLOSED", "right_boundary": "CLOSED"},
        "timestamp_authority": "SAMPLE_TIME_UTC",
        "nominal_cadence_minutes": 15,
        "expected_slot_formula": {
            "formula": "NOMINAL_SLOTS_PLUS_ANCHOR",
            "include_anchor": True,
            "include_left_boundary": True,
        },
        "anchor_inclusion": True,
        # E1's measured cadence is approximately 16.6 minutes rather than an
        # exact 15-minute grid.  Use the observed-timestamp semantics measured
        # by B1 so valid rows are not discarded by nominal-slot drift.
        "slot_assignment": {"method": "OBSERVED_TIMESTAMP", "tolerance_minutes": None},
        "duplicate_slot_policy": "FAIL_CLOSED",
        "coverage": {
            "numerator": "UNIQUE_VALID_OCCUPIED_SLOTS",
            "denominator": "EXPECTED_NOMINAL_SLOTS",
            "minimum_ratio": 0.75,
        },
        "max_internal_gap": {"minutes": 30},
        "tie_order": ["sample_time_utc", "record_id"],
        "review_note": "Coverage counts unique valid observations in the closed window; 0.75 and 30 are candidate reference values, not Phase A fits.",
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _write_support_profiles(distribution_path: Path, path: Path) -> None:
    frame = pd.read_parquet(distribution_path).convert_dtypes()
    mask = (
        frame["q_contract_id"].astype(str).eq("Q10")
        & frame["fold_policy_id"].astype(str).eq("E1_PRIMARY_7D_V1")
    )
    if "k" in frame.columns:
        task_names = frame["task_id"].astype(str).str.upper()
        mask &= (
            (task_names.eq("POINT") & frame["k"].isna())
            | (~task_names.eq("POINT") & frame["k"].astype("Int64").eq(3))
        )
    primary = frame.loc[mask]
    support = {}
    for task in ("POINT", "TEMPORAL", "SAME_Y"):
        rows = primary.loc[primary["task_id"].astype(str).str.upper().eq(task)]
        if rows.empty:
            support[task] = {"status": "NO_OBSERVED_ROWS"}
            continue
        if task == "POINT":
            eligible = rows.loc[rows["class_label"].astype(str).isin(["REFERENCE", "LOW", "UNRESOLVED_ENVIRONMENTAL"])]
            support[task] = {
                "observed_min_class_count": int(pd.to_numeric(eligible["class_count"], errors="coerce").min()),
                "recommended_floor": 20,
            }
        else:
            support[task] = {
                "observed_min_class_count": int(pd.to_numeric(rows["class_count"], errors="coerce").min()),
                "observed_min_cluster_count": int(pd.to_numeric(rows["unique_cluster_count"], errors="coerce").min()),
                "recommended_floor_class_count": 20,
                "recommended_floor_cluster_count": 5,
            }
            if task == "TEMPORAL":
                support[task]["observed_min_event_count"] = int(pd.to_numeric(rows["event_count"], errors="coerce").min())
                support[task]["recommended_floor_event_count"] = 5
    path.write_text(yaml.safe_dump({"profile_id": SUPPORT_PROFILE_ID, "authority_status": "CANDIDATE_ONLY", "source": str(distribution_path), "support": support}, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _write_semantic_policy_candidates(path: Path) -> None:
    """Write candidate semantic choices; B2 still requires human approval."""

    payload = {
        "policy_bundle_id": SEMANTIC_POLICY_ID,
        "authority_status": "CANDIDATE_ONLY",
        "point_ontology_policy_id": "POINT_ONTOLOGY_FULL_CONTEXT_V1",
        "point_ontology_policy": {
            "primary_train_eligible": ["REFERENCE", "LOW", "UNRESOLVED_ENVIRONMENTAL"],
            "outside_primary_train": ["POINT_CONTEXT_INCOMPLETE", "POINT_NOT_EVALUABLE"],
        },
        "temporal_ontology_policy_id": "TEMPORAL_ONTOLOGY_PERSISTENCE_V1",
        "temporal_ontology": {
            "primary_train_eligible": ["TEMPORAL_PERSISTENT_LOW"],
            "outside_primary_train": [
                "TEMPORAL_SEMANTIC_NOT_EVALUABLE",
                "TEMPORAL_POINT_UNRESOLVED_TRANSFER",
                "TEMPORAL_POINT_CONTEXT_INCOMPLETE_TRANSFER",
            ],
            "feature_history_exclusion_is_evaluation_only": True,
        },
        "resolver_policy_id": "POINT_RESOLVER_FULL_CONTEXT_V1",
        "resolver_policy": {
            "low_positive": "LOW",
            "low_negative_auxiliary_positive": "UNRESOLVED_ENVIRONMENTAL",
            "low_negative_auxiliary_missing": "POINT_CONTEXT_INCOMPLETE",
            "low_negative_all_required_negative": "REFERENCE",
        },
        "temporal_resolution_policy_id": "TEMPORAL_RESOLVER_PERSISTENCE_V1",
        "temporal_resolution_policy": {
            "window_ineligible": "TEMPORAL_WINDOW_INELIGIBLE",
            "persistent_low": "TEMPORAL_PERSISTENT_LOW",
            "insufficient_persistence": "TEMPORAL_UNRESOLVED_INSUFFICIENT_PERSISTENCE",
            "point_unresolved": "TEMPORAL_POINT_UNRESOLVED_TRANSFER",
            "point_context_incomplete": "TEMPORAL_POINT_CONTEXT_INCOMPLETE_TRANSFER",
            "point_reference": "TEMPORAL_REFERENCE_CONTEXT",
        },
        "same_y_policy_id": "SAME_Y_TRANSFER_V1",
        "same_y_policy": {
            "representation_only": True,
            "target_source": "point_assignment",
        },
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
