from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from Backend.Benchmark.common.digests import file_sha256


REQUIRED_THRESHOLD_IDS = (
    "LOW_MOISTURE_Q05_E1_DISCOVERY_CANDIDATE",
    "LOW_MOISTURE_Q10_E1_DISCOVERY_CANDIDATE",
    "LOW_MOISTURE_Q15_E1_DISCOVERY_CANDIDATE",
    "LOW_MOISTURE_Q20_E1_DISCOVERY_CANDIDATE",
    "THERMAL_VPD_FIXED_2_5_REFERENCE",
    "MOISTURE_RISE_FIXED_5PP_REFERENCE",
    "EC_SHIFT_Q95_E1_DISCOVERY_CANDIDATE",
)


@dataclass(frozen=True)
class PhaseAThresholdInputs:
    registry: pd.DataFrame
    sensitivity: pd.DataFrame
    fit_cohort: pd.DataFrame
    threshold_registry_hash: str
    threshold_sensitivity_hash: str
    fit_cohort_hash: str
    q_values: tuple[tuple[str, float], ...]
    thresholds: dict[str, float]
    fit_cohort_id: str


def load_phase_a_threshold_inputs(phase_a_run_dir: Path) -> PhaseAThresholdInputs:
    run_dir = phase_a_run_dir.resolve()
    registry_path = run_dir / "threshold_diagnostics" / "threshold_registry.csv"
    sensitivity_path = run_dir / "threshold_diagnostics" / "threshold_sensitivity.csv"
    cohort_path = run_dir / "threshold_diagnostics" / "threshold_fit_cohort_records.parquet"
    catalog_path = run_dir / "run_metadata" / "artifact_catalog.csv"
    required = (registry_path, sensitivity_path, cohort_path, catalog_path)
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Phase A threshold artifacts are missing: {missing}")

    registry = pd.read_csv(registry_path).convert_dtypes()
    sensitivity = pd.read_csv(sensitivity_path).convert_dtypes()
    fit_cohort = pd.read_parquet(cohort_path).convert_dtypes()
    catalog = pd.read_csv(catalog_path).convert_dtypes()
    catalog_path_column = "artifact_path" if "artifact_path" in catalog.columns else "relative_path"
    catalog_hash_column = "sha256" if "sha256" in catalog.columns else "file_hash"
    if catalog_path_column not in catalog.columns or catalog_hash_column not in catalog.columns:
        raise ValueError("Phase A artifact catalog lacks path/hash columns.")
    for path in (registry_path, sensitivity_path, cohort_path):
        relative = str(path.relative_to(run_dir)).replace("\\", "/")
        catalog_rows = catalog.loc[catalog[catalog_path_column].astype(str) == relative]
        if len(catalog_rows) != 1 or str(catalog_rows.iloc[0][catalog_hash_column]) != file_sha256(path):
            raise ValueError(f"Phase A artifact hash mismatch: {relative}")
    if "threshold_id" not in registry or "threshold_value" not in registry:
        raise ValueError("Phase A threshold registry lacks threshold_id/threshold_value.")
    rows = registry.loc[registry["threshold_id"].astype("string").isin(REQUIRED_THRESHOLD_IDS)].copy()
    if set(rows["threshold_id"].astype(str)) != set(REQUIRED_THRESHOLD_IDS):
        missing_ids = sorted(set(REQUIRED_THRESHOLD_IDS) - set(rows["threshold_id"].astype(str)))
        raise ValueError(f"Phase A threshold registry is incomplete: {missing_ids}")
    if rows["threshold_id"].duplicated().any():
        raise ValueError("Phase A threshold registry contains duplicate required threshold IDs.")
    if not (rows["fit_cohort_id"].astype(str).isin({"E1_DISCOVERY_TRAIN_V1", "NONE"})).all():
        raise ValueError("Phase A threshold registry contains an unexpected fit cohort.")

    threshold_values: dict[str, float] = {}
    for row in rows.itertuples(index=False):
        value = pd.to_numeric(getattr(row, "threshold_value"), errors="coerce")
        if pd.isna(value) or not pd.api.types.is_number(value):
            raise ValueError(f"Threshold is not finite: {row.threshold_id}")
        threshold_values[str(row.threshold_id)] = float(value)
    q_values = tuple(
        (f"Q{q:02d}", threshold_values[f"LOW_MOISTURE_Q{q:02d}_E1_DISCOVERY_CANDIDATE"])
        for q in (5, 10, 15, 20)
    )
    sensitivity_low = sensitivity.loc[sensitivity["threshold_family"].astype(str) == "LOW_MOISTURE"]
    if len(sensitivity_low) != 1:
        raise ValueError("Phase A sensitivity must contain exactly one LOW_MOISTURE row.")
    sensitivity_row = sensitivity_low.iloc[0]
    for q, value in q_values:
        column = q.lower()
        if column not in sensitivity_row or abs(float(sensitivity_row[column]) - value) > 1e-9:
            raise ValueError(f"Phase A sensitivity does not match threshold registry for {q}.")
    fit_cohort_id = "E1_DISCOVERY_TRAIN_V1"
    if "threshold_fit_cohort_id" in fit_cohort.columns:
        cohort_ids = set(fit_cohort["threshold_fit_cohort_id"].astype(str))
        if cohort_ids != {fit_cohort_id}:
            raise ValueError(f"Unexpected Phase A fit cohort IDs: {sorted(cohort_ids)}")
    return PhaseAThresholdInputs(
        registry=registry,
        sensitivity=sensitivity,
        fit_cohort=fit_cohort,
        threshold_registry_hash=file_sha256(registry_path),
        threshold_sensitivity_hash=file_sha256(sensitivity_path),
        fit_cohort_hash=file_sha256(cohort_path),
        q_values=q_values,
        thresholds=threshold_values,
        fit_cohort_id=fit_cohort_id,
    )


def build_candidate_threshold_audit(
    evidence: pd.DataFrame,
    applicability: pd.DataFrame,
    inputs: PhaseAThresholdInputs,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    frame = evidence.merge(
        applicability[
            [
                "record.id",
                "low_rule_applicability",
                "thermal_rule_applicability",
                "rise_rule_applicability",
                "ec_shift_rule_applicability",
            ]
        ],
        on="record.id",
        how="left",
        validate="one_to_one",
    )
    specs: list[tuple[str, str, str, str, str]] = []
    for q_id, _ in inputs.q_values:
        specs.append(
            (
                f"LOW_MOISTURE_{q_id}_E1_DISCOVERY_CANDIDATE",
                "low",
                "low_evidence_value",
                "low_rule_applicability",
                "<=",
            )
        )
    specs.extend(
        [
            ("THERMAL_VPD_FIXED_2_5_REFERENCE", "thermal", "thermal_evidence_value", "thermal_rule_applicability", ">="),
            ("MOISTURE_RISE_FIXED_5PP_REFERENCE", "moisture_rise", "moisture_rise_evidence_value", "rise_rule_applicability", ">="),
            ("EC_SHIFT_Q95_E1_DISCOVERY_CANDIDATE", "ec_shift", "ec_shift_evidence_value", "ec_shift_rule_applicability", ">="),
        ]
    )
    rows: list[dict[str, object]] = []
    boundary_rows: list[pd.DataFrame] = []
    for threshold_id, evidence_id, value_column, applicability_column, comparator in specs:
        threshold = inputs.thresholds[threshold_id]
        applicable = frame[applicability_column].fillna(False).astype(bool)
        values = pd.to_numeric(frame[value_column], errors="coerce")
        evaluable = applicable & values.notna()
        positive = values.le(threshold) if comparator == "<=" else values.ge(threshold)
        positive = positive.fillna(False) & evaluable
        equal = values.eq(threshold).fillna(False) & evaluable
        valid_values = values.loc[evaluable]
        role = str(inputs.registry.loc[inputs.registry["threshold_id"].astype(str) == threshold_id, "threshold_role"].iloc[0])
        fit_mode = str(inputs.registry.loc[inputs.registry["threshold_id"].astype(str) == threshold_id, "fit_mode"].iloc[0])
        unit = str(inputs.registry.loc[inputs.registry["threshold_id"].astype(str) == threshold_id, "threshold_unit"].iloc[0])
        rows.append(
            {
                "threshold_id": threshold_id,
                "evidence_id": evidence_id,
                "threshold_value": threshold,
                "threshold_unit": unit,
                "comparator": comparator,
                "threshold_role": role,
                "fit_mode": fit_mode,
                "fit_cohort_id": inputs.fit_cohort_id if fit_mode != "FIXED_REFERENCE" else "NONE",
                "evaluable_count": int(evaluable.sum()),
                "positive_count": int(positive.sum()),
                "positive_rate": float(positive.sum() / evaluable.sum()) if evaluable.any() else 0.0,
                "equal_to_threshold_count": int(equal.sum()),
                "missing_or_unevaluable_count": int((~evaluable).sum()),
                "min_evaluable_value": float(valid_values.min()) if not valid_values.empty else pd.NA,
                "max_evaluable_value": float(valid_values.max()) if not valid_values.empty else pd.NA,
                "zero_mass_fraction": float(valid_values.eq(0).mean()) if evidence_id == "ec_shift" and not valid_values.empty else pd.NA,
                "fit_cohort_zero_mass_fraction": (
                    float(pd.to_numeric(inputs.fit_cohort.get("ec_delta_abs_strict"), errors="coerce").dropna().eq(0).mean())
                    if evidence_id == "ec_shift" and "ec_delta_abs_strict" in inputs.fit_cohort.columns
                    and pd.to_numeric(inputs.fit_cohort["ec_delta_abs_strict"], errors="coerce").notna().any()
                    else pd.NA
                ),
                "authority_status": "CANDIDATE_ONLY",
                "review_required": True,
            }
        )
        boundary = frame.loc[equal, ["record.id", "sample_time", value_column]].copy()
        boundary["threshold_id"] = threshold_id
        boundary["evidence_id"] = evidence_id
        boundary_rows.append(boundary)
    boundaries = pd.concat(boundary_rows, ignore_index=True) if boundary_rows else pd.DataFrame()
    audit = pd.DataFrame(rows).convert_dtypes()
    status = {
        "all_thresholds_candidate_only": bool(audit["authority_status"].eq("CANDIDATE_ONLY").all()),
        "ec_shift_viability": "PHASE_B_DECISION_REQUIRED"
        if float(audit.loc[audit["evidence_id"] == "ec_shift", "zero_mass_fraction"].iloc[0] or 0) >= 0.5
        else "MEASURED",
        "thermal_fit_mode": "FIXED_REFERENCE",
        "moisture_rise_fit_mode": "FIXED_REFERENCE",
    }
    return audit, boundaries.convert_dtypes(), status
