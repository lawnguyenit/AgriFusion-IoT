"""Compare synchronized fold-policy projections without freezing a choice.

This module is deliberately diagnostic.  It reads the B1 support and
distribution artifacts, reports structural safety and observed support for the
same Q×K matrix under two fold policies, and never edits boundaries or emits
labels.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml


def build_fold_policy_comparison(
    b1_decision_pack_dir: Path,
    seven_day_profile_path: Path,
    five_day_profile_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Write a synchronized 7-day/5-day comparison report.

    The report separates mechanical safety from scientific support review.  A
    provisional recommendation is emitted only from primary anchor safety;
    final fold selection remains a B2 human decision.
    """

    b1_dir = b1_decision_pack_dir.resolve()
    support_path = b1_dir / "operationalization" / "qk_fold_support.csv"
    distribution_path = b1_dir / "operationalization" / "qk_distribution_audit.parquet"
    if not support_path.exists() or not distribution_path.exists():
        raise FileNotFoundError("B1 qk_fold_support.csv and qk_distribution_audit.parquet are required.")

    support = pd.read_csv(support_path).convert_dtypes()
    distribution = pd.read_parquet(distribution_path).convert_dtypes()
    profiles = [
        ("SEVEN_DAY", _load_profile(seven_day_profile_path)),
        ("FIVE_DAY", _load_profile(five_day_profile_path)),
    ]
    rows: list[dict[str, Any]] = []
    profile_summaries: list[dict[str, Any]] = []
    for policy_label, profile in profiles:
        items = [
            {**profile["primary"], "selection_role": "PRIMARY"},
            *[{**item, "selection_role": "DIAGNOSTIC"} for item in profile["diagnostics"]],
        ]
        policy_ids = sorted({str(item["fold_policy_id"]) for item in items})
        synchronized = len(policy_ids) == 1
        profile_rows: list[dict[str, Any]] = []
        for item in items:
            q = str(item["q"])
            k = int(item["k"])
            fold_policy_id = str(item["fold_policy_id"])
            selected = support.loc[
                support["q_contract_id"].astype(str).eq(q)
                & pd.to_numeric(support["k"], errors="coerce").eq(k)
                & support["fold_policy_id"].astype(str).eq(fold_policy_id)
            ]
            distribution_rows = distribution.loc[
                distribution["q_contract_id"].astype(str).eq(q)
                & distribution["fold_policy_id"].astype(str).eq(fold_policy_id)
                & (
                    ((distribution["task_id"].astype(str).str.upper() == "POINT") & distribution["k"].isna())
                    | ((distribution["task_id"].astype(str).str.upper() != "POINT") & pd.to_numeric(distribution["k"], errors="coerce").eq(k))
                )
            ]
            row = _summarize_item(policy_label, profile["profile_id"], item, selected, distribution_rows)
            rows.append(row)
            profile_rows.append(row)
        primary = next(row for row in profile_rows if row["selection_role"] == "PRIMARY")
        matrix_safe = all(row["safety_status"] == "PASS" for row in profile_rows)
        primary_safe = primary["safety_status"] == "PASS"
        profile_summaries.append({
            "policy_label": policy_label,
            "profile_id": profile["profile_id"],
            "fold_policy_ids": policy_ids,
            "synchronized": synchronized,
            "primary_safety_status": "PASS" if primary_safe else "FAIL",
            "candidate_matrix_safety_status": "PASS" if matrix_safe else "FAIL",
            "primary_evaluation_safety_status": primary["evaluation_safety_status"],
            "candidate_matrix_evaluation_safety_status": (
                "PASS" if all(row["evaluation_safety_status"] == "PASS" for row in profile_rows) else "FAIL"
            ),
            "distribution_review_status": "REVIEW_REQUIRED",
            "primary_operationalization_id": f"{primary['q']}-K{primary['k']}",
        })

    seven = profile_summaries[0]
    five = profile_summaries[1]
    if seven["primary_safety_status"] == "PASS" and seven["candidate_matrix_safety_status"] == "PASS":
        recommendation = "E1_PRIMARY_7D_V1"
        recommendation_basis = "7-day primary and complete candidate matrix passed mechanical safety; distribution still requires B2 review."
    elif five["primary_safety_status"] == "PASS" and five["candidate_matrix_safety_status"] == "PASS":
        recommendation = "E1_DIAGNOSTIC_5D_V1_CANDIDATE"
        recommendation_basis = "7-day matrix safety failed and 5-day matrix safety passed; human approval required."
    else:
        recommendation = "REVIEW_REQUIRED"
        recommendation_basis = "At least one synchronized candidate matrix failed mechanical anchor safety; no fold policy is automatically stable."

    output = output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    table = pd.DataFrame(rows).convert_dtypes()
    table.to_csv(output / "fold_policy_comparison.csv", index=False)
    report = {
        "comparison_status": "MEASURED_REVIEW_REQUIRED",
        "profiles": profile_summaries,
        "provisional_recommendation": recommendation,
        "recommendation_basis": recommendation_basis,
        "selection_authority": "B2_HUMAN_REVIEW",
        "labels_materialized": False,
        "fold_boundaries_changed": False,
        "source_artifacts": {
            "qk_fold_support": str(support_path),
            "qk_distribution_audit": str(distribution_path),
        },
    }
    (output / "fold_policy_comparison.yaml").write_text(
        yaml.safe_dump(report, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    return report


def _load_profile(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.resolve().read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not payload.get("profile_id"):
        raise ValueError(f"Invalid fold selection profile: {path}")
    if not isinstance(payload.get("primary"), dict) or not isinstance(payload.get("diagnostics"), list):
        raise ValueError(f"Fold selection profile must contain primary and diagnostics: {path}")
    items = [payload["primary"], *payload["diagnostics"]]
    required = {"q", "k", "fold_policy_id"}
    if any(not required.issubset(item) for item in items):
        raise ValueError(f"Fold selection profile has incomplete Q×K item: {path}")
    keys = [(str(item["q"]), int(item["k"])) for item in items]
    if len(keys) != len(set(keys)):
        raise ValueError(f"Fold selection profile contains duplicate Q×K items: {path}")
    return payload


def _summarize_item(
    policy_label: str,
    profile_id: str,
    item: dict[str, Any],
    support: pd.DataFrame,
    distribution: pd.DataFrame,
) -> dict[str, Any]:
    if support.empty:
        return {
            "policy_label": policy_label,
            "profile_id": profile_id,
            "selection_role": item["selection_role"],
            "q": item["q"],
            "k": int(item["k"]),
            "fold_policy_id": item["fold_policy_id"],
            "fold_count": 0,
            "cross_split_anchor_count": None,
            "cross_deployment_anchor_count": None,
            "purge_applied": False,
            "distribution_rows": int(len(distribution)),
            "safety_status": "FAIL",
            "failure_reason": "NO_SUPPORT_ROWS",
            "evaluation_safety_status": "FAIL",
            "evaluation_failure_reason": "NO_SUPPORT_ROWS",
            "semantic_cross_split_anchor_count": None,
            "semantic_cross_deployment_anchor_count": None,
            "semantic_admissible_anchor_count": 0,
            "evaluation_admissible_anchor_count": 0,
        }
    cross_split = int(pd.to_numeric(support["cross_split_anchor_count"], errors="coerce").fillna(-1).sum())
    cross_deployment = int(pd.to_numeric(support["cross_deployment_anchor_count"], errors="coerce").fillna(-1).sum())
    semantic_cross_split = int(pd.to_numeric(
        support.get("semantic_cross_split_anchor_count", support["cross_split_anchor_count"]), errors="coerce"
    ).fillna(-1).sum())
    semantic_cross_deployment = int(pd.to_numeric(
        support.get("semantic_cross_deployment_anchor_count", support["cross_deployment_anchor_count"]), errors="coerce"
    ).fillna(-1).sum())
    purge_applied = bool(support["purge_applied"].astype(bool).all())
    fold_count = int(support["fold_id"].nunique())
    safe = fold_count > 0 and semantic_cross_split == 0 and semantic_cross_deployment == 0 and purge_applied
    evaluation_safe = fold_count > 0 and cross_split == 0 and cross_deployment == 0 and purge_applied
    reason = "PASS" if safe else ";".join(
        reason for reason, failed in (
            ("NO_FOLDS", fold_count == 0),
            ("SEMANTIC_CROSS_SPLIT", semantic_cross_split > 0),
            ("SEMANTIC_CROSS_DEPLOYMENT", semantic_cross_deployment > 0),
            ("PURGE_NOT_APPLIED", not purge_applied),
        ) if failed
    )
    evaluation_reason = "PASS" if evaluation_safe else ";".join(
        reason for reason, failed in (
            ("NO_FOLDS", fold_count == 0),
            ("FEATURE_OR_LABEL_CROSS_SPLIT", cross_split > 0),
            ("FEATURE_OR_LABEL_CROSS_DEPLOYMENT", cross_deployment > 0),
            ("PURGE_NOT_APPLIED", not purge_applied),
        ) if failed
    )
    return {
        "policy_label": policy_label,
        "profile_id": profile_id,
        "selection_role": item["selection_role"],
        "q": item["q"],
        "k": int(item["k"]),
        "fold_policy_id": item["fold_policy_id"],
        "fold_count": fold_count,
        "cross_split_anchor_count": cross_split,
        "cross_deployment_anchor_count": cross_deployment,
        "semantic_cross_split_anchor_count": semantic_cross_split,
        "semantic_cross_deployment_anchor_count": semantic_cross_deployment,
        "purge_applied": purge_applied,
        "dependency_admissible_anchor_count": int(pd.to_numeric(support["dependency_admissible_anchor_count"], errors="coerce").fillna(0).sum()),
        "semantic_admissible_anchor_count": int(pd.to_numeric(support.get("semantic_admissible_anchor_count", support["dependency_admissible_anchor_count"]), errors="coerce").fillna(0).sum()),
        "evaluation_admissible_anchor_count": int(pd.to_numeric(support.get("evaluation_admissible_anchor_count", support["dependency_admissible_anchor_count"]), errors="coerce").fillna(0).sum()),
        "distribution_rows": int(len(distribution)),
        "safety_status": "PASS" if safe else "FAIL",
        "failure_reason": reason,
        "evaluation_safety_status": "PASS" if evaluation_safe else "FAIL",
        "evaluation_failure_reason": evaluation_reason,
    }
