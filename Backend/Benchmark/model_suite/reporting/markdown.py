from __future__ import annotations

import pandas as pd


def build_run_report_markdown(
    *,
    run_id: str,
    profile_name: str,
    summary_df: pd.DataFrame,
    pooled_df: pd.DataFrame,
) -> str:
    lines = [
        "# Model Suite Smoke Report",
        "",
        f"- run_id: `{run_id}`",
        f"- profile_name: `{profile_name}`",
        f"- trained_jobs: `{int(summary_df['status'].astype('string').eq('trained').sum()) if not summary_df.empty else 0}`",
        f"- pooled_groups: `{int(len(pooled_df))}`",
        "",
    ]
    if not summary_df.empty:
        lines.extend(
            [
                "## Status Counts",
                "",
                _frame_to_markdown_table(
                    summary_df["status"].astype("string").value_counts(dropna=False).rename_axis("status").reset_index(name="count")
                ),
                "",
            ]
        )
    if not pooled_df.empty:
        display_columns = [
            column
            for column in (
                "model_key",
                "stage_id",
                "feature_view_id",
                "partition",
                "accuracy",
                "supported_class_macro_f1",
                "supported_class_balanced_accuracy",
            )
            if column in pooled_df.columns
        ]
        lines.extend(
            [
                "## Pooled Metrics",
                "",
                _frame_to_markdown_table(pooled_df.loc[:, display_columns]),
                "",
            ]
        )
    return "\n".join(lines)


def _frame_to_markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_empty_"
    display_frame = frame.copy()
    for column in display_frame.columns:
        if pd.api.types.is_float_dtype(display_frame[column]):
            display_frame[column] = display_frame[column].map(lambda value: f"{float(value):.6f}")
        else:
            display_frame[column] = display_frame[column].astype("string").fillna("")
    headers = [str(column) for column in display_frame.columns]
    rows = [headers]
    rows.extend(display_frame.values.tolist())
    widths = [max(len(str(row[index])) for row in rows) for index in range(len(headers))]

    def format_row(values: list[object]) -> str:
        cells = [str(value).ljust(widths[index]) for index, value in enumerate(values)]
        return "| " + " | ".join(cells) + " |"

    separator = "| " + " | ".join("-" * width for width in widths) + " |"
    lines = [format_row(headers), separator]
    lines.extend(format_row(list(row)) for row in display_frame.values.tolist())
    return "\n".join(lines)
