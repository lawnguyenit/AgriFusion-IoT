from __future__ import annotations

import argparse
import json
import math
import re
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
PRETRAIN_OUTPUT_ROOT = PRETRAIN_ROOT / "outputs"
VERSION_ORDER = ["v0", "v1", "v2", "v3", "v4"]
TREE_MODELS = ["hist_gradient_boosting", "random_forest", "lightgbm", "xgboost"]
BASELINE_PRIORITY = ["linear_probe", "torch_probe", "hist_gradient_boosting", "random_forest", "lightgbm", "xgboost"]
CONTRAST_PRIORITY = ["torch_probe", "hist_gradient_boosting", "random_forest", "lightgbm", "xgboost", "linear_probe"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate report-pack summaries and Word-friendly charts across v0-v4."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional output directory. Defaults to report_pack/<YYYY-MM-DD>-pack.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing artifacts if they already exist.",
    )
    parser.add_argument(
        "--lite",
        action="store_true",
        help="Generate a compact Word-friendly pack with fewer charts and lower visual density.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.output_dir is not None:
        output_dir = args.output_dir
    else:
        pack_root = "report_pack_lite" if args.lite else "report_pack"
        output_dir = BASE_DIR / pack_root / f"{date.today():%Y-%m-%d}-pack"
    charts_dir = output_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    pretrain_candidates = collect_pretrain_candidates()
    downstream_candidates = collect_downstream_candidates()

    if pretrain_candidates.empty or downstream_candidates.empty:
        raise FileNotFoundError("No matching benchmark reports were found for the report pack.")

    pretrain_selected = select_pretrain_candidates(pretrain_candidates)
    downstream_roles = select_downstream_roles(downstream_candidates)

    summary_df = build_version_summary(pretrain_selected, downstream_roles)

    pretrain_candidates.to_csv(output_dir / "pretrain_candidates.csv", index=False)
    pretrain_selected.to_csv(output_dir / "pretrain_selected.csv", index=False)
    downstream_candidates.to_csv(output_dir / "downstream_candidates.csv", index=False)
    downstream_roles.to_csv(output_dir / "downstream_roles.csv", index=False)
    summary_df.to_csv(output_dir / "report_pack_summary.csv", index=False)

    generated: list[Path] = []
    generated.append(
        save_grid_figure(
            charts_dir / "pretrain_selected_panels.png",
            1,
            2,
            lambda fig, axes: plot_pretrain_selected(fig, axes, pretrain_selected),
            overwrite=args.force,
        )
    )
    generated.append(
        save_grid_figure(
            charts_dir / "downstream_selected_roles.png",
            2,
            2,
            lambda fig, axes: plot_selected_roles(fig, axes, downstream_roles),
            overwrite=args.force,
        )
    )

    generated.append(
        save_grid_figure(
            charts_dir / "version_trajectory.png",
            1,
            2,
            lambda fig, axes: plot_version_trajectory(fig, axes, summary_df),
            overwrite=args.force,
        )
    )

    if not args.lite:
        for version in VERSION_ORDER:
            version_frame = downstream_candidates.loc[downstream_candidates["version"] == version].copy()
            if version_frame.empty:
                continue
            version_roles = downstream_roles.loc[
                downstream_roles["version"].astype(str) == version
            ][["version", "experiment_name", "model_name", "role"]]
            if not version_roles.empty:
                version_frame = version_frame.merge(
                    version_roles,
                    on=["version", "experiment_name", "model_name"],
                    how="left",
                )
            generated.append(
                save_grid_figure(
                    charts_dir / f"downstream_{version}_model_compare.png",
                    2,
                    1,
                    lambda fig, axes, frame=version_frame, version_name=version: plot_version_model_compare(
                        fig, axes, frame, version_name
                    ),
                    overwrite=args.force,
                )
            )
            for experiment_name in _ordered_versions(version_frame["experiment_name"].tolist()):
                experiment_frame = version_frame.loc[version_frame["experiment_name"].astype(str) == experiment_name].copy()
                if experiment_frame.empty:
                    continue
                generated.append(
                    save_grid_figure(
                        charts_dir / f"downstream_{version}_{experiment_name}_compare.png",
                        2,
                        1,
                        lambda fig, axes, frame=experiment_frame, version_name=f"{version}::{experiment_name}": plot_version_model_compare(
                            fig, axes, frame, version_name
                        ),
                        overwrite=args.force,
                    )
                )

    manifest = {
        "output_dir": str(output_dir),
        "generated_files": [str(path) for path in generated if path is not None],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


def collect_pretrain_candidates() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    latest_by_source: dict[tuple[str, str], Path] = {}

    for report_path in PRETRAIN_OUTPUT_ROOT.rglob("pretrain_report.json"):
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        version = str(report.get("benchmark_version", ""))
        source_kind = resolve_source_kind(report, report_path)
        if version not in VERSION_ORDER or not source_kind:
            continue
        key = (version, source_kind)
        current = latest_by_source.get(key)
        if current is None or report_path.stat().st_mtime > current.stat().st_mtime:
            latest_by_source[key] = report_path

    for (version, source_kind), report_path in sorted(latest_by_source.items()):
        report = json.loads(report_path.read_text(encoding="utf-8"))
        source_kind = resolve_source_kind(report, report_path)
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
        rows.append(
            {
                "version": version,
                "source_kind": source_kind,
                "run_id": report.get("run_id"),
                "pretrain_best_loss": float(best_loss) if best_loss is not None else float("nan"),
                "best_epoch": int(training.get("best_epoch", report.get("best_epoch", -1))),
                "epochs_ran": len(training.get("validation_loss", []) or []),
                "feature_count": len(feature_columns),
                "rows_after_cleaning": int(row_counts.get("after_cleaning", 0)),
                "excluded_rows": int(split_policy.get("excluded_row_count", 0)),
                "gap_minutes": int(split_policy.get("gap_minutes", 0)),
            }
        )

    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    return frame.sort_values(["version", "pretrain_best_loss", "source_kind"], ascending=[True, True, True])


def collect_downstream_candidates() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for version in VERSION_ORDER:
        report_path = find_latest_downstream_report(version)
        if report_path is None:
            continue
        report = json.loads(report_path.read_text(encoding="utf-8"))
        metrics_path = report_path.parent / "aggregate_model_metrics.csv"
        if not metrics_path.exists():
            metrics_path = report_path.parent / "model_metrics.csv"
        if not metrics_path.exists():
            continue
        metrics_df = pd.read_csv(metrics_path)
        if metrics_df.empty:
            continue
        if "experiment_name" not in metrics_df.columns:
            metrics_df = metrics_df.copy()
            metrics_df["experiment_name"] = "run"
        metrics_df["version"] = version
        metrics_df["run_id"] = report.get("run_id")
        for _, row in metrics_df.iterrows():
            rows.append(
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
                    "artifact_path": row.get("artifact_path"),
                    "checkpoint_path": row.get("checkpoint_path"),
                }
            )

    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    return frame.sort_values(
        ["version", "validation_macro_f1", "test_macro_f1"],
        ascending=[True, False, False],
        na_position="last",
    )


def resolve_source_kind(report: dict[str, object], report_path: Path) -> str:
    source_kind = report.get("source_kind")
    if isinstance(source_kind, str) and source_kind:
        return source_kind
    checkpoint_config = report.get("pretrain_checkpoint_config")
    if isinstance(checkpoint_config, dict):
        nested = checkpoint_config.get("source_kind")
        if isinstance(nested, str) and nested:
            return nested
    run_id = str(report.get("run_id") or report_path.parent.name)
    match = re.match(r"^v\d+_(.+)_(\d{8}_\d{6})$", run_id)
    if match:
        return match.group(1)
    parent_name = report_path.parent.name
    match = re.match(r"^v\d+_(.+)_(\d{6})$", parent_name)
    if match:
        return match.group(1)
    return parent_name


def select_pretrain_candidates(pretrain_candidates: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for version in VERSION_ORDER:
        frame = pretrain_candidates.loc[pretrain_candidates["version"] == version].copy()
        if frame.empty:
            continue
        best_row = frame.sort_values(["pretrain_best_loss", "best_epoch"], ascending=[True, True]).iloc[0]
        row = best_row.to_dict()
        row["selected"] = True
        rows.append(row)
    return pd.DataFrame(rows)


def select_downstream_roles(downstream_candidates: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for version in VERSION_ORDER:
        frame = downstream_candidates.loc[downstream_candidates["version"] == version].copy()
        if frame.empty:
            continue
        selected = select_roles_for_version(frame)
        for role_name, row in selected.items():
            row = dict(row)
            row["role"] = role_name
            row["role_reason"] = role_reason(role_name)
            rows.append(row)
    return pd.DataFrame(rows)


def select_roles_for_version(frame: pd.DataFrame) -> dict[str, pd.Series]:
    baseline = pick_by_priority(frame, BASELINE_PRIORITY)
    contrast = pick_by_priority(frame, CONTRAST_PRIORITY, exclude={baseline.name} if baseline is not None else None)
    tree_main = pick_best_tree(frame, exclude={baseline.name} if baseline is not None else None)
    if tree_main is None:
        tree_main = pick_best_overall(frame, exclude={baseline.name} if baseline is not None else None)
    if contrast is None:
        contrast = pick_best_overall(frame, exclude={baseline.name} if baseline is not None else None)
    selected: dict[str, pd.Series] = {}
    if baseline is not None:
        selected["baseline"] = baseline
    if contrast is not None:
        selected["contrast"] = contrast
    if tree_main is not None:
        selected["main"] = tree_main
    return selected


def pick_by_priority(frame: pd.DataFrame, priority: list[str], exclude: set[str] | None = None) -> pd.Series | None:
    exclude = exclude or set()
    for model_name in priority:
        subset = frame.loc[
            (frame["model_name"].astype(str) == model_name) & (~frame.index.astype(str).isin(exclude))
        ]
        if subset.empty:
            continue
        return subset.sort_values(["validation_macro_f1", "test_macro_f1"], ascending=[False, False]).iloc[0]
    return None


def pick_best_tree(frame: pd.DataFrame, exclude: set[str] | None = None) -> pd.Series | None:
    exclude = exclude or set()
    subset = frame.loc[
        frame["model_name"].astype(str).isin(TREE_MODELS) & (~frame.index.astype(str).isin(exclude))
    ]
    if subset.empty:
        return None
    return subset.sort_values(["validation_macro_f1", "test_macro_f1"], ascending=[False, False]).iloc[0]


def pick_best_overall(frame: pd.DataFrame, exclude: set[str] | None = None) -> pd.Series | None:
    exclude = exclude or set()
    subset = frame.loc[~frame.index.astype(str).isin(exclude)]
    if subset.empty:
        return None
    return subset.sort_values(["validation_macro_f1", "test_macro_f1"], ascending=[False, False]).iloc[0]


def role_reason(role: str) -> str:
    if role == "baseline":
        return "linear separability check"
    if role == "contrast":
        return "minimal nonlinear adapter check"
    return "practical tree-ensemble candidate"


def build_version_summary(pretrain_selected: pd.DataFrame, downstream_roles: pd.DataFrame) -> pd.DataFrame:
    if pretrain_selected.empty or downstream_roles.empty:
        return pd.DataFrame()
    baseline = downstream_roles.loc[downstream_roles["role"] == "baseline", [
        "version",
        "experiment_name",
        "model_name",
        "validation_macro_f1",
        "validation_balanced_accuracy",
        "test_macro_f1",
        "test_balanced_accuracy",
    ]].rename(
        columns={
            "experiment_name": "baseline_experiment",
            "model_name": "baseline_model",
            "validation_macro_f1": "baseline_validation_macro_f1",
            "validation_balanced_accuracy": "baseline_validation_balanced_accuracy",
            "test_macro_f1": "baseline_test_macro_f1",
            "test_balanced_accuracy": "baseline_test_balanced_accuracy",
        }
    )
    contrast = downstream_roles.loc[downstream_roles["role"] == "contrast", [
        "version",
        "experiment_name",
        "model_name",
        "validation_macro_f1",
        "validation_balanced_accuracy",
        "test_macro_f1",
        "test_balanced_accuracy",
    ]].rename(
        columns={
            "experiment_name": "contrast_experiment",
            "model_name": "contrast_model",
            "validation_macro_f1": "contrast_validation_macro_f1",
            "validation_balanced_accuracy": "contrast_validation_balanced_accuracy",
            "test_macro_f1": "contrast_test_macro_f1",
            "test_balanced_accuracy": "contrast_test_balanced_accuracy",
        }
    )
    main = downstream_roles.loc[downstream_roles["role"] == "main", [
        "version",
        "experiment_name",
        "model_name",
        "validation_macro_f1",
        "validation_balanced_accuracy",
        "test_macro_f1",
        "test_balanced_accuracy",
    ]].rename(
        columns={
            "experiment_name": "main_experiment",
            "model_name": "main_model",
            "validation_macro_f1": "main_validation_macro_f1",
            "validation_balanced_accuracy": "main_validation_balanced_accuracy",
            "test_macro_f1": "main_test_macro_f1",
            "test_balanced_accuracy": "main_test_balanced_accuracy",
        }
    )
    summary = pretrain_selected.merge(baseline, on="version", how="left")
    summary = summary.merge(contrast, on="version", how="left")
    summary = summary.merge(main, on="version", how="left")
    return summary.sort_values("version", key=_version_sort_key)


def plot_pretrain_selected(fig: plt.Figure, axes: np.ndarray, summary: pd.DataFrame) -> None:
    plots = [
        (axes[0, 0], "pretrain_best_loss", "Selected pretrain best loss", "#4c78a8", "{:.2f}"),
        (axes[0, 1], "best_epoch", "Selected pretrain best epoch", "#72b7b2", "{:.0f}"),
    ]
    labels = [
        f'{row["version"]}\n{row["source_kind"]}' for _, row in summary.iterrows()
    ]
    for ax, column, title, color, fmt in plots:
        bars = ax.bar(labels, summary[column].to_numpy(dtype=float), color=color)
        ax.set_title(title)
        ax.grid(axis="y", alpha=0.25)
        annotate_bars(ax, bars, fmt=fmt)
        for label in ax.get_xticklabels():
            label.set_fontsize(9)
    axes[0, 0].set_ylabel("loss (lower is better)")
    axes[0, 1].set_ylabel("epoch")
    fig.suptitle("Selected pretrain candidate per version", fontsize=15)


def plot_selected_roles(fig: plt.Figure, axes: np.ndarray, summary: pd.DataFrame) -> None:
    panels = [
        (axes[0, 0], "validation_macro_f1", "Selected role validation macro F1"),
        (axes[0, 1], "test_macro_f1", "Selected role test macro F1"),
        (axes[1, 0], "validation_balanced_accuracy", "Selected role validation balanced accuracy"),
        (axes[1, 1], "test_balanced_accuracy", "Selected role test balanced accuracy"),
    ]
    role_order = ["baseline", "contrast", "main"]
    colors = {"baseline": "#4c78a8", "contrast": "#f58518", "main": "#54a24b"}
    versions = _ordered_versions(summary["version"].tolist())
    x = np.arange(len(versions))
    width = 0.25
    for ax, column, title in panels:
        for idx, role in enumerate(role_order):
            role_frame = summary.loc[summary["role"] == role].copy()
            if role_frame.empty:
                continue
            role_frame = role_frame.set_index("version").reindex(versions)
            bars = ax.bar(
                x + (idx - 1) * width,
                role_frame[column].to_numpy(dtype=float),
                width=width,
                color=colors[role],
                label=role,
            )
            annotate_bars(ax, bars, fmt="{:.2f}")
        ax.set_title(title)
        ax.set_xticks(x)
        ax.set_xticklabels(versions)
        ax.set_ylim(0, 1.0)
        ax.grid(axis="y", alpha=0.25)
        ax.legend(loc="best")
    axes[0, 0].set_ylabel("score")
    axes[1, 0].set_ylabel("score")
    axes[1, 1].set_ylabel("score")
    fig.suptitle("Selected baseline / contrast / main roles by version", fontsize=15)


def plot_version_model_compare(fig: plt.Figure, axes: np.ndarray, frame: pd.DataFrame, version_name: str) -> None:
    frame = frame.sort_values(["validation_macro_f1", "test_macro_f1"], ascending=[False, False]).copy()
    role_lookup = {
        (str(row["experiment_name"]), str(row["model_name"])): clean_text(row.get("role"))
        for _, row in frame.iterrows()
        if "role" in row.index
    }
    labels = [
        build_version_model_label(row, role_lookup)
        for _, row in frame.iterrows()
    ]
    panels = [
        (axes[0], "validation_macro_f1", "test_macro_f1", "Macro F1"),
        (axes[1], "validation_balanced_accuracy", "test_balanced_accuracy", "Balanced accuracy"),
    ]
    x = np.arange(len(frame))
    width = 0.35
    for ax, val_col, test_col, title in panels:
        if isinstance(ax, np.ndarray):
            ax = ax.item()
        val_bars = ax.bar(x - width / 2, frame[val_col].to_numpy(dtype=float), width=width, color="#4c78a8", label="validation")
        test_bars = ax.bar(x + width / 2, frame[test_col].to_numpy(dtype=float), width=width, color="#54a24b", label="test")
        annotate_bars(ax, val_bars, fmt="{:.2f}")
        annotate_bars(ax, test_bars, fmt="{:.2f}")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=0)
        ax.set_ylim(0, 1.0)
        ax.grid(axis="y", alpha=0.25)
        ax.set_ylabel("score")
        ax.set_title(f"{version_name} :: {title}")
        ax.legend(loc="best")
        for label in ax.get_xticklabels():
            label.set_fontsize(9)
    fig.suptitle(f"Model comparison for {version_name}", fontsize=15)


def plot_version_trajectory(fig: plt.Figure, axes: np.ndarray, summary: pd.DataFrame) -> None:
    versions = _ordered_versions(summary["version"].tolist())
    frame = summary.set_index("version").reindex(versions)

    ax = axes[0, 0]
    ax.plot(versions, frame["pretrain_best_loss"].to_numpy(dtype=float), marker="o", linewidth=2.0, color="#4c78a8")
    for x, y in zip(versions, frame["pretrain_best_loss"].to_numpy(dtype=float)):
        ax.text(x, y + 0.01, f"{y:.2f}", ha="center", va="bottom", fontsize=8)
    ax.set_title("Selected pretrain loss by version")
    ax.set_ylabel("loss (lower is better)")
    ax.grid(axis="y", alpha=0.25)

    ax = axes[0, 1]
    ax.plot(versions, frame["main_validation_macro_f1"].to_numpy(dtype=float), marker="o", linewidth=2.0, label="validation", color="#4c78a8")
    ax.plot(versions, frame["main_test_macro_f1"].to_numpy(dtype=float), marker="o", linewidth=2.0, label="test", color="#54a24b")
    for series, color in [
        (frame["main_validation_macro_f1"].to_numpy(dtype=float), "#4c78a8"),
        (frame["main_test_macro_f1"].to_numpy(dtype=float), "#54a24b"),
    ]:
        for x, y in zip(versions, series):
            ax.text(x, y + 0.01, f"{y:.2f}", ha="center", va="bottom", fontsize=8, color=color)
    ax.set_title("Selected main model macro F1 by version")
    ax.set_ylabel("macro F1")
    ax.set_ylim(0, 1.0)
    ax.grid(axis="y", alpha=0.25)
    ax.legend(loc="best")

    fig.suptitle("Compact version trajectory", fontsize=15)


def annotate_bars(ax: plt.Axes, bars, *, fmt: str) -> None:
    for bar in bars:
        height = bar.get_height()
        if math.isnan(float(height)):
            continue
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            height + 0.01,
            fmt.format(float(height)),
            ha="center",
            va="bottom",
            fontsize=8,
        )


def build_version_model_label(row: pd.Series, role_lookup: dict[tuple[str, str], str | None]) -> str:
    experiment_name = str(row["experiment_name"])
    model_name = str(row["model_name"])
    role = clean_text(role_lookup.get((experiment_name, model_name)))
    label = f"{experiment_name}\n{model_name}"
    if role:
        label += f"\n[{role}]"
    return label


def save_grid_figure(path: Path, nrows: int, ncols: int, plotter, *, overwrite: bool) -> Path:
    if path.exists() and not overwrite:
        return path
    fig, axes = plt.subplots(nrows, ncols, figsize=(7.5 * ncols, 4.5 * nrows))
    if nrows == 1 and ncols == 1:
        axes = np.array([[axes]])
    elif nrows == 1:
        axes = np.array([axes])
    elif ncols == 1:
        axes = np.array([[ax] for ax in axes])
    try:
        plotter(fig, axes)
        fig.tight_layout(rect=(0, 0, 1, 0.96))
        fig.savefig(path, dpi=180, bbox_inches="tight")
    finally:
        plt.close(fig)
    return path


def find_latest_downstream_report(version: str) -> Path | None:
    root = BASE_DIR / version / "outputs"
    if not root.exists():
        return None
    candidates = list(root.rglob("training_report.json"))
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


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


def clean_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return text


def _version_sort_key(series: pd.Series) -> pd.Series:
    return series.map(lambda value: int(str(value).lstrip("v")) if str(value).lstrip("v").isdigit() else str(value))


def _ordered_versions(values: Iterable[object]) -> list[str]:
    unique = []
    seen = set()
    for value in values:
        text = str(value)
        if text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return sorted(unique, key=lambda item: int(item.lstrip("v")) if item.lstrip("v").isdigit() else item)


if __name__ == "__main__":
    main()
