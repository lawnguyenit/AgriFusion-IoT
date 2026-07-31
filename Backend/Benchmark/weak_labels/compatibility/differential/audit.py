from __future__ import annotations

from pathlib import Path

import pandas as pd

from Backend.Benchmark.common.digests import file_sha256
from Backend.Benchmark.weak_labels.contracts.native import DifferentialAuditResult, deterministic_id


def build_shadow_differential_audit(
    *,
    native_assignments: pd.DataFrame,
    legacy_assignments: pd.DataFrame,
    expected_difference_contract_path: Path,
    output_dir: Path,
    expected_contract_hash: str | None = None,
) -> DifferentialAuditResult:
    expected_difference_contract_path = expected_difference_contract_path.resolve()
    if not expected_difference_contract_path.exists():
        raise FileNotFoundError(expected_difference_contract_path)
    actual_hash = file_sha256(expected_difference_contract_path)
    if expected_contract_hash is not None and actual_hash != expected_contract_hash:
        raise ValueError("Expected-difference contract hash mismatch.")
    contract = pd.read_csv(expected_difference_contract_path).convert_dtypes()
    required = {"difference_type", "priority", "required_old_state", "required_new_state", "required_evidence_condition", "authority_decision_id"}
    missing = required - set(contract.columns)
    if missing:
        raise ValueError(f"Expected-difference contract is incomplete: {sorted(missing)}")
    native = native_assignments.loc[:, ["sample_id", "task_id", "horizon_id", "label"]].rename(columns={"label": "native_label"})
    legacy = legacy_assignments.loc[:, ["sample_id", "task_id", "horizon_id", "label"]].rename(columns={"label": "legacy_label"})
    merged = native.merge(legacy, on=["sample_id", "task_id", "horizon_id"], how="outer", indicator=True)
    differences = merged.loc[merged["native_label"].astype("string") != merged["legacy_label"].astype("string")].copy()
    rows: list[dict[str, object]] = []
    unmatched = 0
    multiply = 0
    for row in differences.to_dict(orient="records"):
        matches = contract.loc[
            contract["required_old_state"].astype("string").isin(["*", str(row.get("legacy_label"))])
            & contract["required_new_state"].astype("string").isin(["*", str(row.get("native_label"))])
        ]
        match_count = int(len(matches))
        if match_count == 0:
            unmatched += 1
        if match_count > 1:
            multiply += 1
        selected = matches.sort_values(["priority", "authority_decision_id"], kind="stable").iloc[0] if match_count == 1 else None
        rows.append(
            {
                "sample_id": row.get("sample_id"),
                "task_id": row.get("task_id"),
                "horizon_id": row.get("horizon_id"),
                "legacy_label": row.get("legacy_label"),
                "native_label": row.get("native_label"),
                "matched_difference_count": match_count,
                "difference_status": "UNMATCHED_ENGINE_DIVERGENCE" if match_count == 0 else "AMBIGUOUS_DIFFERENCE" if match_count > 1 else "EXPECTED_DIFFERENCE",
                "primary_difference_reason": selected["difference_type"] if selected is not None else pd.NA,
                "all_difference_reasons": "|".join(matches["difference_type"].astype("string")) if match_count else pd.NA,
            }
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    report = pd.DataFrame(rows).convert_dtypes()
    report.to_parquet(output_dir / "differential_audit.parquet", index=False)
    status = "PASS" if unmatched == 0 and multiply == 0 else "FAIL"
    audit_id = deterministic_id({"object_type": "DIFFERENTIAL_AUDIT", "schema_version": "native.differential.v1", "expected_difference_contract_hash": actual_hash, "difference_count": len(differences)})
    return DifferentialAuditResult(audit_id, output_dir, status, unmatched, multiply)

