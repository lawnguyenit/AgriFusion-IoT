"""Materialize paired online/event temporal target views.

The native temporal release remains the online/current-state authority.  This
module creates an additive, provenance-rich derivative for a controlled
event-vs-online experiment.  It never mutates the native release or feature
artifacts.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from Backend.Benchmark.shared.artifacts import create_run_directory, write_json, write_text

Y_EVENT = "temporal_event_3h"
Y_ONLINE = "temporal_online_3h"
TARGET_VIEW_IDS = (Y_EVENT, Y_ONLINE)
TEMPORAL_TASK_ID = "TEMPORAL_ANCHOR"
LOW_POINT_LABEL = "low_relative_moisture_point"
AUX_POINT_LABEL = "unresolved_environmental_evidence_point"
LOW_LABEL = "persistent_low_relative_moisture_at_anchor"
UNRES_LABEL = "unresolved_environmental_evidence_at_anchor"
REF_LABEL = "reference_context_at_anchor"
WINDOW_INELIGIBLE = "window_ineligible"
EVENT_UNDETERMINED = "event_undetermined"


@dataclass(frozen=True)
class TemporalTargetViewsConfig:
    native_release_dir: Path
    output_root: Path
    horizon_id: str = "3h"
    selected_k: int | None = None


@dataclass(frozen=True)
class TemporalTargetViewsResult:
    run_id: str
    output_dir: Path
    native_row_count: int
    paired_row_count: int
    event_undetermined_count: int


def build_temporal_target_views(config: TemporalTargetViewsConfig) -> TemporalTargetViewsResult:
    release_dir = config.native_release_dir.resolve()
    if not release_dir.is_dir():
        raise FileNotFoundError(f"Native release directory does not exist: {release_dir}")
    horizon = str(config.horizon_id)
    source = _load_sources(release_dir, horizon)
    point = source["point"].loc[:, ["sample_id", "label", "label_name", "label_status", "intrinsic_eligibility", "assignment_id"]].copy()
    point["sample_id"] = point["sample_id"].astype("string")
    point = point.drop_duplicates("sample_id", keep=False)
    if point.empty:
        raise ValueError("Point assignment source has no unique sample IDs.")

    continuity = source["continuity"].loc[:, [
        "record.id", "deployment_segment_id", "sample_time_utc", "strictly_consecutive_from_previous"
    ]].copy()
    continuity["record.id"] = continuity["record.id"].astype("string")
    continuity["sample_time_utc"] = pd.to_datetime(continuity["sample_time_utc"], utc=True, errors="coerce")
    continuity = continuity.dropna(subset=["record.id", "sample_time_utc"])
    if continuity["record.id"].duplicated().any():
        raise ValueError("Continuity registry is not unique by record.id.")
    working = continuity.merge(point, left_on="record.id", right_on="sample_id", how="left", validate="one_to_one")
    working = working.sort_values(["deployment_segment_id", "sample_time_utc", "record.id"], kind="stable").reset_index(drop=True)
    run_frame = _derive_runs(working, source["temporal_resolutions"], config.selected_k)
    temporal = source["temporal"].loc[:, [
        "sample_id", "label", "label_name", "label_status", "intrinsic_eligibility", "assignment_id",
        "source_label", "semantic_assignment_admissible"
    ]].copy()
    temporal = temporal.rename(columns={"label": "online_assignment_label", "label_name": "online_label_name", "label_status": "online_label_status", "intrinsic_eligibility": "online_intrinsic_eligibility", "assignment_id": "online_assignment_id"})
    temporal["sample_id"] = temporal["sample_id"].astype("string")
    temporal = temporal.drop_duplicates("sample_id", keep=False)
    if temporal.empty:
        raise ValueError("Temporal assignment source has no unique sample IDs.")

    base = (
        run_frame.merge(temporal, on="sample_id", how="left", validate="one_to_one")
        .merge(source["origin"], on="sample_id", how="left", validate="one_to_one")
    )
    k_values = pd.to_numeric(source["temporal_resolutions"].get("required_k"), errors="coerce").dropna().astype(int).unique()
    if config.selected_k is not None:
        required_k = int(config.selected_k)
    elif len(k_values) == 1:
        required_k = int(k_values[0])
    else:
        raise ValueError(f"Expected one required K in native temporal resolutions, found {k_values.tolist()}")
    base["required_k"] = required_k
    base["online_label_name"] = base["online_label_name"].astype("string")
    base["point_label"] = base["point_label"].astype("string")
    base["online_label_status"] = base["online_label_status"].astype("string")
    base["eventual_run_length"] = pd.to_numeric(base["eventual_run_length"], errors="coerce").astype("Int64")
    base["support_depth_at_anchor"] = pd.to_numeric(base["support_depth_at_anchor"], errors="coerce").fillna(0).astype("Int64")
    base["event_label_name"] = base.apply(lambda row: _event_label(row, required_k), axis=1).astype("string")
    base["event_label_status"] = base.apply(lambda row: _event_label_status(row), axis=1).astype("string")
    base["event_intrinsic_eligibility"] = base["event_label_status"].eq("LABELED")
    base["target_pair_status"] = base.apply(lambda row: _pair_status(row), axis=1).astype("string")
    base["event_vs_online_changed"] = base["event_label_name"].ne(base["online_label_name"]) & base["target_pair_status"].eq("PAIRED")
    base["unres_origin"] = base.apply(lambda row: _derive_origin(row), axis=1).astype("string")
    base["origin_formula"] = base["unres_origin"].map({
        "UNRES_K": "M_t <= Q and d_t < K",
        "UNRES_A": "M_t > Q and E_aux+",
    }).fillna("N/A").astype("string")
    base["event_oracle_kind"] = "RETROSPECTIVE_EVENT_RUN_LENGTH"
    base["online_oracle_kind"] = "CAUSAL_SUPPORT_DEPTH"

    target_rows = _build_target_rows(base, required_k, horizon)
    paired_rows = base.loc[base["target_pair_status"].eq("PAIRED")].copy()
    run_registry = _build_run_registry(base)
    run_id, output_dir = create_run_directory(config.output_root.resolve(), prefix="temporal_event_online_target_views")
    _persist_target_files(
        output_dir=output_dir,
        target_rows=target_rows,
        run_registry=run_registry,
        base=base,
        source=source,
        required_k=required_k,
        horizon=horizon,
        run_id=run_id,
        release_dir=release_dir,
    )
    return TemporalTargetViewsResult(
        run_id=run_id,
        output_dir=output_dir,
        native_row_count=len(base),
        paired_row_count=len(paired_rows),
        event_undetermined_count=int(base["event_label_status"].eq("ABSTAIN_EVENT_UNDETERMINED").sum()),
    )


def _load_sources(release_dir: Path, horizon: str) -> dict[str, pd.DataFrame]:
    temporal_dir = release_dir / "tasks" / "temporal" / f"horizon_{horizon}"
    paths = {
        "point": release_dir / "tasks" / "point" / "assignments.parquet",
        "temporal": temporal_dir / "assignments.parquet",
        "evidence": temporal_dir / "evidence.parquet",
        "continuity": release_dir / "audit" / "continuity_registry.parquet",
        "temporal_resolutions": release_dir / "audit" / "resolutions.parquet",
        "rule_firings": release_dir / "audit" / "rule_firings.parquet",
    }
    for path in paths.values():
        if not path.exists():
            raise FileNotFoundError(f"Required target-view source is missing: {path}")
    temporal_resolutions = pd.read_parquet(paths["temporal_resolutions"]).convert_dtypes()
    temporal_resolutions = temporal_resolutions.loc[
        temporal_resolutions["task_id"].astype("string").eq(TEMPORAL_TASK_ID)
        & temporal_resolutions["horizon_id"].astype("string").eq(horizon)
    ].copy()
    temporal = pd.read_parquet(paths["temporal"]).convert_dtypes()
    temporal = temporal.loc[temporal["horizon_id"].astype("string").eq(horizon)].copy()
    point = pd.read_parquet(paths["point"]).convert_dtypes()
    continuity = pd.read_parquet(paths["continuity"]).convert_dtypes()
    evidence = pd.read_parquet(paths["evidence"]).convert_dtypes()
    firings = pd.read_parquet(paths["rule_firings"]).convert_dtypes()
    origin = _build_origin_frame(point, firings, temporal_resolutions)
    return {
        "point": point,
        "temporal": temporal,
        "evidence": evidence,
        "continuity": continuity,
        "temporal_resolutions": temporal_resolutions,
        "rule_firings": firings,
        "origin": origin,
        "paths": paths,
    }


def _derive_runs(working: pd.DataFrame, resolutions: pd.DataFrame, selected_k: int | None) -> pd.DataFrame:
    previous_labels = working.groupby("deployment_segment_id", dropna=False)["label"].shift(1).astype("string")
    working["previous_point_label"] = previous_labels
    run_ids: list[object] = []
    support_depths: list[int] = []
    current_segment: str | None = None
    current_run_id: str | None = None
    current_depth = 0
    run_starts: dict[str, str] = {}
    for row in working.to_dict("records"):
        segment = str(row["deployment_segment_id"])
        point_label = str(row.get("label", ""))
        strict = bool(row.get("strictly_consecutive_from_previous", False))
        previous_label = str(row.get("previous_point_label", ""))
        if point_label == LOW_POINT_LABEL and strict and current_segment == segment and previous_label == LOW_POINT_LABEL:
            current_depth += 1
        elif point_label == LOW_POINT_LABEL:
            current_segment = segment
            current_depth = 1
            current_run_id = _run_id(segment, str(row["record.id"]))
            run_starts[current_run_id] = str(row["record.id"])
        else:
            current_segment = None
            current_run_id = None
            current_depth = 0
        run_ids.append(current_run_id if current_run_id is not None else pd.NA)
        support_depths.append(current_depth)
    working["run_id"] = pd.Series(run_ids, dtype="string")
    working["support_depth_at_anchor"] = pd.Series(support_depths, dtype="Int64")
    run_stats = (
        working.loc[working["run_id"].notna()]
        .groupby("run_id", dropna=False)
        .agg(
            deployment_segment_id=("deployment_segment_id", "first"),
            run_start_record_id=("record.id", "first"),
            run_end_record_id=("record.id", "last"),
            run_start_time_utc=("sample_time_utc", "min"),
            run_end_time_utc=("sample_time_utc", "max"),
            eventual_run_length=("support_depth_at_anchor", "max"),
        )
        .reset_index()
    )
    last_record_by_segment = working.groupby("deployment_segment_id", dropna=False)["record.id"].last().to_dict()
    run_stats["run_complete"] = run_stats.apply(
        lambda row: str(row["run_end_record_id"]) != str(last_record_by_segment.get(row["deployment_segment_id"])),
        axis=1,
    )
    result = working.loc[:, ["record.id", "sample_id", "deployment_segment_id", "sample_time_utc", "run_id", "support_depth_at_anchor"]].copy()
    result = result.merge(run_stats.loc[:, ["run_id", "eventual_run_length", "run_complete"]], on="run_id", how="left", validate="many_to_one")
    return result


def _build_origin_frame(point: pd.DataFrame, firings: pd.DataFrame, resolutions: pd.DataFrame) -> pd.DataFrame:
    result = point.loc[:, ["sample_id", "label"]].rename(columns={"label": "point_label"}).copy()
    result["sample_id"] = result["sample_id"].astype("string")
    low_firing = firings.loc[
        firings["task_id"].astype("string").eq("POINT")
        & firings["rule_id"].astype("string").eq("LOW_RELATIVE_MOISTURE"),
        ["sample_id", "evidence_value", "threshold_value", "comparison_operator"],
    ].drop_duplicates("sample_id", keep=False)
    low_firing = low_firing.rename(columns={"evidence_value": "moisture_value", "threshold_value": "q_threshold", "comparison_operator": "q_comparator"})
    result = result.merge(low_firing, on="sample_id", how="left", validate="one_to_one")
    result["m_relation_to_q"] = "UNKNOWN"
    result.loc[pd.to_numeric(result["moisture_value"], errors="coerce") <= pd.to_numeric(result["q_threshold"], errors="coerce"), "m_relation_to_q"] = "M_t<=Q"
    result.loc[pd.to_numeric(result["moisture_value"], errors="coerce") > pd.to_numeric(result["q_threshold"], errors="coerce"), "m_relation_to_q"] = "M_t>Q"
    result["aux_positive_count"] = 0
    aux = firings.loc[
        firings["task_id"].astype("string").eq("POINT")
        & firings["rule_id"].astype("string").isin(["THERMAL_CONTEXT", "MOISTURE_RISE", "EC_SHIFT"])
        & firings["evidence_state"].astype("string").eq("POSITIVE"),
        ["sample_id", "rule_id"],
    ].drop_duplicates(["sample_id", "rule_id"])
    aux_counts = aux.groupby("sample_id", dropna=False).size().rename("aux_positive_count")
    result["aux_positive_count"] = result["sample_id"].map(aux_counts).fillna(0).astype("Int64")
    return result.convert_dtypes()


def _event_label(row: pd.Series, required_k: int) -> str:
    if str(row.get("point_label", "")) == LOW_POINT_LABEL and not bool(row.get("run_complete", False)):
        return EVENT_UNDETERMINED
    if str(row.get("online_label_status", "")) != "LABELED":
        return EVENT_UNDETERMINED if str(row.get("point_label", "")) == LOW_POINT_LABEL else str(row.get("online_label_name", WINDOW_INELIGIBLE))
    point_label = str(row.get("point_label", ""))
    if point_label == LOW_POINT_LABEL:
        if bool(row.get("run_complete", False)) and int(row.get("eventual_run_length") or 0) >= required_k:
            return LOW_LABEL
        return UNRES_LABEL
    if point_label == AUX_POINT_LABEL:
        return UNRES_LABEL
    return str(row.get("online_label_name", WINDOW_INELIGIBLE))


def _event_label_status(row: pd.Series) -> str:
    if str(row.get("online_label_status", "")) != "LABELED":
        if str(row.get("point_label", "")) == LOW_POINT_LABEL:
            return "ABSTAIN_EVENT_UNDETERMINED"
        return str(row.get("online_label_status", "ABSTAIN_INSUFFICIENT_EVIDENCE"))
    if str(row.get("event_label_name", "")) == EVENT_UNDETERMINED:
        return "ABSTAIN_EVENT_UNDETERMINED"
    return "LABELED"


def _pair_status(row: pd.Series) -> str:
    online_labeled = str(row.get("online_label_status", "")) == "LABELED"
    event_labeled = str(row.get("event_label_status", "")) == "LABELED"
    return "PAIRED" if online_labeled and event_labeled else "EXCLUDED"


def _derive_origin(row: pd.Series) -> str:
    if str(row.get("online_label_name", "")) != UNRES_LABEL:
        return "NOT_UNRES"
    if str(row.get("point_label", "")) == LOW_POINT_LABEL and int(row.get("support_depth_at_anchor") or 0) < int(row.get("required_k") or 0):
        return "UNRES_K"
    if str(row.get("point_label", "")) == AUX_POINT_LABEL:
        return "UNRES_A"
    return "NOT_UNRES"


def _build_target_rows(base: pd.DataFrame, required_k: int, horizon: str) -> pd.DataFrame:
    common = [
        "sample_id", "deployment_segment_id", "sample_time_utc", "run_id", "support_depth_at_anchor",
        "eventual_run_length", "run_complete", "required_k", "unres_origin", "origin_formula",
        "point_label",
        "online_label_name", "online_label_status", "online_intrinsic_eligibility", "event_label_name",
        "event_label_status", "event_intrinsic_eligibility", "target_pair_status", "event_vs_online_changed",
        "moisture_value", "q_threshold", "q_comparator", "m_relation_to_q", "aux_positive_count",
    ]
    base = base.copy()
    frames: list[pd.DataFrame] = []
    for target_view_id, label_column, status_column, eligibility_column in (
        (Y_ONLINE, "online_label_name", "online_label_status", "online_intrinsic_eligibility"),
        (Y_EVENT, "event_label_name", "event_label_status", "event_intrinsic_eligibility"),
    ):
        frame = base.loc[:, [column for column in common if column in base.columns]].copy()
        frame["target_view_id"] = target_view_id
        frame["label_task_id"] = target_view_id
        frame["task_id"] = TEMPORAL_TASK_ID
        frame["horizon_id"] = horizon
        frame["label_name"] = frame[label_column]
        frame["label"] = frame[label_column]
        frame["label_status"] = frame[status_column]
        frame["intrinsic_eligibility"] = frame[eligibility_column]
        frame["train_inclusion_status"] = frame["label_status"].map({"LABELED": "INCLUDED"}).fillna("EXCLUDED")
        frame["assignment_mode"] = "DERIVED_TARGET_VIEW"
        frame["assignment_status"] = "ASSIGNED"
        frame["source_task"] = "TEMPORAL_NATIVE_ONLINE"
        frame["source_label"] = frame["online_label_name"]
        frame["semantic_assignment_admissible"] = frame["label_status"].eq("LABELED")
        frame["target_semantics"] = "EVENT_RETROSPECTIVE" if target_view_id == Y_EVENT else "ONLINE_CAUSAL_CONFIRMATION"
        frames.append(frame)
    return pd.concat(frames, ignore_index=True).sort_values(["target_view_id", "sample_time_utc", "sample_id"], kind="stable").reset_index(drop=True).convert_dtypes()


def _build_run_registry(base: pd.DataFrame) -> pd.DataFrame:
    rows = base.loc[base["run_id"].notna(), [
        "run_id", "deployment_segment_id", "eventual_run_length", "run_complete"
    ]].drop_duplicates("run_id").copy()
    return rows.rename(columns={"run_id": "observed_low_run_id"}).convert_dtypes()


def _persist_target_files(*, output_dir: Path, target_rows: pd.DataFrame, run_registry: pd.DataFrame, base: pd.DataFrame, source: dict[str, pd.DataFrame], required_k: int, horizon: str, run_id: str, release_dir: Path) -> None:
    target_rows_path = output_dir / "target_views_assignments.parquet"
    run_registry_path = output_dir / "event_run_registry.parquet"
    summary_path = output_dir / "target_views_summary.csv"
    report_path = output_dir / "temporal_target_views_report.md"
    target_rows.to_parquet(target_rows_path, index=False)
    run_registry.to_parquet(run_registry_path, index=False)
    summary = _summary_frame(target_rows)
    summary.to_csv(summary_path, index=False)
    for target_view_id in TARGET_VIEW_IDS:
        view_dir = output_dir / "targets" / target_view_id
        view_dir.mkdir(parents=True, exist_ok=True)
        view_rows = target_rows.loc[target_rows["target_view_id"].eq(target_view_id)].copy()
        view_rows.to_parquet(view_dir / "assignments.parquet", index=False)
        resolution_rows = view_rows.loc[:, ["sample_id", "horizon_id", "label_name", "label_status", "support_depth_at_anchor", "required_k"]].copy()
        resolution_rows["task_id"] = TEMPORAL_TASK_ID
        resolution_rows["resolved_label"] = resolution_rows["label_name"]
        resolution_rows["resolution_code"] = "DERIVED_TARGET_VIEW"
        resolution_rows.to_parquet(view_dir / "resolutions.parquet", index=False)
        audit_dir = view_dir / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        view_rows.loc[:, ["sample_id", "label", "task_id"]].to_parquet(audit_dir / "assignments.parquet", index=False)
        resolution_rows.loc[:, ["sample_id", "horizon_id", "task_id", "resolved_label", "required_k", "support_depth_at_anchor"]].to_parquet(audit_dir / "resolutions.parquet", index=False)
    source_paths = source["paths"]
    manifest = {
        "artifact_type": "DERIVED_TEMPORAL_EVENT_ONLINE_TARGET_VIEWS",
        "artifact_status": "DERIVED_ANALYSIS_ONLY",
        "authority_status": "CANDIDATE_REFERENCE_ONLY",
        "run_id": run_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_native_release_dir": str(release_dir),
        "source_native_release_id": release_dir.name,
        "horizon_id": horizon,
        "selected_k": required_k,
        "target_view_ids": list(TARGET_VIEW_IDS),
        "model_facing_ontology": [LOW_LABEL, UNRES_LABEL, REF_LABEL],
        "future_used_for": "Y_event label construction only",
        "future_forbidden_in_features": True,
        "native_label_mutated": False,
        "feature_artifacts_mutated": False,
        "model_training_executed": False,
        "model_inference_executed": False,
        "definitions": {
            Y_ONLINE: "current temporal label: point LOW and d_t>=K -> LOW; point LOW and d_t<K -> UNRES",
            Y_EVENT: "complete point-LOW run with L_r>=K -> LOW for every row in the run, including d_t<K prefix",
            "paired_cohort": "online label status LABELED and event label status LABELED",
            "event_censoring": "point-LOW run ending at the observed segment boundary is EVENT_UNDETERMINED",
        },
        "source_files": {key: {"path": str(path), "sha256": _sha256(path)} for key, path in source_paths.items()},
        "output_files": {
            "combined_assignments": str(target_rows_path),
            "event_run_registry": str(run_registry_path),
            "summary": str(summary_path),
            "report": str(report_path),
        },
        "row_counts": {
            "native_rows": int(len(base)),
            "paired_rows": int(base["target_pair_status"].eq("PAIRED").sum()),
            "event_undetermined_rows": int(base["event_label_status"].eq("ABSTAIN_EVENT_UNDETERMINED").sum()),
            "event_online_changed_rows": int(base["event_vs_online_changed"].sum()),
        },
        "summary": json.loads(summary.to_json(orient="records")),
    }
    write_json(output_dir / "run_metadata" / "run_manifest.json", manifest)
    write_text(output_dir / "README.md", _build_readme(manifest))
    write_text(report_path, _build_report(manifest, summary))


def _summary_frame(target_rows: pd.DataFrame) -> pd.DataFrame:
    return (
        target_rows.groupby(["target_view_id", "label_name", "label_status"], dropna=False)
        .size()
        .rename("row_count")
        .reset_index()
        .sort_values(["target_view_id", "label_name", "label_status"], kind="stable")
        .convert_dtypes()
    )


def _build_readme(manifest: dict[str, object]) -> str:
    return f"""# Temporal event/online target views

This additive artifact derives `Y_event` and `Y_online` from native release
`{manifest['source_native_release_id']}`. It does not replace native labels or
features. Future information is used only to construct the retrospective
`Y_event` target; it is forbidden from model features.

The model-facing ontology remains `{', '.join(manifest['model_facing_ontology'])}`.
See `temporal_target_views_report.md` and `run_metadata/run_manifest.json`.
"""


def _build_report(manifest: dict[str, object], summary: pd.DataFrame) -> str:
    lines = [
        "# Temporal event/online target views — report",
        "",
        "> Additive target-view artifact. Native labels and feature artifacts are unchanged.",
        "",
        "## Contract",
        "",
        f"- Native release: `{manifest['source_native_release_id']}`",
        f"- K: `{manifest['selected_k']}`",
        f"- Model-facing ontology: `{', '.join(manifest['model_facing_ontology'])}`",
        "- `Y_online`: causal current-state confirmation using `d_t`.",
        "- `Y_event`: retrospective complete-run membership using `L_r`.",
        "- Right-censored runs: `EVENT_UNDETERMINED`, excluded from the paired cohort.",
        "",
        "## Counts",
        "",
        _markdown_table(summary, ["target_view_id", "label_name", "label_status", "row_count"]),
        "",
        "## Paired-difference scope",
        "",
        f"- Native rows: `{manifest['row_counts']['native_rows']}`",
        f"- Common paired rows: `{manifest['row_counts']['paired_rows']}`",
        f"- Event-undetermined rows: `{manifest['row_counts']['event_undetermined_rows']}`",
        f"- Rows where event and online labels differ: `{manifest['row_counts']['event_online_changed_rows']}`",
        "",
        "The changed rows are the successful-run prefix cohort `G` where `L_r >= K` and `d_t < K`.",
        "",
        "## Outputs",
        "",
        "- `target_views_assignments.parquet`: combined target-view rows.",
        "- `targets/temporal_event_3h/assignments.parquet`: retrospective target.",
        "- `targets/temporal_online_3h/assignments.parquet`: causal target view.",
        "- `event_run_registry.parquet`: run length/completeness evidence.",
        "- `run_metadata/run_manifest.json`: source hashes and lineage flags.",
    ]
    return "\n".join(lines) + "\n"


def _markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    if frame.empty:
        return "_empty_"
    display = frame.loc[:, columns].astype("string").fillna("")
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    rows = ["| " + " | ".join(str(value) for value in row) + " |" for row in display.itertuples(index=False, name=None)]
    return "\n".join([header, separator, *rows])


def _pair_status_unused(row: pd.Series) -> str:
    return "PAIRED"


def _run_id(segment: str, start_record_id: str) -> str:
    return hashlib.sha256(f"{segment}|{start_record_id}".encode("utf-8")).hexdigest()[:32]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
