from __future__ import annotations

from pathlib import Path

import pandas as pd

from Backend.Benchmark.weak_labels.lifecycle.phase_b_contract.boundary_audit import (
    build_boundary_audit,
)
from Backend.Benchmark.weak_labels.lifecycle.phase_b_contract.candidate_runs import (
    build_candidate_low_frame,
    load_e1_geometry_frame,
)


def build_qk_anchor_safety_audits(
    canonical_history_path: Path,
    phase_a_run_dir: Path,
    protocol_registry_run_dir: Path,
    q_values: tuple[tuple[str, float], ...],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build interval-safe Q×K support and boundary diagnostics.

    The intrinsic Q×K geometry remains separate. This function only projects
    candidate anchors into usable folds using the Phase A dependency audit.
    Future continuation of an observed run is retained as an audit field and
    never used as a causal exclusion.
    """

    phase_a = phase_a_run_dir.resolve()
    dependency_path = phase_a / "continuity" / "evaluation_dependency_interval_audit.parquet"
    if not dependency_path.exists():
        raise FileNotFoundError(f"Missing Phase A dependency audit: {dependency_path}")
    folds_path = protocol_registry_run_dir.resolve() / "folds" / "e1_fold_registry.parquet"
    if not folds_path.exists():
        raise FileNotFoundError(f"Missing E1 fold registry: {folds_path}")

    frame = load_e1_geometry_frame(
        canonical_history_path, phase_a, protocol_registry_run_dir
    )
    dependency = pd.read_parquet(dependency_path).copy()
    folds = pd.read_parquet(folds_path).copy()
    folds = folds.loc[folds["evaluation_usable"].fillna(False).astype(bool)].copy()
    if folds.empty:
        raise ValueError("No evaluation-usable E1 folds are available for B1 safety audit.")
    dependency = _prepare_dependency_rows(dependency, folds)

    summaries: list[pd.DataFrame] = []
    anchor_rows: list[pd.DataFrame] = []
    boundary_rows: list[pd.DataFrame] = []
    for q_id, threshold in q_values:
        working, runs = build_candidate_low_frame(frame, q_id, threshold)
        candidate_map = working.loc[working["low"]].copy()
        candidate_map["q_contract_id"] = q_id
        candidate_map["threshold_value"] = threshold
        for k in sorted(dependency["persistence_k"].dropna().astype(int).unique()):
            anchors = candidate_map.loc[
                candidate_map["run_position"].ge(k)
                & candidate_map["run_length"].ge(k)
            ].copy()
            if anchors.empty:
                continue
            anchors["persistence_k"] = k
            projected = dependency.loc[dependency["persistence_k"].eq(k)].merge(
                anchors[
                    [
                        "record.id",
                        "q_contract_id",
                        "threshold_value",
                        "observed_low_run_id",
                        "run_position",
                        "run_length",
                        "strict_continuity_id",
                        "deployment_segment_id",
                    ]
                ].rename(columns={"record.id": "record_id"}),
                on="record_id",
                how="inner",
                validate="many_to_one",
            )
            if projected.empty:
                continue
            projected["candidate_anchor"] = True
            projected["anchor_dependency_admissible"] = projected[
                "evaluation_dependency_eligible"
            ].fillna(False).astype(bool)
            projected["interval_crosses_nominal_split"] = (
                projected["feature_interval_crosses_nominal_split"]
                | projected["persistence_interval_crosses_nominal_split"]
            )
            projected["purge_excluded"] = (
                projected["phase_a_dependency_crosses_split_or_purge"]
                & ~projected["interval_crosses_nominal_split"]
                & ~projected["dependency_crosses_deployment"]
            )
            projected["boundary_excluded"] = (
                projected["dependency_crosses_deployment"]
                | projected["persistence_dependency_unavailable"]
            )
            projected["cross_split_anchor"] = projected[
                "interval_crosses_nominal_split"
            ]
            projected["cross_deployment_anchor"] = projected[
                "dependency_crosses_deployment"
            ]
            projected["semantic_cross_split_anchor"] = (
                projected["persistence_interval_crosses_nominal_split"]
                | projected["persistence_dependency_unavailable"]
            )
            projected["semantic_cross_deployment_anchor"] = projected[
                "dependency_crosses_deployment"
            ]
            projected["semantic_assignment_admissible"] = ~(
                projected["semantic_cross_split_anchor"]
                | projected["semantic_cross_deployment_anchor"]
            )
            projected["feature_history_admissible"] = ~projected[
                "feature_interval_crosses_nominal_split"
            ]
            projected["crossing_cause"] = projected.apply(_crossing_cause, axis=1)
            projected["dependency_type"] = projected.apply(_dependency_type, axis=1)
            projected["exclusion_reason"] = projected["crossing_cause"].map(
                {
                    "DEPLOYMENT_BOUNDARY": "DEPLOYMENT_BOUNDARY",
                    "FEATURE_HISTORY_AND_DEPLOYMENT": "DEPLOYMENT_BOUNDARY",
                    "LABEL_DEPENDENCY_UNAVAILABLE": "LABEL_DEPENDENCY_UNAVAILABLE",
                    "FEATURE_AND_LABEL_DEPENDENCY": "LABEL_DEPENDENCY_CROSS_SPLIT",
                    "LABEL_DEPENDENCY_ONLY": "LABEL_DEPENDENCY_CROSS_SPLIT",
                    "FEATURE_HISTORY_ONLY": "FEATURE_HISTORY_ONLY",
                    "NONE": "NONE",
                }
            ).fillna("UNCLASSIFIED")
            projected["observed_run_crossing_audit"] = projected[
                "observed_run_crosses_split"
            ]
            anchor_rows.append(projected)
            summaries.append(_summarize_projected_anchors(projected))
        boundary_rows.append(build_boundary_audit(working, runs, folds, q_id, threshold))

    if not summaries:
        raise ValueError("No Q×K anchors could be projected into the E1 folds.")
    summary = pd.concat(summaries, ignore_index=True).convert_dtypes()
    summary["k"] = summary["persistence_k"]
    detail = pd.concat(anchor_rows, ignore_index=True).convert_dtypes()
    boundary = pd.concat(boundary_rows, ignore_index=True).convert_dtypes()
    return summary, detail, boundary


def aggregate_fold_support_for_b2(anchor_safety: pd.DataFrame) -> pd.DataFrame:
    """Collapse horizon-specific safety rows to one conservative B2 row.

    B2 validates one row per Q×K×fold×split. The detailed artifact keeps the
    3h/8h views; this projection uses the worst admissibility/support across
    all audited horizons so it cannot silently overstate support.
    """

    keys = [
        "q_contract_id",
        "threshold_value",
        "persistence_k",
        "fold_policy_id",
        "fold_id",
        "split_role",
    ]
    rows: list[dict[str, object]] = []
    for values, group in anchor_safety.groupby(keys, dropna=False):
        row = dict(zip(keys, values))
        policy_role = (
            str(group["fold_policy_role"].iloc[0])
            if "fold_policy_role" in group.columns
            else ("PRIMARY" if "PRIMARY" in str(row["fold_policy_id"]) else "DIAGNOSTIC")
        )
        row.update(
            {
                "k": row["persistence_k"],
                "window_horizon_hours": "ALL_AUDITED",
                "fold_policy_role": policy_role,
                "raw_anchor_count": int(group["raw_anchor_count"].max()),
                "unique_anchor_count": int(group["unique_anchor_count"].max()),
                "dependency_admissible_anchor_count": int(
                    group["dependency_admissible_anchor_count"].min()
                ),
                "semantic_admissible_anchor_count": int(
                    group["semantic_admissible_anchor_count"].min()
                ),
                "feature_history_admissible_anchor_count": int(
                    group["feature_history_admissible_anchor_count"].min()
                ),
                "evaluation_admissible_anchor_count": int(
                    group["evaluation_admissible_anchor_count"].min()
                ),
                "purge_excluded_count": int(group["purge_excluded_count"].max()),
                "boundary_excluded_count": int(group["boundary_excluded_count"].max()),
                "cross_split_anchor_count": int(group["cross_split_anchor_count"].max()),
                "cross_deployment_anchor_count": int(
                    group["cross_deployment_anchor_count"].max()
                ),
                "semantic_cross_split_anchor_count": int(
                    group["semantic_cross_split_anchor_count"].max()
                ),
                "semantic_cross_deployment_anchor_count": int(
                    group["semantic_cross_deployment_anchor_count"].max()
                ),
                "observed_run_crossing_audit_count": int(
                    group["observed_run_crossing_audit_count"].max()
                ),
                "raw_event_count": int(group["raw_event_count"].max()),
                "admissible_event_count": int(group["admissible_event_count"].min()),
                "event_count": int(group["event_count"].min()),
                "persistent_anchor_count": int(group["persistent_anchor_count"].min()),
                "purge_applied": bool(group["purge_applied"].all()),
                "evaluation_anchor_admissible": bool(
                    group["evaluation_anchor_admissible"].all()
                ),
                "semantic_assignment_admissible": bool(
                    group["semantic_assignment_admissible"].all()
                ),
                "feature_history_admissible": bool(
                    group["feature_history_admissible"].all()
                ),
                "support_scope": "DEPENDENCY_ADMISSIBLE_ACROSS_ALL_AUDITED_HORIZONS",
                "authority_status": "CANDIDATE_ONLY",
            }
        )
        rows.append(row)
    return pd.DataFrame(rows).convert_dtypes()


def _prepare_dependency_rows(dependency: pd.DataFrame, folds: pd.DataFrame) -> pd.DataFrame:
    required = {
        "record_id",
        "fold_policy_id",
        "fold_id",
        "split_role",
        "persistence_k",
        "evaluation_dependency_eligible",
        "feature_interval_crosses_split_or_purge",
        "persistence_interval_crosses_split_or_purge",
        "dependency_crosses_deployment",
        "observed_run_crosses_split",
        "persistence_dependency_start",
    }
    missing = sorted(required - set(dependency.columns))
    if missing:
        raise KeyError(f"Phase A dependency audit is missing columns: {missing}")
    fold_fields = [
        "fold_policy_id",
        "fold_id",
        "evaluation_usable",
        "train_start",
        "train_end",
        "validation_start",
        "validation_end",
        "test_start",
        "test_end",
        "purge_3h_min",
        "purge_8h_min",
    ]
    fold_frame = folds[[column for column in fold_fields if column in folds.columns]].copy()
    for column in fold_frame.columns:
        if column.endswith("_start") or column.endswith("_end"):
            fold_frame[column] = pd.to_datetime(fold_frame[column], utc=True, errors="coerce")
    dependency = dependency.merge(
        fold_frame,
        on=["fold_policy_id", "fold_id"],
        how="inner",
        validate="many_to_one",
    )
    dependency["persistence_k"] = pd.to_numeric(
        dependency["persistence_k"], errors="coerce"
    ).astype("Int64")
    dependency["split_start"] = dependency.apply(
        lambda row: row.get(f"{row['split_role']}_start"), axis=1
    )
    dependency["split_end"] = dependency.apply(
        lambda row: row.get(f"{row['split_role']}_end"), axis=1
    )
    for column in (
        "feature_dependency_start",
        "feature_dependency_end",
        "persistence_dependency_start",
        "persistence_dependency_end",
    ):
        if column in dependency.columns:
            dependency[column] = pd.to_datetime(
                dependency[column], utc=True, errors="coerce"
            )
    dependency["feature_interval_crosses_nominal_split"] = (
        dependency["feature_dependency_start"].isna()
        | dependency["feature_dependency_end"].isna()
        | (dependency["feature_dependency_start"] < dependency["split_start"])
        | (dependency["feature_dependency_end"] >= dependency["split_end"])
    )
    dependency["persistence_interval_crosses_nominal_split"] = (
        dependency["persistence_dependency_start"].isna()
        | dependency["persistence_dependency_end"].isna()
        | (dependency["persistence_dependency_start"] < dependency["split_start"])
        | (dependency["persistence_dependency_end"] >= dependency["split_end"])
    )
    dependency["persistence_dependency_unavailable"] = (
        dependency["persistence_dependency_start"].isna()
        | dependency["persistence_dependency_end"].isna()
    )
    dependency["phase_a_dependency_crosses_split_or_purge"] = (
        dependency["feature_interval_crosses_split_or_purge"].fillna(True).astype(bool)
        | dependency["persistence_interval_crosses_split_or_purge"].fillna(True).astype(bool)
    )
    for column in (
        "dependency_crosses_deployment",
        "observed_run_crosses_split",
        "evaluation_dependency_eligible",
    ):
        dependency[column] = dependency[column].fillna(False).astype(bool)
    return dependency


def _summarize_projected_anchors(projected: pd.DataFrame) -> pd.DataFrame:
    group_columns = [
        "q_contract_id",
        "threshold_value",
        "persistence_k",
        "fold_policy_id",
        "fold_id",
        "split_role",
        "window_horizon_hours",
    ]
    rows: list[dict[str, object]] = []
    for keys, group in projected.groupby(group_columns, dropna=False):
        values = dict(zip(group_columns, keys))
        policy_role = (
            str(group["fold_policy_role"].iloc[0])
            if "fold_policy_role" in group.columns
            else (
                "PRIMARY"
                if "PRIMARY" in str(values["fold_policy_id"])
                else "DIAGNOSTIC"
            )
        )
        evaluation_admissible = group["anchor_dependency_admissible"]
        semantic_admissible = group.get("semantic_assignment_admissible", evaluation_admissible)
        feature_admissible = group.get("feature_history_admissible", evaluation_admissible)
        values.update(
            {
                "raw_anchor_count": int(len(group)),
                "unique_anchor_count": int(
                    group["record_id"].nunique() if "record_id" in group.columns else len(group)
                ),
                "dependency_admissible_anchor_count": int(evaluation_admissible.sum()),
                "semantic_admissible_anchor_count": int(semantic_admissible.sum()),
                "feature_history_admissible_anchor_count": int(feature_admissible.sum()),
                "evaluation_admissible_anchor_count": int(evaluation_admissible.sum()),
                "purge_excluded_count": int(group["purge_excluded"].sum()),
                "boundary_excluded_count": int(group["boundary_excluded"].sum()),
                "cross_split_anchor_count": int(group["cross_split_anchor"].sum()),
                "cross_deployment_anchor_count": int(group["cross_deployment_anchor"].sum()),
                "semantic_cross_split_anchor_count": int(group.get("semantic_cross_split_anchor", group["cross_split_anchor"]).sum()),
                "semantic_cross_deployment_anchor_count": int(group.get("semantic_cross_deployment_anchor", group["cross_deployment_anchor"]).sum()),
                "observed_run_crossing_audit_count": int(
                    group["observed_run_crossing_audit"].sum()
                ),
                "raw_event_count": int(group["observed_low_run_id"].nunique()),
                "admissible_event_count": int(
                    group.loc[semantic_admissible, "observed_low_run_id"].nunique()
                ),
                "event_count": int(
                    group.loc[semantic_admissible, "observed_low_run_id"].nunique()
                ),
                "persistent_anchor_count": int(semantic_admissible.sum()),
                "purge_applied": True,
                "evaluation_anchor_admissible": bool(evaluation_admissible.all()),
                "semantic_assignment_admissible": bool(semantic_admissible.all()),
                "feature_history_admissible": bool(feature_admissible.all()),
                "support_scope": "DEPENDENCY_ADMISSIBLE_ANCHORS",
                "fold_policy_role": policy_role,
                "authority_status": "CANDIDATE_ONLY",
            }
        )
        rows.append(values)
    return pd.DataFrame(rows)


def _crossing_cause(row: pd.Series) -> str:
    feature = bool(row.get("feature_interval_crosses_nominal_split", False))
    persistence = bool(row.get("persistence_interval_crosses_nominal_split", False))
    deployment = bool(row.get("dependency_crosses_deployment", False))
    unavailable = bool(row.get("persistence_dependency_unavailable", False))
    if deployment and feature:
        return "FEATURE_HISTORY_AND_DEPLOYMENT"
    if deployment:
        return "DEPLOYMENT_BOUNDARY"
    if unavailable:
        return "LABEL_DEPENDENCY_UNAVAILABLE"
    if feature and persistence:
        return "FEATURE_AND_LABEL_DEPENDENCY"
    if feature:
        return "FEATURE_HISTORY_ONLY"
    if persistence:
        return "LABEL_DEPENDENCY_ONLY"
    return "NONE"


def _dependency_type(row: pd.Series) -> str:
    feature = bool(row.get("feature_interval_crosses_nominal_split", False))
    persistence = bool(row.get("persistence_interval_crosses_nominal_split", False))
    deployment = bool(row.get("dependency_crosses_deployment", False))
    if feature and persistence:
        return "COMBINED"
    if feature:
        return "FEATURE_HISTORY"
    if persistence:
        return "PERSISTENCE"
    if deployment:
        return "DEPLOYMENT"
    return "NONE"
