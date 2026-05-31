from __future__ import annotations

import argparse
import json
import math
from datetime import date
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from Backend.Benchmark.common.paths import PRETRAIN_ROOT, PRETRAIN_SUPERVISED_ROOT

BASE_DIR = PRETRAIN_SUPERVISED_ROOT


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate layered summary charts across v0-v4 benchmark runs."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional output directory. Defaults to charts_summary/<YYYY-MM-DD>-summary.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing charts if they already exist.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary_dir = args.output_dir or (BASE_DIR / "charts_summary" / f"{date.today():%Y-%m-%d}-summary")
    summary_dir.mkdir(parents=True, exist_ok=True)

    version_order = ["v0", "v1", "v2", "v3", "v4"]
    pretrain_rows: list[dict[str, object]] = []
    downstream_rows: list[dict[str, object]] = []
    model_rows: list[dict[str, object]] = []

    for version in version_order:
        pretrain_report = find_latest_pretrain_report(version)
        downstream_report = find_latest_downstream_report(version)
        if pretrain_report is None or downstream_report is None:
            continue

        pretrain_rows.append(read_pretrain_summary(version, pretrain_report))
        version_downstream_rows, model_rows_for_version = read_downstream_summary(version, downstream_report)
        downstream_rows.append(version_downstream_rows)
        model_rows.extend(model_rows_for_version)

    if not pretrain_rows or not downstream_rows:
        raise FileNotFoundError("No matching v0-v4 benchmark reports were found.")

    pretrain_df = pd.DataFrame(pretrain_rows).sort_values("version", key=_version_sort_key)
    downstream_df = pd.DataFrame(downstream_rows).sort_values("version", key=_version_sort_key)
    model_df = pd.DataFrame(model_rows)
    version_df = pretrain_df.rename(columns={"run_id": "pretrain_run_id"}).merge(
        downstream_df.rename(columns={"run_id": "downstream_run_id"}),
        on="version",
        how="outer",
        validate="one_to_one",
    )
    version_df = version_df.sort_values("version", key=_version_sort_key)
    best_model_df = build_best_model_summary(downstream_df, model_df)

    version_df.to_csv(summary_dir / "version_summary.csv", index=False)
    pretrain_df.to_csv(summary_dir / "pretrain_summary.csv", index=False)
    downstream_df.to_csv(summary_dir / "downstream_summary.csv", index=False)
    if not model_df.empty:
        model_df.to_csv(summary_dir / "model_metrics_summary.csv", index=False)
    if not best_model_df.empty:
        best_model_df.to_csv(summary_dir / "best_model_summary.csv", index=False)

    generated: list[Path] = []
    generated.append(
        save_grid_figure(
            summary_dir / "pretrain_summary_panels.png",
            lambda fig, axes: plot_pretrain_panels(fig, axes, pretrain_df),
            overwrite=args.force,
        )
    )
    generated.append(
        save_grid_figure(
            summary_dir / "downstream_summary_panels.png",
            lambda fig, axes: plot_downstream_panels(fig, axes, downstream_df),
            overwrite=args.force,
        )
    )
    if not model_df.empty:
        generated.append(
            save_grid_figure(
                summary_dir / "best_model_panels.png",
                lambda fig, axes: plot_best_model_panels(fig, axes, best_model_df),
                overwrite=args.force,
            )
        )
        generated.append(
            save_heatmap_figure(
                summary_dir / "model_metrics_heatmap.png",
                lambda fig, axes: plot_model_heatmap(fig, axes, model_df),
                overwrite=args.force,
                row_count=len(model_df),
            )
        )

    manifest = {
        "summary_dir": str(summary_dir),
        "generated_files": [str(path) for path in generated if path is not None],
    }
    (summary_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


def find_latest_pretrain_report(version: str) -> Path | None:
    candidates: list[Path] = []
    for report_path in (PRETRAIN_ROOT / "outputs").rglob("pretrain_report.json"):
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if report.get("benchmark_version") != version:
            continue
        candidates.append(report_path)
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def find_latest_downstream_report(version: str) -> Path | None:
    root = BASE_DIR / version / "outputs"
    if not root.exists():
        return None
    candidates = list(root.rglob("training_report.json"))
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def read_pretrain_summary(version: str, report_path: Path) -> dict[str, object]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    training = report.get("training", {}) or {}
    split_policy = report.get("split_policy", {}) or {}
    row_counts = report.get("row_counts", {}) or {}
    feature_columns = report.get("feature_columns", []) or []

    best_loss = (
        training.get("best_validation_loss")
        or training.get("best_validation_masked_mse")
        or report.get("best_validation_loss")
        or report.get("best_validation_masked_mse")
    )
    if best_loss is None:
        raise KeyError(f"No pretrain loss field found in {report_path}")

    return {
        "version": version,
        "run_id": report.get("run_id"),
        "input_csv": Path(str(report.get("input_csv", ""))).name,
        "pretrain_best_loss": float(best_loss),
        "best_epoch": int(training.get("best_epoch", report.get("best_epoch", -1))),
        "epochs_ran": len(training.get("validation_loss", []) or []),
        "feature_count": len(feature_columns),
        "rows_after_cleaning": int(row_counts.get("after_cleaning", 0)),
        "excluded_rows": int(split_policy.get("excluded_row_count", 0)),
        "gap_minutes": int(split_policy.get("gap_minutes", 0)),
    }


def read_downstream_summary(version: str, report_path: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    run_dir = report_path.parent
    metrics_path = run_dir / "aggregate_model_metrics.csv"
    if not metrics_path.exists():
        metrics_path = run_dir / "model_metrics.csv"
    if not metrics_path.exists():
        raise FileNotFoundError(f"No model metrics found for {run_dir}")

    metrics_df = pd.read_csv(metrics_path)
    if metrics_df.empty:
        raise ValueError(f"Empty model metrics at {metrics_path}")

    if "experiment_name" not in metrics_df.columns:
        metrics_df = metrics_df.copy()
        metrics_df["experiment_name"] = "run"

    metrics_df["version"] = version

    best_experiment, best_model = get_best_experiment_and_model(report)
    best_row = select_best_metric_row(metrics_df, best_experiment, best_model)

    summary = {
        "version": version,
        "run_id": report.get("run_id"),
        "best_experiment": best_experiment,
        "best_model": best_model,
        "validation_accuracy": numeric_or_nan(best_row, "validation_accuracy"),
        "validation_balanced_accuracy": numeric_or_nan(best_row, "validation_balanced_accuracy"),
        "validation_macro_f1": numeric_or_nan(best_row, "validation_macro_f1"),
        "validation_weighted_f1": numeric_or_nan(best_row, "validation_weighted_f1"),
        "test_accuracy": numeric_or_nan(best_row, "test_accuracy"),
        "test_balanced_accuracy": numeric_or_nan(best_row, "test_balanced_accuracy"),
        "test_macro_f1": numeric_or_nan(best_row, "test_macro_f1"),
        "test_weighted_f1": numeric_or_nan(best_row, "test_weighted_f1"),
    }

    model_rows: list[dict[str, object]] = []
    for _, row in metrics_df.iterrows():
        model_rows.append(
            {
                "version": version,
                "run_id": report.get("run_id"),
                "experiment_name": row.get("experiment_name", "run"),
                "model_name": row.get("model_name"),
                "validation_accuracy": numeric_or_nan(row, "validation_accuracy"),
                "validation_balanced_accuracy": numeric_or_nan(row, "validation_balanced_accuracy"),
                "validation_macro_f1": numeric_or_nan(row, "validation_macro_f1"),
                "validation_weighted_f1": numeric_or_nan(row, "validation_weighted_f1"),
                "test_accuracy": numeric_or_nan(row, "test_accuracy"),
                "test_balanced_accuracy": numeric_or_nan(row, "test_balanced_accuracy"),
                "test_macro_f1": numeric_or_nan(row, "test_macro_f1"),
                "test_weighted_f1": numeric_or_nan(row, "test_weighted_f1"),
            }
        )

    return summary, model_rows


def build_best_model_summary(downstream_df: pd.DataFrame, model_df: pd.DataFrame) -> pd.DataFrame:
    if downstream_df.empty or model_df.empty:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    for _, version_row in downstream_df.iterrows():
        version = version_row["version"]
        experiment_name = version_row.get("best_experiment")
        model_name = version_row.get("best_model")
        subset = model_df.loc[
            (model_df["version"].astype(str) == str(version))
            & (model_df["experiment_name"].astype(str) == str(experiment_name))
            & (model_df["model_name"].astype(str) == str(model_name))
        ]
        if subset.empty:
            continue
        row = subset.iloc[0].to_dict()
        row["best_experiment"] = experiment_name
        row["best_model"] = model_name
        rows.append(row)
    return pd.DataFrame(rows).sort_values("version", key=_version_sort_key)


def get_best_experiment_and_model(report: dict[str, object]) -> tuple[str | None, str | None]:
    if "best_result" in report and isinstance(report["best_result"], dict):
        best = report["best_result"]
        return best.get("experiment_name"), best.get("model_name")
    if "selected_model" in report and isinstance(report["selected_model"], dict):
        best = report["selected_model"]
        return "run", best.get("model_name")
    return None, None


def select_best_metric_row(metrics_df: pd.DataFrame, experiment_name: str | None, model_name: str | None) -> pd.Series:
    frame = metrics_df.copy()
    if experiment_name is not None and "experiment_name" in frame.columns:
        subset = frame.loc[frame["experiment_name"].astype(str) == str(experiment_name)]
        if model_name is not None:
            subset = subset.loc[subset["model_name"].astype(str) == str(model_name)]
        if not subset.empty:
            return subset.iloc[0]
    if model_name is not None:
        subset = frame.loc[frame["model_name"].astype(str) == str(model_name)]
        if not subset.empty:
            if "validation_macro_f1" in subset.columns:
                return subset.sort_values(by="validation_macro_f1", ascending=False).iloc[0]
            return subset.iloc[0]
    if "validation_macro_f1" in frame.columns:
        return frame.sort_values(by="validation_macro_f1", ascending=False).iloc[0]
    return frame.iloc[0]


def numeric_or_nan(row: pd.Series, column: str) -> float:
    if column not in row.index:
        return float("nan")
    value = row[column]
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return float("nan")
    try:
        return float(value)
    except Exception:
        return float("nan")


def plot_pretrain_panels(fig: plt.Figure, axes: np.ndarray, summary: pd.DataFrame) -> None:
    ax = axes[0, 0]
    bars = ax.bar(summary["version"], summary["pretrain_best_loss"], color="#4c78a8")
    ax.set_title("Pretrain best validation loss")
    ax.set_ylabel("loss (lower is better)")
    ax.grid(axis="y", alpha=0.25)
    annotate_bars(ax, bars, fmt="{:.4f}")

    ax = axes[0, 1]
    bars = ax.bar(summary["version"], summary["best_epoch"], color="#72b7b2")
    ax.set_title("Best pretrain epoch")
    ax.set_ylabel("epoch")
    ax.grid(axis="y", alpha=0.25)
    annotate_bars(ax, bars, fmt="{:.0f}")

    ax = axes[1, 0]
    bars = ax.bar(summary["version"], summary["feature_count"], color="#f58518")
    ax.set_title("Feature count")
    ax.set_ylabel("features")
    ax.grid(axis="y", alpha=0.25)
    annotate_bars(ax, bars, fmt="{:.0f}")

    ax = axes[1, 1]
    bars = ax.bar(summary["version"], summary["excluded_rows"], color="#e45756")
    ax.set_title("Excluded purge-gap rows")
    ax.set_ylabel("rows")
    ax.grid(axis="y", alpha=0.25)
    annotate_bars(ax, bars, fmt="{:.0f}")

    fig.suptitle("Pretrain summary by version", fontsize=15)


def plot_downstream_panels(fig: plt.Figure, axes: np.ndarray, summary: pd.DataFrame) -> None:
    plots = [
        (axes[0, 0], "validation_macro_f1", "Validation macro F1", "#4c78a8"),
        (axes[0, 1], "test_macro_f1", "Test macro F1", "#54a24b"),
        (axes[1, 0], "validation_balanced_accuracy", "Validation balanced accuracy", "#f58518"),
        (axes[1, 1], "test_balanced_accuracy", "Test balanced accuracy", "#e45756"),
    ]
    for ax, column, title, color in plots:
        vals = summary[column].to_numpy(dtype=float)
        bars = ax.bar(summary["version"], vals, color=color)
        ax.set_title(title)
        ax.set_ylabel("score")
        ax.set_ylim(0, 1.0)
        ax.grid(axis="y", alpha=0.25)
        annotate_bars(ax, bars, fmt="{:.4f}")
    fig.suptitle("Downstream summary by version", fontsize=15)


def plot_model_heatmap(fig: plt.Figure, ax: plt.Axes, model_rows: pd.DataFrame) -> None:
    model_rows = model_rows.copy()
    model_rows["row_label"] = (
        model_rows["version"].astype(str)
        + " | "
        + model_rows["experiment_name"].astype(str)
        + " | "
        + model_rows["model_name"].astype(str)
    )
    row_labels = model_rows["row_label"].tolist()
    metric_columns = [
        "validation_accuracy",
        "validation_balanced_accuracy",
        "validation_macro_f1",
        "test_accuracy",
        "test_balanced_accuracy",
        "test_macro_f1",
    ]
    matrix = model_rows[metric_columns].to_numpy(dtype=float)
    masked = np.ma.masked_invalid(matrix)
    cmap = plt.cm.viridis.copy()
    cmap.set_bad(color="#e6e6e6")
    im = ax.imshow(masked, aspect="auto", cmap=cmap)
    ax.set_xticks(np.arange(len(metric_columns)))
    ax.set_xticklabels(metric_columns, rotation=25, ha="right")
    ax.set_yticks(np.arange(len(row_labels)))
    ax.set_yticklabels(row_labels, fontsize=8)
    ax.set_title("Model metrics across all versions / experiments")
    ax.set_xlabel("metric")
    ax.set_ylabel("version | experiment | model")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    for i in range(len(row_labels)):
        for j in range(len(metric_columns)):
            value = matrix[i, j]
            if not math.isnan(value):
                ax.text(j, i, f"{value:.2f}", ha="center", va="center", color="white", fontsize=7)


def plot_best_model_panels(fig: plt.Figure, axes: np.ndarray, summary: pd.DataFrame) -> None:
    plots = [
        (axes[0, 0], "validation_macro_f1", "Best model validation macro F1", "#4c78a8"),
        (axes[0, 1], "test_macro_f1", "Best model test macro F1", "#54a24b"),
        (axes[1, 0], "validation_balanced_accuracy", "Best model validation balanced accuracy", "#f58518"),
        (axes[1, 1], "test_balanced_accuracy", "Best model test balanced accuracy", "#e45756"),
    ]
    for ax, column, title, color in plots:
        vals = summary[column].to_numpy(dtype=float)
        labels = [
            f'{row["version"]}\n{row["best_experiment"]}/{row["best_model"]}'
            for _, row in summary.iterrows()
        ]
        bars = ax.bar(labels, vals, color=color)
        ax.set_title(title)
        ax.set_ylabel("score")
        ax.set_ylim(0, 1.0)
        ax.grid(axis="y", alpha=0.25)
        ax.tick_params(axis="x", labelrotation=0)
        annotate_bars(ax, bars, fmt="{:.4f}")
        for label in ax.get_xticklabels():
            label.set_fontsize(9)
    fig.suptitle("Best downstream model per version", fontsize=15)


def annotate_bars(ax: plt.Axes, bars, *, fmt: str) -> None:
    for bar in bars:
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            height + 0.01,
            fmt.format(height),
            ha="center",
            va="bottom",
            fontsize=8,
        )


def save_grid_figure(path: Path, plotter, *, overwrite: bool) -> Path:
    if path.exists() and not overwrite:
        return path
    fig, axes = plt.subplots(2, 2, figsize=(16, 11))
    try:
        plotter(fig, axes)
        fig.tight_layout(rect=(0, 0, 1, 0.96))
        fig.savefig(path, dpi=180, bbox_inches="tight")
    finally:
        plt.close(fig)
    return path


def save_heatmap_figure(path: Path, plotter, *, overwrite: bool, row_count: int) -> Path:
    if path.exists() and not overwrite:
        return path
    height = max(8.0, 0.30 * float(row_count) + 3.5)
    fig, axes = plt.subplots(1, 1, figsize=(18, height))
    try:
        plotter(fig, axes)
        fig.tight_layout(rect=(0, 0, 1, 0.97))
        fig.savefig(path, dpi=180, bbox_inches="tight")
    finally:
        plt.close(fig)
    return path


def _version_sort_key(series: pd.Series) -> pd.Series:
    return series.map(lambda value: int(str(value).lstrip("v")) if str(value).lstrip("v").isdigit() else str(value))


if __name__ == "__main__":
    main()
