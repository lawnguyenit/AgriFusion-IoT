from __future__ import annotations

import json

import pandas as pd

from Backend.Benchmark.validity_lifecycle.contracts import EnvironmentSpec, ValidityLifecycleConfig
from Backend.Benchmark.validity_lifecycle.defaults import PRIMARY_VIEW_IDS


def build_validation_payload(
    *,
    config: ValidityLifecycleConfig,
    support_df: pd.DataFrame,
    eligibility_df: pd.DataFrame,
    comparison_hash_df: pd.DataFrame,
    ec_dependency_df: pd.DataFrame,
    ph_stability_df: pd.DataFrame,
) -> dict[str, object]:
    support_gate = _gate_from_counts(
        fail_count=int(
            support_df.loc[
                support_df["view_id"].astype("string").isin(PRIMARY_VIEW_IDS)
                & support_df["support_status"].astype("string").eq("NOT_ESTIMABLE")
            ].shape[0]
        ),
        warn_count=int(
            support_df.loc[
                support_df["view_id"].astype("string").isin(PRIMARY_VIEW_IDS)
                & support_df["support_status"].astype("string").isin(["LOW_SUPPORT", "ABSENT"])
            ].shape[0]
        ),
    )
    eligibility_gate = _gate_from_counts(
        fail_count=int(
            eligibility_df.loc[
                eligibility_df["view_id"].astype("string").isin(PRIMARY_VIEW_IDS)
                & eligibility_df["base_row_count"].fillna(0).astype(int).gt(0)
                & eligibility_df["eligible_row_count"].fillna(0).astype(int).eq(0)
            ].shape[0]
        ),
        warn_count=int(
            eligibility_df.loc[
                eligibility_df["view_id"].astype("string").isin(PRIMARY_VIEW_IDS)
                & eligibility_df["eligible_rate"].fillna(1.0).astype(float).lt(config.low_eligibility_rate_threshold)
                & eligibility_df["eligible_row_count"].fillna(0).astype(int).gt(0)
            ].shape[0]
        ),
    )
    comparison_gate = _gate_from_counts(
        fail_count=int(comparison_hash_df["status"].astype("string").eq("FAIL").sum()),
        warn_count=0,
    )
    dependency_warn_count = int(
        ec_dependency_df["relationship_class"].astype("string").isin(
            ["DETERMINISTIC_EC_DERIVED_PROXY", "NEAR_DETERMINISTIC_PROXY"]
        ).sum()
        + ph_stability_df["stability_class"].astype("string").isin(["STEP_CHANGE", "SPARSE"]).sum()
    )
    dependency_gate = _gate_from_counts(fail_count=0, warn_count=dependency_warn_count)

    stage_status_lookup = {
        spec.environment_id: _combine_statuses(
            (
                _environment_support_status(spec, support_df),
                _environment_eligibility_status(spec, eligibility_df, config.low_eligibility_rate_threshold),
            )
        )
        for spec in config.environment_specs
    }
    strongest_proxy = _strongest_proxy_finding(ec_dependency_df)
    ph_finding = _overall_ph_finding(ph_stability_df)
    source_expansion_status = _combine_statuses((stage_status_lookup.get("E2", "PASS"), stage_status_lookup.get("E3", "PASS"), comparison_gate["status"]))
    repair_status = dependency_gate["status"]
    stage_entries = [
        {
            "stage_name": "Discovery",
            "environment_id": "E1",
            "status": stage_status_lookup.get("E1", "BLOCKED"),
            "question": "Under stable source conditions, what dependency appears usable before transport stress?",
            "answer": f"No model discovery run is executed in this lane. Current audit evidence says the strongest proxy finding is `{strongest_proxy}` and E1 support readiness is `{stage_status_lookup.get('E1', 'BLOCKED')}`.",
        },
        {
            "stage_name": "Temporal falsification",
            "environment_id": "E2",
            "status": stage_status_lookup.get("E2", "BLOCKED"),
            "question": "Does a dependency seen in E1 survive the later P1 regime without refitting the contract?",
            "answer": f"No E1->E2 model run is executed here. This lane only confirms whether E2 is audit-ready, which is currently `{stage_status_lookup.get('E2', 'BLOCKED')}`.",
        },
        {
            "stage_name": "Source expansion",
            "environment_id": "E2+E3",
            "status": source_expansion_status,
            "question": "Does adding E2 create transport evidence or only add more source data?",
            "answer": f"No Train(E1) vs Train(E1+E2) experiment is executed here. Comparison integrity is `{comparison_gate['status']}` and downstream E3 support is `{stage_status_lookup.get('E3', 'BLOCKED')}`.",
        },
        {
            "stage_name": "Deployment transport",
            "environment_id": "E3",
            "status": stage_status_lookup.get("E3", "BLOCKED"),
            "question": "After relocation, what remains estimable, transportable, or ambiguous?",
            "answer": f"No source-to-E3 model transport is executed here. This audit only reports that E3 support readiness is `{stage_status_lookup.get('E3', 'BLOCKED')}`.",
        },
        {
            "stage_name": "Repair derivation",
            "environment_id": "ALL",
            "status": repair_status,
            "question": "Which additional measurements are needed to separate still-ambiguous failure causes?",
            "answer": f"Proxy evidence is `{strongest_proxy}` and overall pH stability is `{ph_finding}`. Any later collection-repair recommendation must distinguish those ambiguity sources explicitly.",
        },
    ]
    overall_status = _combine_statuses((support_gate["status"], eligibility_gate["status"], comparison_gate["status"], dependency_gate["status"]))
    if overall_status == "FAIL":
        overall_status = "BLOCKED"
    return {
        "overall_status": overall_status,
        "gates": {
            "support_gate": support_gate,
            "eligibility_gate": eligibility_gate,
            "comparison_hash_gate": comparison_gate,
            "dependency_gate": dependency_gate,
        },
        "stage_readiness": stage_entries,
        "summary": {
            "strongest_proxy_finding": strongest_proxy,
            "overall_ph_finding": ph_finding,
        },
    }


def render_validity_lifecycle_report(
    *,
    validation_payload: dict[str, object],
    config: ValidityLifecycleConfig,
    support_df: pd.DataFrame,
    eligibility_df: pd.DataFrame,
    comparison_hash_df: pd.DataFrame,
    ec_dependency_df: pd.DataFrame,
    ph_stability_df: pd.DataFrame,
) -> str:
    lines = [
        "# Validity Lifecycle Audit Report",
        "",
        f"- Overall lifecycle status: `{validation_payload['overall_status']}`.",
        f"- Protocol source: `{config.evaluation_protocol_run_dir}`.",
        "",
        "## Lifecycle Flow",
        "",
        "```mermaid",
        "flowchart LR",
        '    A["Discovery\\nTrain E1\\nEvaluate future folds in E1"] --> B["Temporal falsification\\nTrain E1\\nEvaluate E2"]',
        '    B --> C["Source expansion\\nCompare Train(E1) vs Train(E1+E2) on E3"]',
        '    C --> D["Deployment transport\\nTrain P1 source\\nEvaluate E3"]',
        '    D --> E["Repair derivation\\nInspect aggregate failures\\nand missing evidence"]',
        "```",
        "",
        "## Gate Summary",
        "",
    ]
    for gate_name, gate_payload in validation_payload["gates"].items():
        lines.append(
            f"- `{gate_name}`: `{gate_payload['status']}` "
            f"(fail={gate_payload['fail_count']}, warn={gate_payload['warn_count']})."
        )
    lines.extend(
        [
            "",
            "## Stage Answers",
            "",
            "| Stage | Status | Question | Current answer |",
            "| --- | --- | --- | --- |",
        ]
    )
    for stage in validation_payload["stage_readiness"]:
        lines.append(
            f"| {stage['stage_name']} | `{stage['status']}` | {stage['question']} | {stage['answer']} |"
        )
    lines.extend(
        [
            "",
            "## Key Evidence",
            "",
            f"- Strongest EC/NPK proxy finding: `{validation_payload['summary']['strongest_proxy_finding']}`.",
            f"- Overall pH stability finding: `{validation_payload['summary']['overall_ph_finding']}`.",
            f"- Support rows audited: `{int(len(support_df))}`.",
            f"- Eligibility rows audited: `{int(len(eligibility_df))}`.",
            f"- Comparison cohorts audited: `{int(len(comparison_hash_df))}`.",
            f"- EC/NPK summaries produced: `{int(len(ec_dependency_df))}`.",
            f"- pH summaries produced: `{int(len(ph_stability_df))}`.",
            "",
            "## Interpretation Limits",
            "",
            "- This lane does not train models.",
            "- Discovery, falsification, and transport answers remain readiness statements until later experiment lanes consume these manifests.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def _gate_from_counts(*, fail_count: int, warn_count: int) -> dict[str, object]:
    if fail_count > 0:
        status = "FAIL"
    elif warn_count > 0:
        status = "WARN"
    else:
        status = "PASS"
    return {
        "status": status,
        "fail_count": fail_count,
        "warn_count": warn_count,
    }


def _environment_support_status(spec: EnvironmentSpec, support_df: pd.DataFrame) -> str:
    env_rows = support_df.loc[
        support_df["environment_id"].astype("string") == spec.environment_id
    ].copy()
    return _combine_statuses(_row_statuses(env_rows, "support_status"))


def _environment_eligibility_status(spec: EnvironmentSpec, eligibility_df: pd.DataFrame, threshold: float) -> str:
    env_rows = eligibility_df.loc[
        eligibility_df["environment_id"].astype("string") == spec.environment_id
    ].copy()
    fail = env_rows.loc[
        env_rows["base_row_count"].fillna(0).astype(int).gt(0)
        & env_rows["eligible_row_count"].fillna(0).astype(int).eq(0)
    ]
    if not fail.empty:
        return "FAIL"
    warn = env_rows.loc[
        env_rows["eligible_rate"].fillna(1.0).astype(float).lt(threshold)
        & env_rows["eligible_row_count"].fillna(0).astype(int).gt(0)
    ]
    if not warn.empty:
        return "WARN"
    return "PASS"


def _combine_statuses(statuses: tuple[str, ...] | list[str]) -> str:
    normalized = [status for status in statuses if status]
    if any(status in {"FAIL", "BLOCKED"} for status in normalized):
        return "FAIL"
    if any(status == "WARN" for status in normalized):
        return "WARN"
    return "PASS"


def _row_statuses(frame: pd.DataFrame, status_column: str) -> tuple[str, ...]:
    if frame.empty:
        return ("FAIL",)
    statuses = []
    for value in frame[status_column].astype("string").tolist():
        if value == "NOT_ESTIMABLE":
            statuses.append("FAIL")
        elif value in {"LOW_SUPPORT", "ABSENT"}:
            statuses.append("WARN")
        else:
            statuses.append("PASS")
    return tuple(statuses)


def _strongest_proxy_finding(ec_dependency_df: pd.DataFrame) -> str:
    if ec_dependency_df.empty:
        return "not available"
    priority = {
        "DETERMINISTIC_EC_DERIVED_PROXY": 0,
        "NEAR_DETERMINISTIC_PROXY": 1,
        "CORRELATED_SENSOR_OUTPUT": 2,
        "INCONCLUSIVE": 3,
        "INSUFFICIENT_VARIATION": 4,
    }
    ordered = ec_dependency_df.sort_values(
        by="relationship_class",
        key=lambda series: series.astype("string").map(priority).fillna(99),
        kind="stable",
    )
    best = ordered.iloc[0]
    return f"{best['nutrient_column']}::{best['relationship_class']}"


def _overall_ph_finding(ph_stability_df: pd.DataFrame) -> str:
    if ph_stability_df.empty:
        return "not available"
    overall = ph_stability_df.loc[ph_stability_df["environment_id"].astype("string") == "ALL"].copy()
    if overall.empty:
        overall = ph_stability_df.head(1)
    row = overall.iloc[0]
    return str(row["stability_class"])
