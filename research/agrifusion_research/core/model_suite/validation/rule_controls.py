"""Independent weak-label validation controls used by model jobs."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd


def run_rule_controls(
    *,
    evaluation_partitions: tuple[str, ...],
    partitions: dict[str, pd.DataFrame],
    label_artifact_path: Path,
    output_dir: Path,
    oracle_artifact_path: Path | None = None,
    oracle_kind: str | None = None,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for partition in evaluation_partitions:
        frame = partitions[partition].copy()
        frame["partition"] = partition
        frames.append(frame)
    evaluation_frame = pd.concat(frames, ignore_index=True).convert_dtypes() if frames else pd.DataFrame()
    if evaluation_frame.empty:
        return _write_empty(output_dir)

    artifact = pd.read_parquet(label_artifact_path).convert_dtypes()
    artifact = _normalise_label_columns(artifact)
    required = {"sample_id", "label_name", "label_status"}
    missing = required - set(artifact.columns)
    if missing:
        raise ValueError(f"Label artifact is missing positive-control columns: {sorted(missing)}")

    task_kind = _infer_task_kind(artifact)

    observed = evaluation_frame[["sample_id", "label_name", "label_status", "partition"]].copy()
    observed["sample_id"] = observed["sample_id"].astype("string")
    observed = observed.rename(columns={"label_name": "label_name_observed", "label_status": "label_status_observed"})
    artifact = artifact.loc[:, ["sample_id", "label_name", "label_status"]].copy()
    artifact["sample_id"] = artifact["sample_id"].astype("string")
    artifact = artifact.rename(columns={"label_name": "label_name_artifact", "label_status": "label_status_artifact"})
    artifact = artifact.drop_duplicates("sample_id", keep=False)
    artifact_join = observed.merge(artifact, on="sample_id", how="left", suffixes=("", "_artifact"), validate="one_to_one")
    artifact_disagreements = artifact_join.loc[
        artifact_join["label_name_observed"].astype("string") != artifact_join["label_name_artifact"].astype("string")
    ].copy()
    artifact_disagreements = artifact_disagreements.loc[artifact_disagreements["label_name_artifact"].notna()]

    audit_task_id = "TEMPORAL_ANCHOR" if task_kind == "temporal" else "POINT"
    audit_assignments = _load_task_audit(
        label_artifact_path,
        "assignments.parquet",
        "label",
        "label_audit_assignment",
        task_id=audit_task_id,
    )
    audit_resolutions = _load_task_audit(
        label_artifact_path,
        "resolutions.parquet",
        "resolved_label",
        "resolved_label_audit",
        task_id=audit_task_id,
    )
    assignment_disagreements = _compare_audit_labels(
        artifact,
        audit_assignments,
        audit_column="label_audit_assignment",
        source_name="audit_assignment",
    )
    resolution_disagreements = _compare_audit_labels(
        artifact,
        audit_resolutions,
        audit_column="resolved_label_audit",
        source_name="audit_resolution",
    )
    if not assignment_disagreements.empty:
        artifact_disagreements = pd.concat([artifact_disagreements, assignment_disagreements], ignore_index=True)
    if not resolution_disagreements.empty:
        artifact_disagreements = pd.concat([artifact_disagreements, resolution_disagreements], ignore_index=True)
    artifact_disagreements.to_parquet(output_dir / "artifact_consistency_disagreements.parquet", index=False)

    if task_kind == "temporal":
        oracle_source_path = oracle_artifact_path or label_artifact_path
        if oracle_kind == "RETROSPECTIVE_EVENT_RUN_LENGTH":
            oracle = _independent_temporal_event_oracle(
                label_artifact_path=label_artifact_path,
                oracle_artifact_path=oracle_source_path,
                sample_ids=observed["sample_id"],
            )
            oracle_source = "native point/rules+continuity+temporal/evidence+retrospective run completion"
        else:
            oracle = _independent_temporal_oracle(
                label_artifact_path=oracle_source_path,
                sample_ids=observed["sample_id"],
            )
            oracle_source = "audit/rule_firings.parquet+audit/continuity_registry.parquet+temporal/evidence.parquet"
    else:
        oracle = _independent_point_oracle(label_artifact_path=label_artifact_path, sample_ids=observed["sample_id"])
        oracle_source = "audit/rule_firings.parquet"
    oracle_join = observed.merge(oracle, on="sample_id", how="left", validate="one_to_one")
    oracle_disagreements = oracle_join.loc[
        oracle_join["label_name_observed"].astype("string") != oracle_join["oracle_label"].astype("string")
    ].copy()
    oracle_disagreements = oracle_disagreements.loc[oracle_disagreements["oracle_label"].notna()]
    oracle_disagreements.to_parquet(output_dir / "independent_oracle_disagreements.parquet", index=False)
    oracle_disagreements.to_parquet(output_dir / "disagreement_samples.parquet", index=False)

    coverage = int(len(observed))
    artifact_rate = _agreement_rate(len(artifact_disagreements), coverage)
    oracle_rate = _agreement_rate(len(oracle_disagreements), coverage)
    assignment_rate = _agreement_rate(len(assignment_disagreements), coverage)
    resolution_rate = _agreement_rate(len(resolution_disagreements), coverage)
    summary = {
        "rule_agreement_rate": oracle_rate,
        "independent_oracle_agreement_rate": oracle_rate,
        "artifact_consistency_agreement_rate": artifact_rate,
        "artifact_assignment_agreement_rate": assignment_rate,
        "artifact_resolution_agreement_rate": resolution_rate,
        "rule_disagreement_count": int(len(oracle_disagreements)),
        "artifact_consistency_disagreement_count": int(len(artifact_disagreements)),
        "coverage": coverage,
        "conflict_count": 0,
        "abstention_count": int((observed["label_status_observed"].astype("string") != "LABELED").sum()),
        "positive_control_status": (
            "PASS"
            if artifact_rate == 1.0
            and assignment_rate == 1.0
            and resolution_rate == 1.0
            and oracle_rate == 1.0
            else "FAIL"
        ),
        "oracle_source": oracle_source,
        "artifact_source": str(label_artifact_path),
    }
    (output_dir / "rule_control_summary.json").write_text(
        json.dumps(summary, ensure_ascii=True, indent=2, allow_nan=True),
        encoding="utf-8",
    )
    if summary["positive_control_status"] != "PASS":
        raise ValueError("Independent weak-label positive control disagreement detected.")
    return summary


def _normalise_label_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "label_name" not in result.columns and "label" in result.columns:
        result["label_name"] = result["label"]
    if "label_status" not in result.columns:
        result["label_status"] = result.get("train_inclusion_status", pd.Series("LABELED", index=result.index))
        result["label_status"] = result["label_status"].replace({"INCLUDED": "LABELED", "EXCLUDED": "ABSTAIN_INSUFFICIENT_EVIDENCE"})
    return result


def _infer_task_kind(frame: pd.DataFrame) -> str:
    task_ids = set(frame.get("task_id", pd.Series(dtype="string")).astype("string").str.lower().dropna())
    labels = set(frame["label_name"].astype("string").dropna())
    if any("temporal" in task_id for task_id in task_ids) or any(
        label.endswith("_at_anchor") for label in labels
    ):
        return "temporal"
    return "point"


def _independent_point_oracle(*, label_artifact_path: Path, sample_ids: pd.Series) -> pd.DataFrame:
    firing_path = _locate_rule_firings(label_artifact_path)
    firings = pd.read_parquet(firing_path).convert_dtypes()
    firings = firings.loc[
        firings["task_id"].astype("string").eq("POINT")
        & firings["sample_id"].astype("string").isin(sample_ids.astype("string"))
    ].copy()
    rows: list[dict[str, object]] = []
    for sample_id, group in firings.groupby(firings["sample_id"].astype("string"), sort=False):
        states = {
            str(rule_id): str(state)
            for rule_id, state in zip(group["rule_id"].astype("string"), group["evidence_state"].astype("string"), strict=False)
        }
        low = states.get("LOW_RELATIVE_MOISTURE", "NOT_EVALUABLE")
        auxiliary = [states.get(rule_id, "NOT_EVALUABLE") for rule_id in ("THERMAL_CONTEXT", "MOISTURE_RISE", "EC_SHIFT")]
        if low == "NOT_EVALUABLE":
            label = "point_not_evaluable"
        elif low == "POSITIVE":
            label = "low_relative_moisture_point"
        elif "POSITIVE" in auxiliary:
            label = "unresolved_environmental_evidence_point"
        elif "NOT_EVALUABLE" in auxiliary:
            label = "point_context_incomplete"
        else:
            label = "reference_context_point"
        rows.append({"sample_id": str(sample_id), "oracle_label": label})
    return pd.DataFrame(rows).convert_dtypes()


def _independent_temporal_oracle(*, label_artifact_path: Path, sample_ids: pd.Series) -> pd.DataFrame:
    firing_path = _locate_rule_firings(label_artifact_path)
    firings = pd.read_parquet(firing_path).convert_dtypes()
    all_sample_ids = firings["sample_id"].astype("string").dropna().drop_duplicates()
    point_oracle = _independent_point_oracle(
        label_artifact_path=label_artifact_path,
        sample_ids=all_sample_ids,
    )

    continuity_path = _locate_optional_audit(label_artifact_path, "continuity_registry.parquet")
    if continuity_path is None:
        raise FileNotFoundError("Independent temporal oracle requires audit/continuity_registry.parquet.")
    continuity = pd.read_parquet(continuity_path).convert_dtypes()
    required_continuity = {
        "record.id",
        "deployment_segment_id",
        "sample_time_utc",
        "strictly_consecutive_from_previous",
    }
    missing_continuity = required_continuity - set(continuity.columns)
    if missing_continuity:
        raise ValueError(
            "Temporal continuity audit is missing oracle columns: "
            f"{sorted(missing_continuity)}"
        )
    working = continuity.loc[
        :, [
            "record.id",
            "deployment_segment_id",
            "sample_time_utc",
            "strictly_consecutive_from_previous",
        ]
    ].copy()
    working = working.merge(
        point_oracle.rename(columns={"sample_id": "record.id", "oracle_label": "point_oracle_label"}),
        on="record.id",
        how="inner",
        validate="one_to_one",
    )
    working = working.sort_values(
        ["deployment_segment_id", "sample_time_utc", "record.id"],
        kind="stable",
    ).reset_index(drop=True)
    working["previous_point_oracle_label"] = working.groupby(
        "deployment_segment_id", dropna=False
    )["point_oracle_label"].shift(1)
    support_depths: list[int] = []
    current_segment: str | None = None
    current_depth = 0
    for row in working.to_dict(orient="records"):
        segment = str(row["deployment_segment_id"])
        point_label = str(row.get("point_oracle_label", ""))
        strict = (
            bool(row["strictly_consecutive_from_previous"])
            if pd.notna(row["strictly_consecutive_from_previous"])
            else False
        )
        previous_label = str(row.get("previous_point_oracle_label", ""))
        if (
            point_label == "low_relative_moisture_point"
            and strict
            and current_segment == segment
            and previous_label == "low_relative_moisture_point"
        ):
            current_depth += 1
        elif point_label == "low_relative_moisture_point":
            current_segment = segment
            current_depth = 1
        else:
            current_segment = None
            current_depth = 0
        support_depths.append(current_depth)
    working["support_depth_at_anchor"] = support_depths

    evidence_path = label_artifact_path.resolve().parent / "evidence.parquet"
    if not evidence_path.exists():
        raise FileNotFoundError(f"Independent temporal oracle requires temporal evidence: {evidence_path}")
    evidence = pd.read_parquet(evidence_path).convert_dtypes()
    if "representation_history_status" not in evidence.columns:
        raise ValueError("Temporal evidence is missing representation_history_status.")
    evidence = evidence.loc[:, ["sample_id", "representation_history_status"]].drop_duplicates(
        "sample_id", keep=False
    )
    working = working.merge(
        evidence,
        left_on="record.id",
        right_on="sample_id",
        how="left",
        validate="one_to_one",
    )

    resolution_path = _locate_optional_audit(label_artifact_path, "resolutions.parquet")
    if resolution_path is None:
        raise FileNotFoundError("Independent temporal oracle requires audit/resolutions.parquet.")
    resolutions = pd.read_parquet(resolution_path).convert_dtypes()
    label_artifact = pd.read_parquet(label_artifact_path).convert_dtypes()
    horizon_values = label_artifact.get("horizon_id", pd.Series(dtype="string")).astype("string").dropna().unique()
    if len(horizon_values) != 1:
        raise ValueError(
            "Independent temporal oracle requires exactly one artifact horizon, "
            f"found {horizon_values.tolist()}"
        )
    temporal_resolutions = resolutions.loc[
        resolutions["task_id"].astype("string").eq("TEMPORAL_ANCHOR")
        & resolutions["horizon_id"].astype("string").eq(str(horizon_values[0]))
    ].copy()
    k_values = pd.to_numeric(temporal_resolutions.get("required_k"), errors="coerce").dropna().astype(int).unique()
    if len(k_values) != 1:
        raise ValueError(f"Independent temporal oracle requires exactly one required_k, found {k_values.tolist()}.")
    required_k = int(k_values[0])

    rows: list[dict[str, object]] = []
    observed_ids = sample_ids.astype("string").dropna().drop_duplicates()
    selected = working.loc[working["record.id"].astype("string").isin(observed_ids)].copy()
    for row in selected.to_dict(orient="records"):
        point_label = str(row.get("point_oracle_label", "point_not_evaluable"))
        eligible = str(row.get("representation_history_status", "INELIGIBLE")) == "ELIGIBLE"
        support = int(row.get("support_depth_at_anchor") or 0)
        if not eligible:
            oracle_label = "window_ineligible"
        elif point_label == "low_relative_moisture_point" and support >= required_k:
            oracle_label = "persistent_low_relative_moisture_at_anchor"
        elif point_label == "low_relative_moisture_point":
            oracle_label = "unresolved_environmental_evidence_at_anchor"
        elif point_label == "unresolved_environmental_evidence_point":
            oracle_label = "unresolved_environmental_evidence_at_anchor"
        elif point_label == "point_context_incomplete":
            oracle_label = "point_context_incomplete_transfer"
        elif point_label == "reference_context_point":
            oracle_label = "reference_context_at_anchor"
        else:
            oracle_label = "point_not_evaluable"
        rows.append({"sample_id": str(row["record.id"]), "oracle_label": oracle_label})
    return pd.DataFrame(rows).convert_dtypes()


def _independent_temporal_event_oracle(
    *,
    label_artifact_path: Path,
    oracle_artifact_path: Path,
    sample_ids: pd.Series,
) -> pd.DataFrame:
    """Reconstruct the retrospective event target from native evidence.

    The target artifact is used only for the local audit comparison.  This
    oracle recomputes point rules, continuity, run completion, and eventual
    run length from the native release so the positive control does not simply
    compare a target file with itself.
    """
    firing_path = _locate_rule_firings(oracle_artifact_path)
    firings = pd.read_parquet(firing_path).convert_dtypes()
    all_sample_ids = firings["sample_id"].astype("string").dropna().drop_duplicates()
    point_oracle = _independent_point_oracle(
        label_artifact_path=oracle_artifact_path,
        sample_ids=all_sample_ids,
    )

    continuity_path = _locate_optional_audit(oracle_artifact_path, "continuity_registry.parquet")
    if continuity_path is None:
        raise FileNotFoundError("Independent event oracle requires audit/continuity_registry.parquet.")
    continuity = pd.read_parquet(continuity_path).convert_dtypes()
    required_continuity = {
        "record.id",
        "deployment_segment_id",
        "sample_time_utc",
        "strictly_consecutive_from_previous",
    }
    missing_continuity = required_continuity - set(continuity.columns)
    if missing_continuity:
        raise ValueError(f"Event oracle continuity is missing columns: {sorted(missing_continuity)}")
    working = continuity.loc[:, sorted(required_continuity)].copy()
    working = working.merge(
        point_oracle.rename(columns={"sample_id": "record.id", "oracle_label": "point_oracle_label"}),
        on="record.id",
        how="inner",
        validate="one_to_one",
    )
    working["sample_time_utc"] = pd.to_datetime(working["sample_time_utc"], utc=True, errors="coerce")
    working = working.sort_values(
        ["deployment_segment_id", "sample_time_utc", "record.id"], kind="stable"
    ).reset_index(drop=True)
    working["previous_point_oracle_label"] = working.groupby(
        "deployment_segment_id", dropna=False
    )["point_oracle_label"].shift(1)

    run_ids: list[object] = []
    support_depths: list[int] = []
    current_segment: str | None = None
    current_run_id: str | None = None
    current_depth = 0
    for row in working.to_dict(orient="records"):
        segment = str(row["deployment_segment_id"])
        point_label = str(row.get("point_oracle_label", ""))
        strict = bool(row["strictly_consecutive_from_previous"]) if pd.notna(
            row["strictly_consecutive_from_previous"]
        ) else False
        previous_label = str(row.get("previous_point_oracle_label", ""))
        if (
            point_label == "low_relative_moisture_point"
            and strict
            and current_segment == segment
            and previous_label == "low_relative_moisture_point"
        ):
            current_depth += 1
        elif point_label == "low_relative_moisture_point":
            current_segment = segment
            current_depth = 1
            current_run_id = f"{segment}|{row['record.id']}"
        else:
            current_segment = None
            current_run_id = None
            current_depth = 0
        run_ids.append(current_run_id if current_run_id is not None else pd.NA)
        support_depths.append(current_depth)
    working["event_run_id"] = pd.Series(run_ids, dtype="string")
    working["support_depth_at_anchor"] = pd.Series(support_depths, dtype="Int64")
    run_stats = (
        working.loc[working["event_run_id"].notna()]
        .groupby("event_run_id", dropna=False)
        .agg(
            run_end_record_id=("record.id", "last"),
            eventual_run_length=("support_depth_at_anchor", "max"),
            deployment_segment_id=("deployment_segment_id", "first"),
        )
        .reset_index()
    )
    last_record_by_segment = working.groupby("deployment_segment_id", dropna=False)["record.id"].last().to_dict()
    run_stats["run_complete"] = run_stats.apply(
        lambda row: str(row["run_end_record_id"])
        != str(last_record_by_segment.get(row["deployment_segment_id"])),
        axis=1,
    )
    working = working.merge(
        run_stats.loc[:, ["event_run_id", "eventual_run_length", "run_complete"]],
        on="event_run_id",
        how="left",
        validate="many_to_one",
    )

    evidence_path = oracle_artifact_path.resolve().parent / "evidence.parquet"
    if not evidence_path.exists():
        raise FileNotFoundError(f"Independent event oracle requires temporal evidence: {evidence_path}")
    evidence = pd.read_parquet(evidence_path).convert_dtypes()
    if "representation_history_status" not in evidence.columns:
        raise ValueError("Temporal evidence is missing representation_history_status.")
    evidence = evidence.loc[:, ["sample_id", "representation_history_status"]].drop_duplicates(
        "sample_id", keep=False
    )
    working = working.merge(
        evidence,
        left_on="record.id",
        right_on="sample_id",
        how="left",
        validate="one_to_one",
    )

    resolution_path = _locate_optional_audit(oracle_artifact_path, "resolutions.parquet")
    if resolution_path is None:
        raise FileNotFoundError("Independent event oracle requires audit/resolutions.parquet.")
    resolutions = pd.read_parquet(resolution_path).convert_dtypes()
    native_labels = pd.read_parquet(oracle_artifact_path).convert_dtypes()
    horizon_values = native_labels.get("horizon_id", pd.Series(dtype="string")).astype("string").dropna().unique()
    if len(horizon_values) != 1:
        raise ValueError(f"Event oracle requires exactly one horizon, found {horizon_values.tolist()}")
    temporal_resolutions = resolutions.loc[
        resolutions["task_id"].astype("string").eq("TEMPORAL_ANCHOR")
        & resolutions["horizon_id"].astype("string").eq(str(horizon_values[0]))
    ].copy()
    k_values = pd.to_numeric(temporal_resolutions.get("required_k"), errors="coerce").dropna().astype(int).unique()
    if len(k_values) != 1:
        raise ValueError(f"Event oracle requires exactly one required_k, found {k_values.tolist()}")
    required_k = int(k_values[0])

    observed_ids = sample_ids.astype("string").dropna().drop_duplicates()
    selected = working.loc[working["record.id"].astype("string").isin(observed_ids)].copy()
    rows: list[dict[str, object]] = []
    for row in selected.to_dict(orient="records"):
        point_label = str(row.get("point_oracle_label", "point_not_evaluable"))
        eligible = str(row.get("representation_history_status", "INELIGIBLE")) == "ELIGIBLE"
        if not eligible:
            oracle_label = "window_ineligible"
        elif point_label == "low_relative_moisture_point" and not bool(row.get("run_complete", False)):
            oracle_label = "event_undetermined"
        elif (
            point_label == "low_relative_moisture_point"
            and int(row.get("eventual_run_length") or 0) >= required_k
        ):
            oracle_label = "persistent_low_relative_moisture_at_anchor"
        elif point_label == "low_relative_moisture_point":
            oracle_label = "unresolved_environmental_evidence_at_anchor"
        elif point_label == "unresolved_environmental_evidence_point":
            oracle_label = "unresolved_environmental_evidence_at_anchor"
        elif point_label == "point_context_incomplete":
            oracle_label = "point_context_incomplete_transfer"
        elif point_label == "reference_context_point":
            oracle_label = "reference_context_at_anchor"
        else:
            oracle_label = "point_not_evaluable"
        rows.append({"sample_id": str(row["record.id"]), "oracle_label": oracle_label})
    return pd.DataFrame(rows).convert_dtypes()


def _load_task_audit(
    label_artifact_path: Path,
    filename: str,
    label_column: str,
    output_column: str,
    *,
    task_id: str,
) -> pd.DataFrame:
    audit_path = _locate_optional_audit(label_artifact_path, filename)
    if audit_path is None:
        return pd.DataFrame(columns=["sample_id", label_column]).convert_dtypes()
    frame = pd.read_parquet(audit_path).convert_dtypes()
    if "task_id" in frame.columns:
        frame = frame.loc[frame["task_id"].astype("string").str.upper().eq(task_id)].copy()
    if "sample_id" not in frame.columns or label_column not in frame.columns:
        return pd.DataFrame(columns=["sample_id", label_column]).convert_dtypes()
    return (
        frame.loc[:, ["sample_id", label_column]]
        .dropna(subset=["sample_id"])
        .drop_duplicates("sample_id", keep=False)
        .rename(columns={label_column: output_column})
        .convert_dtypes()
    )


def _compare_audit_labels(
    artifact: pd.DataFrame,
    audit: pd.DataFrame,
    *,
    audit_column: str,
    source_name: str,
) -> pd.DataFrame:
    if audit.empty:
        return pd.DataFrame()
    joined = artifact.merge(audit, on="sample_id", how="inner", validate="one_to_one")
    disagreements = joined.loc[
        joined["label_name_artifact"].astype("string") != joined[audit_column].astype("string")
    ].copy()
    if disagreements.empty:
        return disagreements
    disagreements["source_name"] = source_name
    return disagreements


def _locate_rule_firings(label_artifact_path: Path) -> Path:
    """Locate the release-level rule-firing audit for any task artifact layout."""
    resolved = label_artifact_path.resolve()
    candidates = [parent / "audit" / "rule_firings.parquet" for parent in resolved.parents]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    expected = resolved.parents[-1] / "audit" / "rule_firings.parquet"
    raise FileNotFoundError(f"Independent oracle source is missing: {expected}")


def _locate_optional_audit(label_artifact_path: Path, filename: str) -> Path | None:
    resolved = label_artifact_path.resolve()
    for parent in resolved.parents:
        candidate = parent / "audit" / filename
        if candidate.exists():
            return candidate
    return None


def _agreement_rate(disagreement_count: int, coverage: int) -> float:
    return float(1.0 - disagreement_count / coverage) if coverage else math.nan


def _write_empty(output_dir: Path) -> dict[str, object]:
    summary = {
        "rule_agreement_rate": math.nan,
        "independent_oracle_agreement_rate": math.nan,
        "artifact_consistency_agreement_rate": math.nan,
        "rule_disagreement_count": 0,
        "artifact_consistency_disagreement_count": 0,
        "coverage": 0,
        "conflict_count": 0,
        "abstention_count": 0,
        "positive_control_status": "NOT_ESTIMABLE",
    }
    pd.DataFrame().to_parquet(output_dir / "artifact_consistency_disagreements.parquet", index=False)
    pd.DataFrame().to_parquet(output_dir / "independent_oracle_disagreements.parquet", index=False)
    pd.DataFrame().to_parquet(output_dir / "disagreement_samples.parquet", index=False)
    (output_dir / "rule_control_summary.json").write_text(
        json.dumps(summary, ensure_ascii=True, indent=2, allow_nan=True),
        encoding="utf-8",
    )
    return summary
