from __future__ import annotations

from pathlib import Path

import pandas as pd

from Backend.Benchmark.weak_labels.lifecycle.phase_b_contract.candidate_runs import (
    load_e1_geometry_frame,
)
from Backend.Benchmark.weak_labels.lifecycle.phase_b_contract.resolution import (
    build_point_contract_replay,
)


def build_qk_distribution_audit(
    canonical_history_path: Path,
    phase_a_run_dir: Path,
    protocol_registry_run_dir: Path,
    q_values: tuple[tuple[str, float], ...],
    anchor_detail: pd.DataFrame,
) -> pd.DataFrame:
    """Report candidate class distribution after semantic admissibility.

    Point distributions use intrinsic split membership. Temporal and Same-Y
    distributions use the interval-safe anchor projection produced by
    ``build_qk_anchor_safety_audits``. No feature-view eligibility is inferred.
    """

    phase_a = phase_a_run_dir.resolve()
    frame = load_e1_geometry_frame(
        canonical_history_path, phase_a, protocol_registry_run_dir
    )
    applicability = pd.read_parquet(
        phase_a / "technical_applicability" / "rule_applicability.parquet"
    )
    primitive = pd.read_parquet(
        phase_a / "evidence_inventory" / "e1_primitive_evidence.parquet"
    )
    folds = pd.read_parquet(
        protocol_registry_run_dir.resolve() / "folds" / "e1_fold_registry.parquet"
    )
    folds = folds.loc[folds["evaluation_usable"].fillna(False).astype(bool)].copy()
    rows: list[pd.DataFrame] = []

    for q_id, threshold in q_values:
        point = _build_candidate_point_replay(frame, applicability, primitive, q_id, threshold)
        rows.append(_build_point_distribution(point, frame, folds, q_id, threshold))
        detail = anchor_detail.loc[anchor_detail["q_contract_id"].eq(q_id)].copy()
        if detail.empty:
            continue
        detail = detail.merge(
            point[["record.id", "point_resolution", "candidate_train_eligibility"]],
            left_on="record_id",
            right_on="record.id",
            how="left",
            validate="many_to_one",
        )
        rows.append(_build_temporal_distribution(detail))
        rows.append(_build_same_y_distribution(detail))

    result = pd.concat(rows, ignore_index=True).convert_dtypes()
    result["k"] = result["persistence_k"]
    result["class_label"] = result["class_name"]
    result["authority_status"] = "CANDIDATE_ONLY"
    result["review_required"] = True
    return result


def _build_candidate_point_replay(
    frame: pd.DataFrame,
    applicability: pd.DataFrame,
    primitive: pd.DataFrame,
    q_id: str,
    threshold: float,
) -> pd.DataFrame:
    moisture = frame[["record.id", "npk.soil_moisture_pct"]].copy()
    moisture["moisture_value"] = pd.to_numeric(
        moisture["npk.soil_moisture_pct"], errors="coerce"
    )
    point_primitive = primitive.copy()
    point_primitive = point_primitive.drop(columns=["low_flag"], errors="ignore").merge(
        moisture[["record.id", "moisture_value"]],
        on="record.id",
        how="left",
        validate="one_to_one",
    )
    point_primitive = point_primitive.merge(
        applicability[["record.id", "low_target_eligibility"]],
        on="record.id",
        how="left",
        validate="one_to_one",
    )
    evaluable = point_primitive["low_target_eligibility"].fillna(False).astype(bool) & point_primitive[
        "moisture_value"
    ].notna()
    point_primitive["low_flag"] = pd.Series(pd.NA, index=point_primitive.index, dtype="boolean")
    point_primitive.loc[evaluable, "low_flag"] = point_primitive.loc[
        evaluable, "moisture_value"
    ].le(threshold)
    point_primitive = point_primitive.drop(
        columns=["low_target_eligibility", "moisture_value"], errors="ignore"
    )
    point, _, _ = build_point_contract_replay(applicability, point_primitive)
    point["q_contract_id"] = q_id
    point["threshold_value"] = threshold
    return point


def _build_point_distribution(
    point: pd.DataFrame,
    frame: pd.DataFrame,
    folds: pd.DataFrame,
    q_id: str,
    threshold: float,
) -> pd.DataFrame:
    projected = point.drop(columns=["sample_time"], errors="ignore").merge(
        frame[["record.id", "sample_time", "strict_continuity_id"]],
        on="record.id",
        how="left",
        validate="one_to_one",
    )
    rows: list[dict[str, object]] = []
    for fold in folds.itertuples(index=False):
        for split in ("train", "validation", "test"):
            start = pd.to_datetime(getattr(fold, f"{split}_start"), utc=True)
            end = pd.to_datetime(getattr(fold, f"{split}_end"), utc=True)
            subset = projected.loc[
                (projected["sample_time"] >= start)
                & (projected["sample_time"] < end)
            ].copy()
            rows.extend(
                _class_rows(
                    subset,
                    {
                        "q_contract_id": q_id,
                        "threshold_value": threshold,
                        "persistence_k": pd.NA,
                        "fold_policy_id": fold.fold_policy_id,
                        "fold_id": fold.fold_id,
                        "split_role": split,
                        "task_id": "POINT",
                        "horizon_id": "NONE",
                        "support_scope": "INTRINSIC_POINT_ASSIGNMENT",
                    },
                    label_column="point_resolution",
                    admissible_column="candidate_train_eligibility",
                    event_column=None,
                )
            )
    return pd.DataFrame(rows)


def _build_temporal_distribution(detail: pd.DataFrame) -> pd.DataFrame:
    working = detail.copy()
    semantic_column = _semantic_admissibility_column(working)
    working["temporal_resolution"] = working.apply(_temporal_resolution, axis=1)
    rows: list[dict[str, object]] = []
    group_columns = [
        "q_contract_id",
        "threshold_value",
        "persistence_k",
        "fold_policy_id",
        "fold_id",
        "split_role",
        "window_horizon_hours",
    ]
    for keys, group in working.groupby(group_columns, dropna=False):
        values = dict(zip(group_columns, keys))
        values.update({"task_id": "TEMPORAL", "horizon_id": f"{keys[-1]}H"})
        values["support_scope"] = "DEPENDENCY_ADMISSIBLE_ANCHORS"
        values["raw_anchor_count"] = int(len(group))
        values["admissible_anchor_count"] = int(group[semantic_column].sum())
        values["evaluation_admissible_anchor_count"] = int(group["anchor_dependency_admissible"].sum())
        values["feature_history_excluded_count"] = int((~group["feature_history_admissible"]).sum()) if "feature_history_admissible" in group else 0
        rows.extend(_class_rows_from_group(group, values, "temporal_resolution", "observed_low_run_id", semantic_column))
    return pd.DataFrame(rows)


def _build_same_y_distribution(detail: pd.DataFrame) -> pd.DataFrame:
    working = detail.copy()
    semantic_column = _semantic_admissibility_column(working)
    working["same_y_status"] = working[semantic_column].map(
        {True: "ELIGIBLE", False: "INELIGIBLE"}
    )
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
    for keys, group in working.groupby(group_columns, dropna=False):
        values = dict(zip(group_columns, keys))
        values.update(
            {
                "task_id": "SAME_Y",
                "horizon_id": f"{keys[-1]}H",
                "support_scope": "DEPENDENCY_ADMISSIBLE_ANCHORS",
                "raw_anchor_count": int(len(group)),
                "admissible_anchor_count": int(group[semantic_column].sum()),
                "evaluation_admissible_anchor_count": int(group["anchor_dependency_admissible"].sum()),
                "feature_history_excluded_count": int((~group["feature_history_admissible"]).sum()) if "feature_history_admissible" in group else 0,
            }
        )
        rows.extend(_class_rows_from_group(group, values, "same_y_status", None, semantic_column))
    return pd.DataFrame(rows)


def _class_rows(
    subset: pd.DataFrame,
    context: dict[str, object],
    *,
    label_column: str,
    admissible_column: str,
    event_column: str | None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for label, group in subset.groupby(label_column, dropna=False):
        eligible = group.loc[group[admissible_column].fillna(False).astype(bool)]
        row = dict(context)
        row.update(
            {
                "class_name": str(label),
                "raw_class_count": int(len(group)),
                "class_count": int(len(eligible)),
                "raw_anchor_count": int(len(subset)),
                "admissible_anchor_count": int(
                    subset[admissible_column].fillna(False).astype(bool).sum()
                ),
                "unique_anchor_count": int(eligible["record.id"].nunique()),
                "event_count": int(
                    eligible[event_column].nunique() if event_column else 0
                ),
                "unique_cluster_count": int(
                    eligible["strict_continuity_id"].nunique()
                    if "strict_continuity_id" in eligible.columns
                    else 0
                ),
                "class_prevalence": (
                    float(len(eligible) / len(subset)) if len(subset) else 0.0
                ),
            }
        )
        rows.append(row)
    return rows


def _class_rows_from_group(
    group: pd.DataFrame,
    context: dict[str, object],
    label_column: str,
    event_column: str | None,
    admissible_column: str = "anchor_dependency_admissible",
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for label, label_group in group.groupby(label_column, dropna=False):
        eligible = label_group.loc[label_group[admissible_column].fillna(False).astype(bool)]
        row = dict(context)
        row.update(
            {
                "class_name": str(label),
                "raw_class_count": int(len(label_group)),
                "class_count": int(len(eligible)),
                "unique_anchor_count": int(eligible["record_id"].nunique()),
                "event_count": int(
                    eligible[event_column].nunique() if event_column else 0
                ),
                "unique_cluster_count": int(
                    eligible[event_column].nunique()
                    if event_column
                    else (
                        eligible["strict_continuity_id"].nunique()
                        if "strict_continuity_id" in eligible.columns
                        else 0
                    )
                ),
                "class_prevalence": (
                    float(len(eligible) / context["admissible_anchor_count"])
                    if context["admissible_anchor_count"]
                    else 0.0
                ),
            }
        )
        rows.append(row)
    return rows


def _temporal_resolution(row: pd.Series) -> str:
    semantic_column = _semantic_admissibility_column(row)
    if not bool(row[semantic_column]):
        return "TEMPORAL_SEMANTIC_NOT_EVALUABLE"
    point = str(row["point_resolution"])
    if point == "LOW":
        return (
            "TEMPORAL_PERSISTENT_LOW"
            if int(row["run_length"]) >= int(row["persistence_k"])
            else "TEMPORAL_UNRESOLVED_INSUFFICIENT_PERSISTENCE"
        )
    if point == "UNRESOLVED_ENVIRONMENTAL":
        return "TEMPORAL_POINT_UNRESOLVED_TRANSFER"
    if point == "POINT_CONTEXT_INCOMPLETE":
        return "TEMPORAL_POINT_CONTEXT_INCOMPLETE_TRANSFER"
    if point == "REFERENCE":
        return "TEMPORAL_REFERENCE_CONTEXT"
    return "TEMPORAL_POINT_NOT_EVALUABLE"


def _semantic_admissibility_column(frame: pd.DataFrame | pd.Series) -> str:
    if isinstance(frame, pd.Series):
        return "semantic_assignment_admissible" if "semantic_assignment_admissible" in frame.index else "anchor_dependency_admissible"
    return "semantic_assignment_admissible" if "semantic_assignment_admissible" in frame.columns else "anchor_dependency_admissible"
