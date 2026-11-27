"""Human- and machine-readable reporting for UNRES-origin derivatives."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .unres_origin_contract import TEMPORAL_UNRES_LABEL, UNRES_A, UNRES_K


def summarise_scope(
    frame: pd.DataFrame,
    *,
    scope: str,
    partition: str | None = None,
    partition_column: str | None = None,
) -> pd.DataFrame:
    working = frame.copy()
    if partition is not None:
        working["_scope_partition"] = partition
    elif partition_column is not None:
        working["_scope_partition"] = working[partition_column].astype("string")
    else:
        raise ValueError("A fixed partition or partition column is required.")
    grouped = (
        working.groupby(["_scope_partition", "temporal_label", "unres_origin"], dropna=False)
        .size()
        .rename("row_count")
        .reset_index()
        .rename(columns={"_scope_partition": "partition"})
    )
    grouped.insert(0, "scope", scope)
    return grouped.loc[:, ["scope", "partition", "temporal_label", "unres_origin", "row_count"]].sort_values(
        ["scope", "partition", "temporal_label", "unres_origin"], kind="stable"
    )


def count_payload(frame: pd.DataFrame | None) -> dict[str, int] | None:
    if frame is None:
        return None
    return {str(key): int(value) for key, value in frame["unres_origin"].value_counts(dropna=False).items()}


def build_readme(manifest: dict[str, Any], report_path_name: str) -> str:
    return f"""# Temporal UNRES origin split

This directory is an audit-only derivative of `{manifest['source_release_id']}`.
It does not replace native labels, alter model inputs, train a model, or run a
model test. The human-readable report is `{report_path_name}`.

The derived field `unres_origin` separates the existing temporal UNRES label
into `UNRES_K` and `UNRES_A`; all other temporal labels are `NOT_UNRES`.
"""


def build_report(
    manifest: dict[str, Any],
    rows: pd.DataFrame,
    summary: pd.DataFrame,
    protocol_scope: pd.DataFrame | None,
) -> str:
    native = rows[rows["unres_origin"].isin([UNRES_K, UNRES_A])]
    lines = [
        "# Temporal UNRES origin split — audit-only report",
        "",
        "> This is a derived provenance report. It does not create a new model",
        "> target, overwrite the native release, train, or test any model.",
        "",
        "## Lineage and status",
        "",
        f"- Source native release: `{manifest['source_release_id']}`",
        f"- Horizon: `{manifest['horizon_id']}`",
        f"- Derived artifact: `{manifest['run_id']}`",
        "- Authority status: `CANDIDATE_REFERENCE_ONLY`",
        "- Native labels mutated: `false`",
        "- Model training executed: `false`",
        "- Model testing executed: `false`",
        "",
        "## Requested separation",
        "",
        "| Derived origin | Formula | Meaning |",
        "|---|---|---|",
        f"| `{UNRES_K}` | `M_t <= Q` and `d_t < K` | LOW candidate; only the persistence gate fails |",
        f"| `{UNRES_A}` | `M_t > Q` and `E_aux+` | Not a LOW candidate; auxiliary evidence creates the fallback |",
        "",
        f"The materialized temporal label remains `{TEMPORAL_UNRES_LABEL}` in both cases.",
        "The split is therefore a provenance field for later filtering, not a replacement ontology.",
        "",
        "## Native temporal 3h release",
        "",
        f"- Total temporal anchors: `{len(rows)}`",
        f"- `{UNRES_K}`: `{_count_rows(rows, UNRES_K)}`",
        f"- `{UNRES_A}`: `{_count_rows(rows, UNRES_A)}`",
        f"- Total UNRES: `{len(native)}`",
        "",
        _markdown_table(
            summary.loc[summary["scope"].eq("native_release"), :],
            ["partition", "temporal_label", "unres_origin", "row_count"],
        ),
        "",
    ]
    if protocol_scope is not None:
        protocol_rows = protocol_scope[protocol_scope["unres_origin"].isin([UNRES_K, UNRES_A])]
        lines.extend(
            [
                "## E1 protocol projection",
                "",
                "This section is a row-scope projection only; no model evaluation was run.",
                "",
                f"- Protocol temporal rows: `{len(protocol_scope)}`",
                f"- Protocol `{UNRES_K}`: `{_count_rows(protocol_scope, UNRES_K)}`",
                f"- Protocol `{UNRES_A}`: `{_count_rows(protocol_scope, UNRES_A)}`",
                f"- Protocol UNRES rows: `{len(protocol_rows)}`",
                "",
                _markdown_table(
                    summary.loc[summary["scope"].eq("protocol_temporal_3h"), :],
                    ["partition", "temporal_label", "unres_origin", "row_count"],
                ),
                "",
            ]
        )
    lines.extend(
        [
            "## RQ preparation",
            "",
            "The two UNRES groups are now separable without changing the original",
            "weights or labels: a later experiment can select `unres_origin ==",
            f"{UNRES_K}` to test the K-fallback boundary, or `unres_origin == {UNRES_A}`",
            "to test the auxiliary-evidence fallback. The first group is the",
            "candidate case where Q is satisfied and only K is insufficient; the",
            "second group is generated by a different point-resolution route.",
            "",
            "## Machine-readable outputs",
            "",
            "- `unres_origin_assignments.parquet`: one row per native temporal anchor",
            "  with the original label plus proof fields for the derived origin.",
            "- `unres_origin_summary.csv`: counts by scope, partition, label, and origin.",
            "- `run_metadata/run_manifest.json`: source hashes, definitions, and no-test status.",
        ]
    )
    return "\n".join(lines) + "\n"


def _count_rows(frame: pd.DataFrame, origin: str) -> int:
    return int(frame["unres_origin"].eq(origin).sum())


def _markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    if frame.empty:
        return "_empty_"
    display = frame.loc[:, columns].copy().astype("string").fillna("")
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    rows = ["| " + " | ".join(str(value) for value in row) + " |" for row in display.itertuples(index=False, name=None)]
    return "\n".join([header, separator, *rows])
