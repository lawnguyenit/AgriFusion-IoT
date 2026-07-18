from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


V2_RANGE_SPECS: tuple[tuple[str, str, str], ...] = (
    ("P1_LATE_CHAIN", "2026-05-09", "2026-05-19"),
    ("P2_TARGET_DEPLOYMENT", "2026-06-27", "2026-07-12"),
)


@dataclass(frozen=True)
class V2CoverageArtifacts:
    daily: pd.DataFrame
    range_summary: pd.DataFrame
    markdown_report: str


def build_v2_coverage_artifacts(
    *,
    v2_evidence_3h: pd.DataFrame,
    v2_evidence_8h: pd.DataFrame,
) -> V2CoverageArtifacts:
    daily = pd.concat(
        [
            _daily_frame(v2_evidence_3h, "3h"),
            _daily_frame(v2_evidence_8h, "8h"),
        ],
        ignore_index=True,
    ).convert_dtypes()
    range_summary = _build_range_summary(daily)
    markdown_report = _build_markdown_report(range_summary)
    return V2CoverageArtifacts(
        daily=daily,
        range_summary=range_summary,
        markdown_report=markdown_report,
    )


def _daily_frame(frame: pd.DataFrame, horizon_name: str) -> pd.DataFrame:
    working = frame.loc[
        :,
        [
            "record.id",
            "record.ts_sample",
            "eligible_for_training",
            "intrinsic_exclusion_reason",
            "valid_observation_count",
            "actual_window_span_sec",
            "max_internal_gap_sec",
        ],
    ].copy()
    timestamps = pd.to_datetime(working["record.ts_sample"], unit="s", utc=True).dt.tz_convert("Asia/Ho_Chi_Minh")
    working["local_date"] = timestamps.dt.strftime("%Y-%m-%d")
    working["window_horizon_name"] = horizon_name
    working["eligible_for_training"] = working["eligible_for_training"].fillna(False).astype(bool)
    grouped = (
        working.groupby(["window_horizon_name", "local_date"], dropna=False, sort=False)
        .agg(
            row_count=("record.id", "size"),
            eligible_count=("eligible_for_training", "sum"),
            insufficient_history_count=(
                "intrinsic_exclusion_reason",
                lambda s: int((pd.Series(s).astype("string") == "insufficient_history").sum()),
            ),
            point_label_not_labeled_count=(
                "intrinsic_exclusion_reason",
                lambda s: int((pd.Series(s).astype("string") == "point_label_not_labeled").sum()),
            ),
            median_valid_observation_count=("valid_observation_count", "median"),
            median_window_span_sec=("actual_window_span_sec", "median"),
            median_max_internal_gap_sec=("max_internal_gap_sec", "median"),
            max_window_span_sec=("actual_window_span_sec", "max"),
            max_internal_gap_sec=("max_internal_gap_sec", "max"),
        )
        .reset_index()
    )
    grouped["eligible_ratio"] = grouped["eligible_count"] / grouped["row_count"].clip(lower=1)
    return grouped.convert_dtypes()


def _build_range_summary(daily: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for range_name, start, end in V2_RANGE_SPECS:
        for horizon_name in ("3h", "8h"):
            selected = daily.loc[
                (daily["window_horizon_name"].astype("string") == horizon_name)
                & (daily["local_date"].astype("string") >= start)
                & (daily["local_date"].astype("string") <= end)
            ].copy()
            if selected.empty:
                continue
            rows.append(
                {
                    "range_name": range_name,
                    "window_horizon_name": horizon_name,
                    "range_start_date": start,
                    "range_end_date": end,
                    "row_count": int(selected["row_count"].sum()),
                    "eligible_count": int(selected["eligible_count"].sum()),
                    "eligible_ratio": float(selected["eligible_count"].sum() / max(int(selected["row_count"].sum()), 1)),
                    "insufficient_history_count": int(selected["insufficient_history_count"].sum()),
                    "point_label_not_labeled_count": int(selected["point_label_not_labeled_count"].sum()),
                    "median_daily_gap_sec": float(selected["median_max_internal_gap_sec"].median()),
                    "max_daily_gap_sec": int(selected["max_internal_gap_sec"].max()),
                }
            )
    summary = pd.DataFrame(rows).convert_dtypes()
    if summary.empty:
        return summary
    pivot = (
        summary.pivot(index="range_name", columns="window_horizon_name", values="eligible_count")
        .rename(columns={"3h": "eligible_count_3h", "8h": "eligible_count_8h"})
        .reset_index()
    )
    ratio_pivot = (
        summary.pivot(index="range_name", columns="window_horizon_name", values="eligible_ratio")
        .rename(columns={"3h": "eligible_ratio_3h", "8h": "eligible_ratio_8h"})
        .reset_index()
    )
    merged = summary.merge(pivot, on="range_name", how="left").merge(ratio_pivot, on="range_name", how="left")
    merged["eligible_count_delta_vs_3h"] = merged["eligible_count"] - merged["eligible_count_3h"]
    merged["eligible_ratio_delta_vs_3h"] = merged["eligible_ratio"] - merged["eligible_ratio_3h"]
    return merged.convert_dtypes()


def _build_markdown_report(range_summary: pd.DataFrame) -> str:
    if range_summary.empty:
        return "# V2 Coverage Loss Report\n\nNo V2 coverage rows were generated.\n"
    lines = [
        "# V2 Coverage Loss Report",
        "",
        "This report summarizes why 8h V2 windows lose more eligible anchors than 3h windows.",
        "",
    ]
    for range_name, group in range_summary.groupby("range_name", dropna=False, sort=False):
        lines.append(f"## {range_name}")
        for _, row in group.sort_values("window_horizon_name", kind="stable").iterrows():
            lines.append(
                "- "
                f"{row['window_horizon_name']}: eligible {int(row['eligible_count'])}/{int(row['row_count'])} "
                f"({float(row['eligible_ratio']):.4f}), "
                f"insufficient_history={int(row['insufficient_history_count'])}, "
                f"point_label_not_labeled={int(row['point_label_not_labeled_count'])}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
