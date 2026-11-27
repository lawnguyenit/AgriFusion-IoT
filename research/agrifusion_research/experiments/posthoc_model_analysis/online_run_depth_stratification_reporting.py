"""Report and chart writers for the online run-depth focal analysis."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .online_run_depth_stratification_data import DEPTH_BINS


def write_chart(summary: pd.DataFrame, path: Path) -> None:
    """Write a grouped LOW-prediction-rate chart by view/partition."""

    import matplotlib.pyplot as plt

    available = summary.loc[summary["run_outcome"].isin(["successful", "failed"])].copy()
    if available.empty:
        return
    views = list(summary["feature_view_id"].astype("string").unique())
    partitions = list(summary["partition"].astype("string").unique())
    fig, axes = plt.subplots(
        len(views),
        len(partitions),
        figsize=(5.6 * len(partitions), 4.2 * len(views)),
        squeeze=False,
        dpi=150,
    )
    colors = {"successful": "#4c78a8", "failed": "#e45756"}
    x = list(range(len(DEPTH_BINS)))
    width = 0.36
    for row_index, view_id in enumerate(views):
        for column_index, partition in enumerate(partitions):
            ax = axes[row_index][column_index]
            for offset, outcome in ((-width / 2, "successful"), (width / 2, "failed")):
                subset = available.loc[
                    available["feature_view_id"].eq(view_id)
                    & available["partition"].eq(partition)
                    & available["run_outcome"].eq(outcome)
                ].set_index("depth_bin")
                values = [
                    float(subset.loc[depth, "pred_low_rate"])
                    if depth in subset.index and pd.notna(subset.loc[depth, "pred_low_rate"])
                    else 0.0
                    for depth in DEPTH_BINS
                ]
                counts = [
                    int(subset.loc[depth, "prediction_rows"]) if depth in subset.index else 0
                    for depth in DEPTH_BINS
                ]
                positions = [value + offset for value in x]
                ax.bar(positions, values, width=width, color=colors[outcome], label=outcome)
                for position, value, count in zip(positions, values, counts, strict=True):
                    if count:
                        ax.text(
                            position,
                            min(value + 0.03, 1.03),
                            f"{value:.2f}\n(n={count})",
                            ha="center",
                            va="bottom",
                            fontsize=8,
                        )
            ax.set_title(f"{str(view_id).replace('v2_', '')} — {partition}")
            ax.set_xticks(x, DEPTH_BINS)
            ax.set_ylim(0, 1.14)
            ax.set_ylabel("P(pred LOW | stratum)")
            ax.set_xlabel("Current run depth d_t")
            ax.grid(axis="y", alpha=0.25)
            if row_index == 0 and column_index == 0:
                ax.legend(frameon=False)
    fig.suptitle("Y_online model: LOW predictions by Q-positive run stratum", y=1.01)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def build_readme(manifest: dict[str, object]) -> str:
    return f"""# Online run-depth focal analysis

This is a non-mutating post-hoc analysis of `{manifest['target_view_id']}`.
It reuses an existing prediction file, restricts rows to Q-positive point
observations, and splits them by current depth and eventual run outcome. No
weights were loaded, no inference was run, and no retraining or relabeling was
performed. See `online_run_depth_focal_report.md` and `run_metadata.json`.
"""


def build_report(
    manifest: dict[str, object],
    population_summary: pd.DataFrame,
    prediction_summary: pd.DataFrame,
) -> str:
    lines = [
        "# Y_online run-depth focal analysis — report",
        "",
        "> Post-hoc diagnostic. Y_online, the model weights, and the original benchmark are unchanged.",
        "",
        "## Scope and definitions",
        "",
        f"- Model run: `{manifest['source_model_run_id']}`; profile `{manifest['profile_name']}`.",
        f"- Target: `{manifest['target_view_id']}`.",
        f"- Q-positive: `{manifest['q_positive_definition']}`.",
        "- Depth bins: `d=1`, `d=2`, `d>=3`.",
        "- Successful: `run_complete` and `L_r>=K`; failed: `run_complete` and `L_r<K`.",
        "- Censored/unknown rows are retained in the population table but are not silently called successful or failed.",
        "- Primary metric: `P(pred LOW | Q-positive, depth, run outcome)` as the hard LOW-prediction fraction.",
        "- Secondary metric: mean predicted probability assigned to LOW.",
        "",
        "## Full Q-positive population",
        "",
        markdown_table(population_summary),
        "",
        f"The complete target artifact contains `{manifest['row_counts']['q_positive_population']}` Q-positive anchors.",
        "",
        "## Existing online predictions",
        "",
        markdown_table(prediction_summary),
        "",
        f"The selected prediction scope contains `{manifest['row_counts']['prediction_rows']}` rows across the requested validation/test partitions and feature views.",
        "Training rows are not included because this model artifact does not emit training predictions.",
        "",
        "## Observed test pattern",
        "",
        *_build_observed_findings(prediction_summary),
        "",
        "## Interpretation rule",
        "",
        "For `d=1` and `d=2`, successful and failed runs have the same current online label (`UNRES_K`). A higher LOW rate for successful than failed runs would therefore indicate a signal about eventual persistence beyond current depth. Similar rates within each depth, followed by a jump at `d>=3`, would indicate dependence mainly on the observed K-gate state.",
        "",
        "The table must be read with sample counts: small cells are diagnostic only, and the same anchors appear under both feature views rather than representing independent samples.",
        "",
        "## Reproducibility flags",
        "",
        "- Model training executed: `false`.",
        "- Model weights loaded: `false`.",
        "- New model inference executed: `false`.",
        "- Post-hoc prediction analysis executed: `true`.",
        "- Native labels mutated: `false`.",
    ]
    return "\n".join(lines) + "\n"


def _build_observed_findings(summary: pd.DataFrame) -> list[str]:
    lines: list[str] = []
    test = summary.loc[summary["partition"].astype("string").eq("test")]
    for view_id in sorted(test["feature_view_id"].astype("string").unique().tolist()):
        view = test.loc[test["feature_view_id"].astype("string").eq(view_id)]
        for depth in ("d=1", "d=2"):
            success = view.loc[
                view["run_outcome"].eq("successful") & view["depth_bin"].eq(depth)
            ].iloc[0]
            failed = view.loc[
                view["run_outcome"].eq("failed") & view["depth_bin"].eq(depth)
            ].iloc[0]
            if pd.notna(success["pred_low_rate"]) and pd.notna(failed["pred_low_rate"]):
                delta = float(success["pred_low_rate"]) - float(failed["pred_low_rate"])
                lines.append(
                    f"- `{view_id}` test `{depth}`: successful LOW rate "
                    f"`{float(success['pred_low_rate']):.4f}` versus failed "
                    f"`{float(failed['pred_low_rate']):.4f}` (difference `{delta:+.4f}`)."
                )
        depth_three = view.loc[
            view["run_outcome"].eq("successful") & view["depth_bin"].eq("d>=3")
        ].iloc[0]
        if pd.notna(depth_three["pred_low_rate"]):
            lines.append(
                f"- `{view_id}` test `d>=3`: LOW rate `"
                f"{float(depth_three['pred_low_rate']):.4f}` on `"
                f"{int(depth_three['prediction_rows'])}` rows; no failed `d>=3` "
                "stratum exists because a run reaching depth 3 is successful by definition."
            )
    return lines or ["- No test rows were available for the requested strata."]


def markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_empty_"
    display = frame.astype("string").fillna("")
    columns = list(display.columns)
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    rows = [
        "| " + " | ".join(str(value) for value in row) + " |"
        for row in display.itertuples(index=False, name=None)
    ]
    return "\n".join([header, separator, *rows])
