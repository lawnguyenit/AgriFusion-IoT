from __future__ import annotations

import pandas as pd


def build_generation_report_markdown(
    *,
    evidence_ledger_df: pd.DataFrame,
    event_registry_df: pd.DataFrame,
    pre_onset_y_df: pd.DataFrame,
    legacy_coverage_report: dict[str, object],
) -> str:
    genealogy_counts = (
        evidence_ledger_df["genealogy"].fillna("unknown").astype(str).value_counts(dropna=False).to_dict()
        if "genealogy" in evidence_ledger_df.columns
        else {}
    )
    unresolved = evidence_ledger_df.loc[
        evidence_ledger_df.get("genealogy", pd.Series([], dtype="string")).astype(str) == "unresolved",
        "feature_name",
    ].astype(str).tolist() if "feature_name" in evidence_ledger_df.columns else []

    lines = [
        "# V3 Operational Lineage Generation Report",
        "",
        "## Coverage",
        f"- Canonical rows: {legacy_coverage_report.get('canonical_row_count', 'unknown')}",
        f"- Legacy weak-label rows: {legacy_coverage_report.get('legacy_event_row_count', 'unknown')}",
        f"- Matched canonical rows: {legacy_coverage_report.get('matched_row_count', 'unknown')}",
        f"- Unmatched canonical rows: {legacy_coverage_report.get('unmatched_canonical_row_count', 'unknown')}",
        "",
        "## Genealogy counts",
        f"- direct_rule: {genealogy_counts.get('direct_rule', 0)}",
        f"- derived_rule: {genealogy_counts.get('derived_rule', 0)}",
        f"- independent_process: {genealogy_counts.get('independent_process', 0)}",
        f"- unresolved: {genealogy_counts.get('unresolved', 0)}",
        "",
        "## Event registry",
        f"- Event count: {int(len(event_registry_df))}",
        "",
        "## Pre-onset targets",
    ]
    for column in pre_onset_y_df.columns:
        if column == "record.id":
            continue
        numeric = pd.to_numeric(pre_onset_y_df[column], errors="coerce")
        lines.append(
            f"- {column}: positives={int(numeric.fillna(0).eq(1).sum())}, eligible={int(numeric.notna().sum())}"
        )
    unresolved_lines = [f"- {feature}" for feature in unresolved] if unresolved else ["- none"]
    lines.extend(
        [
            "",
            "## Unresolved features",
            *unresolved_lines,
            "",
        ]
    )
    return "\n".join(lines) + "\n"
