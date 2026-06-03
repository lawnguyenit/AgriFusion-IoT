from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[4]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate PNG charts from pretrain and downstream benchmark outputs."
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="Run directories or output roots to scan for pretrain_report.json / training_report.json.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing chart files if they already exist.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_dirs = discover_run_dirs(args.paths)
    if not run_dirs:
        raise FileNotFoundError("No benchmark run directories were found under the provided paths.")

    for run_dir in run_dirs:
        generated = generate_charts_for_run(run_dir, overwrite=args.force)
        if generated:
            print(f"{run_dir}:")
            for path in generated:
                print(f"  - {path}")


def discover_run_dirs(paths: Iterable[Path]) -> list[Path]:
    discovered: dict[str, Path] = {}
    for raw_path in paths:
        path = raw_path.resolve()
        if not path.exists():
            continue
        if is_run_dir(path):
            discovered[str(path)] = path
            continue
        for report_path in path.rglob("pretrain_report.json"):
            discovered[str(report_path.parent.resolve())] = report_path.parent.resolve()
        for report_path in path.rglob("training_report.json"):
            discovered[str(report_path.parent.resolve())] = report_path.parent.resolve()
    return [discovered[key] for key in sorted(discovered)]


def is_run_dir(path: Path) -> bool:
    return (path / "pretrain_report.json").exists() or (path / "training_report.json").exists()


def generate_charts_for_run(run_dir: Path, *, overwrite: bool = False) -> list[Path]:
    generated: list[Path] = []
    charts_root = run_dir / "charts"
    charts_root.mkdir(parents=True, exist_ok=True)

    pretrain_report_path = run_dir / "pretrain_report.json"
    if pretrain_report_path.exists():
        generated.extend(generate_pretrain_charts(run_dir, pretrain_report_path, charts_root, overwrite=overwrite))

    downstream_report_path = run_dir / "training_report.json"
    if downstream_report_path.exists():
        generated.extend(generate_downstream_charts(run_dir, downstream_report_path, charts_root, overwrite=overwrite))

    if generated:
        manifest_path = charts_root / "chart_manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "run_dir": str(run_dir),
                    "generated_files": [str(path) for path in generated],
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        generated.append(manifest_path)
    return generated


def generate_pretrain_charts(
    run_dir: Path,
    report_path: Path,
    charts_root: Path,
    *,
    overwrite: bool,
) -> list[Path]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    metrics_path = _resolve_path(report.get("monitoring", {}).get("metrics_csv_path")) or _resolve_path(
        report.get("artifacts", {}).get("training_metrics_path")
    )
    if metrics_path is None or not metrics_path.exists():
        return []

    metrics = pd.read_csv(metrics_path)
    output_paths: list[Path] = []

    output_paths.append(
        _save_figure(
            charts_root / "pretrain_losses.png",
            lambda fig, ax: _plot_pretrain_losses(fig, ax, metrics, run_dir.name),
            overwrite=overwrite,
        )
    )
    output_paths.append(
        _save_figure(
            charts_root / "pretrain_attention_grad.png",
            lambda fig, ax: _plot_pretrain_attention_and_grad(fig, ax, metrics, run_dir.name),
            overwrite=overwrite,
        )
    )
    output_paths.append(
        _save_figure(
            charts_root / "pretrain_split_counts.png",
            lambda fig, ax: _plot_split_counts(fig, ax, report, run_dir.name),
            overwrite=overwrite,
        )
    )

    return [path for path in output_paths if path is not None]


def generate_downstream_charts(
    run_dir: Path,
    report_path: Path,
    charts_root: Path,
    *,
    overwrite: bool,
) -> list[Path]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    aggregate_path = run_dir / "aggregate_model_metrics.csv"
    metrics_path = aggregate_path if aggregate_path.exists() else run_dir / "model_metrics.csv"
    if not metrics_path.exists():
        return []

    metrics = pd.read_csv(metrics_path)
    metrics = metrics.copy()
    metrics["experiment_name"] = metrics.get("experiment_name", report.get("experiment_name", "run"))
    metrics["model_name"] = metrics["model_name"].astype(str)
    metrics["experiment_name"] = metrics["experiment_name"].astype(str)

    output_paths: list[Path] = []
    experiment_names = _ordered_unique(metrics["experiment_name"].tolist())

    for experiment_name in experiment_names:
        experiment_frame = metrics.loc[metrics["experiment_name"] == experiment_name].copy()
        if experiment_frame.empty:
            continue
        output_paths.append(
            _save_figure(
                charts_root / f"downstream_{experiment_name}_bars.png",
                lambda fig, ax, frame=experiment_frame, name=experiment_name: _plot_downstream_bars(
                    fig,
                    ax,
                    frame,
                    title=f"{run_dir.name} :: {name}",
                ),
                overwrite=overwrite,
            )
        )

    if len(experiment_names) > 1:
        output_paths.append(
            _save_figure(
                charts_root / "downstream_test_macro_f1_heatmap.png",
                lambda fig, ax: _plot_downstream_heatmap(fig, ax, metrics, metric="test_macro_f1", title=run_dir.name),
                overwrite=overwrite,
            )
        )
        output_paths.append(
            _save_figure(
                charts_root / "downstream_validation_macro_f1_heatmap.png",
                lambda fig, ax: _plot_downstream_heatmap(fig, ax, metrics, metric="validation_macro_f1", title=run_dir.name),
                overwrite=overwrite,
            )
        )
        output_paths.append(
            _save_figure(
                charts_root / "downstream_test_macro_f1_trend.png",
                lambda fig, ax: _plot_downstream_trend(fig, ax, metrics, metric="test_macro_f1", title=run_dir.name),
                overwrite=overwrite,
            )
        )

    return [path for path in output_paths if path is not None]


def _plot_pretrain_losses(fig: plt.Figure, ax: plt.Axes, metrics: pd.DataFrame, title: str) -> None:
    epochs = metrics["epoch"].to_numpy()
    ax.plot(epochs, metrics["train_loss"], label="train_loss", color="#1f77b4", linewidth=2.0)
    ax.plot(epochs, metrics["validation_loss"], label="validation_loss", color="#ff7f0e", linewidth=2.0)

    best_rows = metrics.loc[metrics["is_best_epoch"].astype(bool)]
    if not best_rows.empty:
        best_epoch = int(best_rows.iloc[-1]["epoch"])
        best_loss = float(best_rows.iloc[-1]["validation_loss"])
        ax.scatter([best_epoch], [best_loss], color="#2ca02c", s=40, zorder=5, label="best_epoch")

    ax.set_title(f"{title} :: pretrain loss curves")
    ax.set_xlabel("epoch")
    ax.set_ylabel("loss")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best")


def _plot_pretrain_attention_and_grad(fig: plt.Figure, ax: plt.Axes, metrics: pd.DataFrame, title: str) -> None:
    ax2 = ax.twinx()
    epochs = metrics["epoch"].to_numpy()
    ax.plot(epochs, metrics["attention_entropy"], label="attention_entropy", color="#9467bd", linewidth=2.0)
    ax2.plot(epochs, metrics["grad_norm"], label="grad_norm", color="#d62728", linewidth=2.0, alpha=0.85)
    ax.set_title(f"{title} :: attention entropy and gradient norm")
    ax.set_xlabel("epoch")
    ax.set_ylabel("attention_entropy")
    ax2.set_ylabel("grad_norm")
    ax.grid(True, alpha=0.25)
    lines = ax.get_lines() + ax2.get_lines()
    labels = [line.get_label() for line in lines]
    ax.legend(lines, labels, loc="best")


def _plot_split_counts(fig: plt.Figure, ax: plt.Axes, report: dict[str, object], title: str) -> None:
    split_counts = report.get("split_counts", {}) or {}
    split_policy = report.get("split_policy", {}) or {}
    row_counts = report.get("row_counts", {}) or {}
    excluded_count = split_policy.get("excluded_row_count", 0)
    labels = ["train", "validation", "test", "excluded_gap", "after_cleaning"]
    values = [
        int(split_counts.get("train", 0)),
        int(split_counts.get("validation", 0)),
        int(split_counts.get("test", 0)),
        int(excluded_count or 0),
        int(row_counts.get("after_cleaning", 0)),
    ]
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#7f7f7f", "#17becf"]
    ax.bar(labels, values, color=colors)
    ax.set_title(f"{title} :: split counts")
    ax.set_ylabel("rows")
    ax.grid(axis="y", alpha=0.25)
    for idx, value in enumerate(values):
        ax.text(idx, value, str(value), ha="center", va="bottom", fontsize=9)


def _plot_downstream_bars(fig: plt.Figure, ax: plt.Axes, frame: pd.DataFrame, title: str) -> None:
    frame = frame.sort_values(by=["validation_macro_f1", "test_macro_f1"], ascending=False).reset_index(drop=True)
    x = np.arange(len(frame))
    width = 0.38
    validation = frame["validation_macro_f1"].astype(float).to_numpy()
    test = frame["test_macro_f1"].astype(float).to_numpy()
    ax.bar(x - width / 2, validation, width, label="validation_macro_f1", color="#1f77b4")
    ax.bar(x + width / 2, test, width, label="test_macro_f1", color="#ff7f0e")
    ax.set_xticks(x)
    ax.set_xticklabels(frame["model_name"].tolist(), rotation=25, ha="right")
    ax.set_title(f"{title} :: model macro-F1")
    ax.set_ylabel("macro_f1")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(loc="best")


def _plot_downstream_heatmap(fig: plt.Figure, ax: plt.Axes, metrics: pd.DataFrame, *, metric: str, title: str) -> None:
    pivot = metrics.pivot_table(index="experiment_name", columns="model_name", values=metric, aggfunc="max")
    row_order = _ordered_unique(metrics["experiment_name"].tolist())
    col_order = _ordered_unique(metrics["model_name"].tolist())
    pivot = pivot.reindex(index=row_order, columns=col_order)

    matrix = pivot.to_numpy(dtype=float)
    masked = np.ma.masked_invalid(matrix)
    cmap = plt.cm.viridis.copy()
    cmap.set_bad(color="#e6e6e6")
    im = ax.imshow(masked, aspect="auto", cmap=cmap)
    ax.set_xticks(np.arange(len(col_order)))
    ax.set_xticklabels(col_order, rotation=25, ha="right")
    ax.set_yticks(np.arange(len(row_order)))
    ax.set_yticklabels(row_order)
    ax.set_title(f"{title} :: {metric}")
    ax.set_xlabel("model")
    ax.set_ylabel("experiment")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    for i, experiment_name in enumerate(row_order):
        for j, model_name in enumerate(col_order):
            value = pivot.iloc[i, j]
            if pd.notna(value):
                ax.text(j, i, f"{value:.2f}", ha="center", va="center", color="white", fontsize=8)


def _plot_downstream_trend(fig: plt.Figure, ax: plt.Axes, metrics: pd.DataFrame, *, metric: str, title: str) -> None:
    row_order = _ordered_unique(metrics["experiment_name"].tolist())
    col_order = _ordered_unique(metrics["model_name"].tolist())
    pivot = metrics.pivot_table(index="experiment_name", columns="model_name", values=metric, aggfunc="max")
    pivot = pivot.reindex(index=row_order, columns=col_order)

    x = np.arange(len(row_order))
    for idx, model_name in enumerate(col_order):
        y = pivot[model_name].to_numpy(dtype=float)
        ax.plot(x, y, marker="o", linewidth=2.0, label=model_name, color=plt.cm.tab20(idx % 20))
    ax.set_xticks(x)
    ax.set_xticklabels(row_order, rotation=0)
    ax.set_title(f"{title} :: {metric} trend")
    ax.set_xlabel("experiment")
    ax.set_ylabel(metric)
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", ncol=2, fontsize=8)


def _save_figure(path: Path, plotter, *, overwrite: bool) -> Path | None:
    if path.exists() and not overwrite:
        return path
    fig, ax = plt.subplots(figsize=(12, 6))
    try:
        plotter(fig, ax)
        fig.tight_layout()
        fig.savefig(path, dpi=180, bbox_inches="tight")
    finally:
        plt.close(fig)
    return path


def _resolve_path(raw_value: object) -> Path | None:
    if raw_value is None:
        return None
    return Path(str(raw_value)).resolve()


def _ordered_unique(values: Iterable[str]) -> list[str]:
    seen: dict[str, None] = {}
    for value in values:
        text = str(value)
        if text not in seen:
            seen[text] = None
    return sorted(seen, key=_natural_key)


def _natural_key(value: str) -> tuple[object, ...]:
    parts = re.split(r"(\d+)", value)
    key: list[object] = []
    for part in parts:
        if not part:
            continue
        key.append(int(part) if part.isdigit() else part.lower())
    return tuple(key)


if __name__ == "__main__":
    main()
