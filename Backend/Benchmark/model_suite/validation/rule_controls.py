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

    audit_assignments = _load_point_audit(
        label_artifact_path,
        "assignments.parquet",
        "label",
        "label_audit_assignment",
    )
    audit_resolutions = _load_point_audit(
        label_artifact_path,
        "resolutions.parquet",
        "resolved_label",
        "resolved_label_audit",
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

    oracle = _independent_point_oracle(label_artifact_path=label_artifact_path, sample_ids=observed["sample_id"])
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
        "oracle_source": "audit/rule_firings.parquet",
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


def _load_point_audit(
    label_artifact_path: Path,
    filename: str,
    label_column: str,
    output_column: str,
) -> pd.DataFrame:
    audit_path = _locate_optional_audit(label_artifact_path, filename)
    if audit_path is None:
        return pd.DataFrame(columns=["sample_id", label_column]).convert_dtypes()
    frame = pd.read_parquet(audit_path).convert_dtypes()
    if "task_id" in frame.columns:
        frame = frame.loc[frame["task_id"].astype("string").str.upper().eq("POINT")].copy()
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
