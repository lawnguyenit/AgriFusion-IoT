"""Markdown and static-figure writers for provenance-aware analysis."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .provenance_strata_analysis_data import PREDICTION_LABELS, PROVENANCE_STRATA


def write_online_heatmap(row_rates: pd.DataFrame, path: Path, *, partition: str = "test") -> None:
    """Write test row-normalized online 5 x 3 prediction heatmaps."""

    import matplotlib.pyplot as plt

    scope = row_rates.loc[
        (row_rates["prediction_source"].eq("online"))
        & (row_rates["partition"].eq(partition))
    ].copy()
    views = list(scope["feature_view_id"].astype("string").unique())
    if scope.empty or not views:
        return
    fig, axes = plt.subplots(
        1,
        len(views),
        figsize=(5.5 * len(views), 5.0),
        squeeze=False,
        dpi=150,
        constrained_layout=True,
    )
    image = None
    for index, view_id in enumerate(views):
        ax = axes[0][index]
        table = scope.loc[scope["feature_view_id"].eq(view_id)].set_index("provenance_stratum")
        values = table.loc[list(PROVENANCE_STRATA), [f"rate_{label}" for label in PREDICTION_LABELS]].astype(float).to_numpy()
        image = ax.imshow(values, vmin=0.0, vmax=1.0, cmap="Blues", aspect="auto")
        for row, stratum in enumerate(PROVENANCE_STRATA):
            for column, label in enumerate(PREDICTION_LABELS):
                ax.text(column, row, f"{values[row, column]:.2f}", ha="center", va="center", fontsize=9)
        ax.set_title(f"{str(view_id).replace('v2_', '')} — {partition}")
        ax.set_xticks(range(len(PREDICTION_LABELS)), PREDICTION_LABELS)
        ax.set_yticks(range(len(PROVENANCE_STRATA)), PROVENANCE_STRATA)
        ax.set_xlabel("Model prediction")
        ax.set_ylabel("True provenance stratum")
    fig.suptitle("Online model: provenance-aware row-normalized prediction map", y=1.02)
    if image is not None:
        fig.colorbar(image, ax=axes.ravel().tolist(), fraction=0.025, pad=0.03, label="Row rate")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def write_k_probability_plot(decomposition: pd.DataFrame, path: Path, *, partition: str = "test") -> None:
    """Write p_LOW for the three Q-positive state strata."""

    import matplotlib.pyplot as plt

    scope = decomposition.loc[
        (decomposition["prediction_source"].eq("online"))
        & (decomposition["partition"].eq(partition))
    ].copy()
    views = list(scope["feature_view_id"].astype("string").unique())
    if scope.empty or not views:
        return
    labels = ["U_K_fail\nd=1", "U_K_fail\nd=2", "U_K_succ\nd=1", "U_K_succ\nd=2", "LOW\nd>=3"]
    keys = [("U_K_fail", "d=1"), ("U_K_fail", "d=2"), ("U_K_succ", "d=1"), ("U_K_succ", "d=2"), ("LOW", "d>=3")]
    fig, axes = plt.subplots(1, len(views), figsize=(6.0 * len(views), 4.8), squeeze=False, dpi=150)
    for index, view_id in enumerate(views):
        ax = axes[0][index]
        table = scope.loc[scope["feature_view_id"].eq(view_id)].set_index(["provenance_stratum", "depth_bin"])
        values: list[float] = []
        counts: list[int] = []
        for key in keys:
            if key in table.index:
                row = table.loc[key]
                values.append(float(row["mean_p_LOW"]))
                counts.append(int(row["prediction_rows"]))
            else:
                values.append(0.0)
                counts.append(0)
        colors = ["#e45756", "#e45756", "#4c78a8", "#4c78a8", "#59a14f"]
        positions = list(range(len(labels)))
        ax.bar(positions, values, color=colors)
        for position, value, count in zip(positions, values, counts, strict=True):
            if count:
                ax.text(position, min(value + 0.03, 1.03), f"{value:.2f}\n(n={count})", ha="center", va="bottom", fontsize=8)
        ax.set_title(f"{str(view_id).replace('v2_', '')} — {partition}")
        ax.set_xticks(positions, labels)
        ax.set_ylim(0, 1.12)
        ax.set_ylabel("Mean p_LOW")
        ax.set_xlabel("Q-positive provenance state")
        ax.grid(axis="y", alpha=0.25)
    fig.suptitle("Online model: K-state versus eventual-run signal", y=1.02)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def write_event_online_delta_plot(deltas: pd.DataFrame, path: Path, *, partition: str = "test") -> None:
    """Write event-minus-online p_LOW deltas by provenance stratum."""

    import matplotlib.pyplot as plt

    scope = deltas.loc[deltas["partition"].eq(partition)].copy()
    views = list(scope["feature_view_id"].astype("string").unique())
    if scope.empty or not views:
        return
    fig, axes = plt.subplots(1, len(views), figsize=(5.5 * len(views), 4.8), squeeze=False, dpi=150)
    for index, view_id in enumerate(views):
        ax = axes[0][index]
        table = scope.loc[scope["feature_view_id"].eq(view_id)].set_index("provenance_stratum")
        values = [float(table.loc[stratum, "delta_event_minus_online_p_LOW"]) for stratum in PROVENANCE_STRATA]
        colors = ["#4c78a8" if value >= 0 else "#e45756" for value in values]
        positions = list(range(len(PROVENANCE_STRATA)))
        ax.bar(positions, values, color=colors)
        ax.axhline(0.0, color="#333333", linewidth=0.8)
        extent = max(max(abs(value) for value in values), 0.05)
        label_offset = max(extent * 0.08, 0.012)
        for position, value in zip(positions, values, strict=True):
            ax.text(
                position,
                value + (label_offset if value >= 0 else -label_offset),
                f"{value:+.2f}",
                ha="center",
                va="bottom" if value >= 0 else "top",
                fontsize=8,
            )
        ax.set_ylim(-extent * 1.20, extent * 1.20)
        ax.set_title(f"{str(view_id).replace('v2_', '')} — {partition}")
        ax.set_xticks(positions, PROVENANCE_STRATA)
        ax.set_ylabel("Event p_LOW − Online p_LOW")
        ax.set_xlabel("Shared provenance stratum")
        ax.grid(axis="y", alpha=0.25)
    fig.suptitle("Retrospective comparator: change in p_LOW", y=1.02)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def build_report(
    manifest: dict[str, object],
    provenance_summary: pd.DataFrame,
    online_counts: pd.DataFrame,
    online_rates: pd.DataFrame,
    online_probabilities: pd.DataFrame,
    event_counts: pd.DataFrame,
    event_rates: pd.DataFrame,
    event_probabilities: pd.DataFrame,
    k_decomposition: pd.DataFrame,
    k_contrasts: pd.DataFrame,
    comparator_deltas: pd.DataFrame,
    transitions: pd.DataFrame,
) -> str:
    test_counts = online_counts.loc[online_counts["partition"].eq("test")]
    test_rates = online_rates.loc[online_rates["partition"].eq("test")]
    test_probabilities = online_probabilities.loc[online_probabilities["partition"].eq("test")]
    test_k = k_decomposition.loc[(k_decomposition["prediction_source"].eq("online")) & (k_decomposition["partition"].eq("test"))]
    test_contrasts = k_contrasts.loc[(k_contrasts["prediction_source"].eq("online")) & (k_contrasts["partition"].eq("test"))]
    test_deltas = comparator_deltas.loc[comparator_deltas["partition"].eq("test")]
    test_event_counts = event_counts.loc[event_counts["partition"].eq("test")]
    test_event_rates = event_rates.loc[event_rates["partition"].eq("test")]
    test_event_probabilities = event_probabilities.loc[event_probabilities["partition"].eq("test")]
    lines = [
        "# Provenance-aware online model analysis — report",
        "",
        "> Main object: Y_online. The model still outputs only LOW/UNRES/REF; the five strata are audit metadata, not training classes.",
        "",
        "## Contract",
        "",
        f"- Model run: `{manifest['source_model_run_id']}`; profile `{manifest['profile_name']}`.",
        f"- Target-view artifact: `{manifest['source_target_views_artifact_id']}`.",
        f"- Locked operationalization: `{manifest['operationalization_id']}`; `K={manifest['selected_k']}`, `Q={manifest['q_value']}` with operator `{manifest['q_comparison_operator']}`.",
        "- Primary target: `Y_online`.",
        "- Provenance strata: `LOW`, `U_K_succ`, `U_K_fail`, `U_A`, `REF`.",
        "- Model outputs: `LOW`, `UNRES`, `REF`.",
        "- `L_r` is used only to stratify retrospective outcome; it is not a model feature.",
        "",
        "## Full labeled provenance population",
        "",
        markdown_table(provenance_summary),
        "",
        "## Tầng 1 — Online 5 x 3 map (test)",
        "",
        "### Hard prediction counts",
        "",
        markdown_table(_pivot_count_table(test_counts)),
        "",
        "### Row-normalized rates",
        "",
        markdown_table(_select_rate_columns(test_rates)),
        "",
        "### Mean output probabilities",
        "",
        markdown_table(_select_probability_columns(test_probabilities)),
        "",
        "## Tầng 2 — K-specific decomposition (test)",
        "",
        markdown_table(_select_k_columns(test_k)),
        "",
        "### K-specific contrasts",
        "",
        markdown_table(test_contrasts),
        "",
        "## Tầng 3 — Event comparator (test)",
        "",
        "Only `U_K_succ` changes target semantics (`Y_online=UNRES`, `Y_event=LOW`); the other strata retain their semantics.",
        "",
        "### Event-model hard prediction counts",
        "",
        markdown_table(_pivot_count_table(test_event_counts)),
        "",
        "### Event-model row-normalized rates",
        "",
        markdown_table(_select_rate_columns(test_event_rates)),
        "",
        "### Event-model mean output probabilities",
        "",
        markdown_table(_select_probability_columns(test_event_probabilities)),
        "",
        "### Event minus online probability deltas",
        "",
        markdown_table(test_deltas),
        "",
        "Hard prediction transitions are stored separately in `event_online_prediction_transitions.csv`.",
        "",
        "## Interpretation",
        "",
        "For `U_K_succ` and `U_K_fail`, the online training target is identical (`UNRES_K`). A higher online `p_LOW` for `U_K_succ` than `U_K_fail` is therefore an observational signal about feature geometry or eventual persistence, not a supervised distinction learned from the online label. `LOW` at `d>=3` mainly measures the current K-confirmation state.",
        "",
        "The event model is a retrospective semantic comparator, not independent ground truth. Small `U_K_succ` test support and the one-fold inherited split limit generalization claims.",
        "",
        "## Reproducibility flags",
        "",
        "- Model training executed: `false`.",
        "- New model inference executed: `false`.",
        "- Native labels mutated: `false`.",
        "- Target ontology changed: `false`.",
    ]
    return "\n".join(lines) + "\n"


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


def _pivot_count_table(counts: pd.DataFrame) -> pd.DataFrame:
    keys = ["prediction_source", "feature_view_id", "partition", "provenance_stratum"]
    table = counts.pivot_table(index=keys, columns="prediction_label", values="prediction_count", fill_value=0, aggfunc="sum").reset_index()
    for label in PREDICTION_LABELS:
        if label not in table.columns:
            table[label] = 0
    table = table.rename(columns={label: f"Pred_{label}" for label in PREDICTION_LABELS})
    return table.loc[:, keys + [f"Pred_{label}" for label in PREDICTION_LABELS]].convert_dtypes()


def _select_rate_columns(rates: pd.DataFrame) -> pd.DataFrame:
    columns = ["prediction_source", "feature_view_id", "partition", "provenance_stratum", "support", "rate_LOW", "rate_UNRES", "rate_REF"]
    return rates.loc[:, [column for column in columns if column in rates.columns]].convert_dtypes()


def _select_probability_columns(probabilities: pd.DataFrame) -> pd.DataFrame:
    columns = ["prediction_source", "feature_view_id", "partition", "provenance_stratum", "prediction_rows", "mean_p_LOW", "mean_p_UNRES", "mean_p_REF"]
    return probabilities.loc[:, [column for column in columns if column in probabilities.columns]].convert_dtypes()


def _select_k_columns(decomposition: pd.DataFrame) -> pd.DataFrame:
    columns = ["prediction_source", "feature_view_id", "partition", "provenance_stratum", "depth_bin", "prediction_rows", "pred_low_rate", "mean_p_LOW", "mean_p_UNRES", "mean_p_REF", "online_target_expected"]
    return decomposition.loc[:, [column for column in columns if column in decomposition.columns]].convert_dtypes()
