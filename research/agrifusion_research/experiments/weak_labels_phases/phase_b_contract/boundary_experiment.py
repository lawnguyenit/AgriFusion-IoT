"""Non-authoritative experiment for profile-wide fold boundary resolution."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


def run_boundary_resolution_experiment(
    b1_decision_pack_dir: Path,
    seven_day_profile_path: Path,
    five_day_profile_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Measure profile-wide boundary adjustments without applying them."""

    b1 = b1_decision_pack_dir.resolve()
    detail_path = b1 / "operationalization" / "anchor_dependency_audit.parquet"
    boundary_path = b1 / "operationalization" / "qk_boundary_audit.parquet"
    if not detail_path.exists() or not boundary_path.exists():
        raise FileNotFoundError("B1 anchor and boundary audit artifacts are required.")
    detail = pd.read_parquet(detail_path).convert_dtypes()
    observed_boundary = pd.read_parquet(boundary_path).convert_dtypes()
    profiles = {
        "SEVEN_DAY": _load_profile(seven_day_profile_path),
        "FIVE_DAY": _load_profile(five_day_profile_path),
    }
    proposals: list[dict[str, Any]] = []
    event_cases: list[pd.DataFrame] = []
    summaries: list[dict[str, Any]] = []
    for profile_label, profile in profiles.items():
        items = [profile["primary"], *profile["diagnostics"]]
        qk = {(str(item["q"]), int(item["k"])) for item in items}
        policy_ids = {str(item["fold_policy_id"]) for item in items}
        if len(policy_ids) != 1:
            raise ValueError(f"Profile {profile_label} is not synchronized: {sorted(policy_ids)}")
        policy_id = next(iter(policy_ids))
        selected = detail.loc[
            detail["fold_policy_id"].astype(str).eq(policy_id)
            & detail.apply(lambda row: (str(row["q_contract_id"]), int(row["persistence_k"])) in qk, axis=1)
        ].copy()
        crossing = selected.loc[
            selected["cross_split_anchor"].astype(bool)
            | selected["cross_deployment_anchor"].astype(bool)
        ].copy()
        proposals.extend(_build_proposals(profile_label, policy_id, crossing))
        event_rows = observed_boundary.loc[
            observed_boundary["fold_policy_id"].astype(str).eq(policy_id)
            & observed_boundary["q_contract_id"].astype(str).isin({q for q, _ in qk})
            & pd.to_numeric(observed_boundary["crossing_event_count"], errors="coerce").fillna(0).gt(0)
        ]
        if not event_rows.empty:
            event_cases.append(event_rows.assign(profile_label=profile_label))
        profile_proposals = [row for row in proposals if row["profile_label"] == profile_label]
        unresolved = [row for row in profile_proposals if row["resolution_status"] == "UNRESOLVABLE_BY_FOLD_SHIFT"]
        material = [row for row in profile_proposals if row["material_shift_ge_4_percent"]]
        semantic_split = crossing["semantic_cross_split_anchor"].astype(bool) if "semantic_cross_split_anchor" in crossing else pd.Series(False, index=crossing.index)
        semantic_deployment = crossing["semantic_cross_deployment_anchor"].astype(bool) if "semantic_cross_deployment_anchor" in crossing else pd.Series(False, index=crossing.index)
        crossing_cause = crossing["crossing_cause"].astype(str) if "crossing_cause" in crossing else pd.Series("", index=crossing.index)
        summaries.append({
            "profile_label": profile_label,
            "profile_id": profile["profile_id"],
            "fold_policy_id": policy_id,
            "qk_count": len(qk),
            "crossing_anchor_rows": int(len(crossing)),
            "crossing_record_count": int(crossing["record_id"].nunique()) if not crossing.empty else 0,
            "semantic_crossing_anchor_rows": int((semantic_split | semantic_deployment).sum()),
            "semantic_crossing_record_count": int(
                crossing.loc[semantic_split | semantic_deployment, "record_id"].nunique()
            ) if not crossing.empty else 0,
            "feature_history_only_crossing_rows": int(
                (crossing_cause == "FEATURE_HISTORY_ONLY").sum()
            ) if not crossing.empty else 0,
            "observed_event_boundary_rows": int(len(event_rows)),
            "boundary_proposal_count": len(profile_proposals),
            "unresolvable_by_fold_shift_count": len(unresolved),
            "material_shift_proposal_count": len(material),
            "status": (
                "UNRESOLVABLE_DEPLOYMENT_OR_DATA_EDGE"
                if unresolved
                else "REVIEW_REQUIRED_MATERIAL_SHIFT"
                if material
                else "RESOLVABLE_CANDIDATE"
                if profile_proposals
                else "NO_CROSSING"
            ),
        })

    output = output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    proposal_frame = pd.DataFrame(proposals).convert_dtypes()
    proposal_frame.to_csv(output / "boundary_resolution_proposals.csv", index=False)
    if event_cases:
        pd.concat(event_cases, ignore_index=True).to_parquet(output / "observed_event_boundary_cases.parquet", index=False)
    report = {
        "experiment_status": "NON_AUTHORITATIVE",
        "boundary_changes_applied": False,
        "fold_registry_changed": False,
        "labels_materialized": False,
        "scope": "ALL_QK_IN_EACH_SYNCHRONIZED_PROFILE",
        "profiles": summaries,
        "interpretation": "A proposal is not a resolved fold. B2 must review and approve a profile-wide decision, then rerun B1 safety and distribution audits.",
        "source_artifacts": {
            "anchor_dependency_audit": str(detail_path),
            "qk_boundary_audit": str(boundary_path),
        },
    }
    (output / "boundary_resolution_experiment.yaml").write_text(
        yaml.safe_dump(report, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    return report


def _build_proposals(profile_label: str, policy_id: str, crossing: pd.DataFrame) -> list[dict[str, Any]]:
    if crossing.empty:
        return []
    rows: list[dict[str, Any]] = []
    for (fold_id, split_role), group in crossing.groupby(["fold_id", "split_role"], dropna=False):
        reasons: list[str] = []
        if group["dependency_crosses_deployment"].astype(bool).any():
            reasons.append("DEPLOYMENT_BOUNDARY")
        left_needed = _max_minutes_before_split(group, "split_start", "feature_dependency_start", "persistence_dependency_start")
        right_needed = _max_minutes_after_split(group, "split_end", "feature_dependency_end", "persistence_dependency_end")
        split_start = pd.to_datetime(group["split_start"], utc=True, errors="coerce")
        split_end = pd.to_datetime(group["split_end"], utc=True, errors="coerce")
        split_duration_minutes = float((split_end - split_start).dt.total_seconds().div(60).max())
        max_shift_minutes = max(left_needed, right_needed)
        shift_percent = (max_shift_minutes / split_duration_minutes * 100.0) if split_duration_minutes > 0 else float("inf")
        if left_needed > 0:
            reasons.append("MOVE_BOUNDARY_EARLIER")
        if right_needed > 0:
            reasons.append("MOVE_BOUNDARY_LATER")
        unresolvable = "DEPLOYMENT_BOUNDARY" in reasons
        rows.append({
            "profile_label": profile_label,
            "fold_policy_id": policy_id,
            "fold_id": fold_id,
            "split_role": split_role,
            "crossing_record_count": int(group["record_id"].nunique()),
            "qk_count": int(group[["q_contract_id", "persistence_k"]].drop_duplicates().shape[0]),
            "q_contracts": "|".join(sorted(group["q_contract_id"].astype(str).unique())),
            "max_shift_earlier_minutes": round(left_needed, 3),
            "max_shift_later_minutes": round(right_needed, 3),
            "max_shift_percent": round(shift_percent, 4),
            "material_shift_ge_4_percent": bool(shift_percent >= 4.0),
            "resolution_status": "UNRESOLVABLE_BY_FOLD_SHIFT" if unresolvable else "CANDIDATE_SHIFT",
            "reasons": "|".join(reasons) if reasons else "CROSS_SPLIT",
        })
    return rows


def _max_minutes_before_split(group: pd.DataFrame, split_start: str, *columns: str) -> float:
    values = []
    for column in columns:
        values.append(pd.to_datetime(group[column], utc=True, errors="coerce"))
    starts = pd.concat(values, axis=1).min(axis=1)
    boundary = pd.to_datetime(group[split_start], utc=True, errors="coerce")
    delta = (boundary - starts).dt.total_seconds().div(60)
    return float(delta.clip(lower=0).max()) if not delta.empty else 0.0


def _max_minutes_after_split(group: pd.DataFrame, split_end: str, *columns: str) -> float:
    values = []
    for column in columns:
        values.append(pd.to_datetime(group[column], utc=True, errors="coerce"))
    ends = pd.concat(values, axis=1).max(axis=1)
    boundary = pd.to_datetime(group[split_end], utc=True, errors="coerce")
    delta = (ends - boundary).dt.total_seconds().div(60)
    return float(delta.clip(lower=0).max()) if not delta.empty else 0.0


def _load_profile(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.resolve().read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not payload.get("profile_id"):
        raise ValueError(f"Invalid profile: {path}")
    if not isinstance(payload.get("primary"), dict) or not isinstance(payload.get("diagnostics"), list):
        raise ValueError(f"Profile must contain primary and diagnostics: {path}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run non-authoritative profile-wide boundary experiment.")
    parser.add_argument("--phase-b1-run-dir", type=Path, required=True)
    parser.add_argument("--seven-day-profile", type=Path, required=True)
    parser.add_argument("--five-day-profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run_boundary_resolution_experiment(
        args.phase_b1_run_dir,
        args.seven_day_profile,
        args.five_day_profile,
        args.output,
    )
    print(f"Boundary experiment: {args.output}")
    for profile in report["profiles"]:
        print(f"{profile['profile_label']}: {profile['status']}")


if __name__ == "__main__":
    main()
