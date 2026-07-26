from __future__ import annotations

import json
from dataclasses import dataclass

import pandas as pd


POINT_LABELS: tuple[str, ...] = (
    "normal_point",
    "low_relative_moisture_point",
    "unknown_environment_point",
)


@dataclass(frozen=True)
class RepresentationValidityArtifacts:
    class_specific_retention: pd.DataFrame
    native_vs_matched_distribution: pd.DataFrame
    markdown_report: str


def build_representation_validity_artifacts(
    *,
    task_training_manifest: pd.DataFrame,
    comparison_training_manifest: pd.DataFrame,
) -> RepresentationValidityArtifacts:
    task_frame = task_training_manifest.loc[
        task_training_manifest["final_trainability"].fillna(False).astype(bool)
    ].copy()
    comparison_frame = comparison_training_manifest.loc[
        comparison_training_manifest["final_trainability"].fillna(False).astype(bool)
    ].copy()

    retention_rows: list[dict[str, object]] = []
    distribution_rows: list[dict[str, object]] = []

    group_columns = [
        "comparison_id",
        "comparison_side",
        "matched_cohort_id",
        "feature_view_id",
        "feature_source_view_id",
        "label_task_id",
        "protocol_view_id",
        "fold_id",
        "partition",
    ]
    for keys, matched in comparison_frame.groupby(group_columns, dropna=False, sort=False):
        row = dict(zip(group_columns, keys, strict=True))
        feature_view_id = str(row["feature_view_id"])
        fold_id = str(row["fold_id"])
        partition = str(row["partition"])
        native = task_frame.loc[
            (task_frame["feature_view_id"].astype("string") == feature_view_id)
            & (task_frame["fold_id"].astype("string") == fold_id)
            & (task_frame["partition"].astype("string") == partition)
        ].copy()
        if native.empty:
            continue

        native_counts = _count_labels(native["label_name"])
        matched_counts = _count_labels(matched["label_name"])
        native_total = int(len(native))
        matched_total = int(len(matched))
        overall_retention = _safe_ratio(matched_total, native_total)
        native_distribution = _to_distribution(native_counts, native_total)
        matched_distribution = _to_distribution(matched_counts, matched_total)
        distribution_distance = _distribution_l1_distance(native_distribution, matched_distribution)

        distribution_rows.append(
            {
                **row,
                "representation_role": _representation_role(feature_view_id),
                "native_rows": native_total,
                "matched_rows": matched_total,
                "overall_retention": overall_retention,
                "native_distribution_json": json.dumps(native_counts, ensure_ascii=False, separators=(",", ":")),
                "matched_distribution_json": json.dumps(matched_counts, ensure_ascii=False, separators=(",", ":")),
                "native_distribution_ratio_json": json.dumps(native_distribution, ensure_ascii=False, separators=(",", ":")),
                "matched_distribution_ratio_json": json.dumps(matched_distribution, ensure_ascii=False, separators=(",", ":")),
                "distribution_l1_distance": distribution_distance,
            }
        )

        for label_name in POINT_LABELS:
            native_count = int(native_counts.get(label_name, 0))
            matched_count = int(matched_counts.get(label_name, 0))
            class_retention = _safe_ratio(matched_count, native_count)
            retention_rows.append(
                {
                    **row,
                    "representation_role": _representation_role(feature_view_id),
                    "class_name": label_name,
                    "native_class_count": native_count,
                    "matched_class_count": matched_count,
                    "class_retention": class_retention,
                    "native_rows": native_total,
                    "matched_rows": matched_total,
                    "overall_retention": overall_retention,
                    "retention_delta_vs_overall": (
                        float(class_retention - overall_retention)
                        if pd.notna(class_retention) and pd.notna(overall_retention)
                        else pd.NA
                    ),
                }
            )

    retention_df = pd.DataFrame(retention_rows).convert_dtypes()
    distribution_df = pd.DataFrame(distribution_rows).convert_dtypes()
    report = _build_representation_report(retention_df, distribution_df)
    return RepresentationValidityArtifacts(
        class_specific_retention=retention_df,
        native_vs_matched_distribution=distribution_df,
        markdown_report=report,
    )


def _build_representation_report(
    retention_df: pd.DataFrame,
    distribution_df: pd.DataFrame,
) -> str:
    lines = [
        "# Representation Validity Report",
        "",
        "This report compares native task cohorts against the matched same-Y cohorts used for benchmark comparisons.",
        "",
    ]
    if retention_df.empty or distribution_df.empty:
        lines.extend(
            [
                "- No matched same-Y representation data was available.",
                "",
            ]
        )
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "## Summary",
            "",
            f"- Matched comparison groups analyzed: `{int(distribution_df[['comparison_id', 'fold_id', 'partition', 'feature_view_id']].drop_duplicates().shape[0])}`.",
            f"- Worst overall retention: `{_format_retention_row(_select_worst_overall_retention(distribution_df))}`.",
            f"- Worst class-specific retention: `{_format_class_retention_row(_select_worst_class_retention(retention_df))}`.",
            f"- Largest native-to-matched distribution shift: `{_format_distribution_row(_select_largest_distribution_shift(distribution_df))}`.",
            "",
            "## Class-Selective Attrition",
            "",
        ]
    )

    point_focus = retention_df.loc[
        retention_df["representation_role"].astype("string") == "point_anchor_reference"
    ].copy()
    if point_focus.empty:
        lines.append("- No point-anchor comparison rows were available.")
    else:
        worst_rows = point_focus.sort_values(
            ["class_retention", "overall_retention"],
            ascending=[True, True],
            kind="stable",
        ).head(6)
        for row in worst_rows.itertuples(index=False):
            lines.append(
                "- "
                f"{row.comparison_id} | {row.feature_view_id} | {row.fold_id} | {row.partition} | "
                f"{row.class_name}: matched {int(row.matched_class_count)}/{int(row.native_class_count)} "
                f"({float(row.class_retention):.4f}) versus overall {float(row.overall_retention):.4f}."
            )

    lines.extend(
        [
            "",
            "## Interpretation Note",
            "",
            "- High overall retention does not guarantee class-stable retention. Use `class_specific_retention.csv` when comparing point views against causal window views.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def _count_labels(series: pd.Series) -> dict[str, int]:
    counts = (
        series.astype("string")
        .dropna()
        .value_counts(sort=False)
        .to_dict()
    )
    return {str(label): int(count) for label, count in counts.items()}


def _to_distribution(counts: dict[str, int], total: int) -> dict[str, float]:
    if total <= 0:
        return {label: 0.0 for label in POINT_LABELS}
    return {label: float(counts.get(label, 0) / total) for label in POINT_LABELS}


def _distribution_l1_distance(
    native_distribution: dict[str, float],
    matched_distribution: dict[str, float],
) -> float:
    return float(
        sum(abs(native_distribution.get(label, 0.0) - matched_distribution.get(label, 0.0)) for label in POINT_LABELS)
    )


def _representation_role(feature_view_id: str) -> str:
    return "window_view" if feature_view_id.startswith("v2_") else "point_anchor_reference"


def _safe_ratio(numerator: int, denominator: int) -> float | pd._libs.missing.NAType:
    if denominator <= 0:
        return pd.NA
    return float(numerator / denominator)


def _select_worst_overall_retention(distribution_df: pd.DataFrame) -> pd.Series | None:
    if distribution_df.empty:
        return None
    return distribution_df.sort_values("overall_retention", ascending=True, kind="stable").iloc[0]


def _select_worst_class_retention(retention_df: pd.DataFrame) -> pd.Series | None:
    if retention_df.empty:
        return None
    filtered = retention_df.loc[retention_df["native_class_count"].fillna(0).astype(int).gt(0)].copy()
    if filtered.empty:
        return None
    return filtered.sort_values("class_retention", ascending=True, kind="stable").iloc[0]


def _select_largest_distribution_shift(distribution_df: pd.DataFrame) -> pd.Series | None:
    if distribution_df.empty:
        return None
    return distribution_df.sort_values("distribution_l1_distance", ascending=False, kind="stable").iloc[0]


def _format_retention_row(row: pd.Series | None) -> str:
    if row is None:
        return "not available"
    return (
        f"{row['comparison_id']} / {row['feature_view_id']} / {row['fold_id']} / {row['partition']} "
        f"=> {float(row['matched_rows'])}/{float(row['native_rows'])} ({float(row['overall_retention']):.4f})"
    )


def _format_class_retention_row(row: pd.Series | None) -> str:
    if row is None:
        return "not available"
    return (
        f"{row['comparison_id']} / {row['feature_view_id']} / {row['fold_id']} / {row['partition']} / {row['class_name']} "
        f"=> {int(row['matched_class_count'])}/{int(row['native_class_count'])} ({float(row['class_retention']):.4f})"
    )


def _format_distribution_row(row: pd.Series | None) -> str:
    if row is None:
        return "not available"
    return (
        f"{row['comparison_id']} / {row['feature_view_id']} / {row['fold_id']} / {row['partition']} "
        f"=> L1 distance {float(row['distribution_l1_distance']):.4f}"
    )
