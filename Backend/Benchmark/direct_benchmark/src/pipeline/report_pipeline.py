from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from Backend.Benchmark.direct_benchmark.src.config.settings import default_report_output_root
from Backend.Benchmark.shared.artifacts import create_run_directory, write_json


def run_report_pipeline(*, training_run_dir: Path, label_mode: str) -> dict[str, object]:
    training_run_dir = training_run_dir.resolve()
    report_root = default_report_output_root(label_mode)
    run_id, output_dir = create_run_directory(report_root, prefix="direct_report")
    metrics_path = training_run_dir / "aggregate_model_metrics.csv"
    report_path = training_run_dir / "training_report.json"
    if not metrics_path.exists():
        raise FileNotFoundError(f"aggregate_model_metrics.csv not found: {metrics_path}")
    if not report_path.exists():
        raise FileNotFoundError(f"training_report.json not found: {report_path}")

    metrics = pd.read_csv(metrics_path).sort_values(
        ["validation_macro_f1", "test_macro_f1"],
        ascending=False,
    )
    training_report = json.loads(report_path.read_text(encoding="utf-8"))
    metrics.to_csv(output_dir / "combined_model_metrics.csv", index=False)

    best_by_experiment = (
        metrics.groupby("experiment_name", as_index=False)[
            ["validation_macro_f1", "test_macro_f1", "validation_accuracy", "test_accuracy"]
        ]
        .max()
        .sort_values("test_macro_f1", ascending=False)
    )
    best_by_experiment.to_csv(output_dir / "summary_model_metrics.csv", index=False)

    _bar_plot(
        metrics,
        metric_column="test_macro_f1",
        title=f"Direct benchmark {label_mode} - test macro F1",
        output_path=output_dir / "chart_test_macro_f1.png",
    )
    _bar_plot(
        metrics,
        metric_column="test_accuracy",
        title=f"Direct benchmark {label_mode} - test accuracy",
        output_path=output_dir / "chart_test_accuracy.png",
    )

    summary_md = output_dir / "report_summary.md"
    summary_md.write_text(_build_markdown_summary(metrics, training_report, label_mode), encoding="utf-8")
    write_json(
        output_dir / "report_manifest.json",
        {
            "run_id": run_id,
            "label_mode": label_mode,
            "training_run_dir": str(training_run_dir),
            "output_dir": str(output_dir),
            "generated_files": sorted([path.name for path in output_dir.iterdir() if path.is_file()]),
        },
    )
    return {
        "run_id": run_id,
        "label_mode": label_mode,
        "output_dir": str(output_dir),
        "combined_metrics_path": str(output_dir / "combined_model_metrics.csv"),
        "summary_metrics_path": str(output_dir / "summary_model_metrics.csv"),
        "report_summary_path": str(summary_md),
    }


def _bar_plot(frame: pd.DataFrame, *, metric_column: str, title: str, output_path: Path) -> None:
    plot_df = frame.copy()
    plot_df["series_label"] = plot_df["experiment_name"] + " | " + plot_df["model_name"]
    plot_df = plot_df.sort_values(metric_column, ascending=False)
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.bar(plot_df["series_label"], plot_df[metric_column], color="#2d6a4f")
    ax.set_title(title)
    ax.set_ylabel(metric_column)
    ax.set_ylim(0.0, 1.05)
    ax.tick_params(axis="x", labelrotation=45)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def _build_markdown_summary(metrics: pd.DataFrame, training_report: dict[str, object], label_mode: str) -> str:
    best = metrics.iloc[0]
    lines = [
        f"# Direct Benchmark Report ({label_mode})",
        "",
        "## Tong quan",
        "",
        f"- training run: `{training_report.get('output_dir', '')}`",
        f"- build run: `{training_report.get('build_run_dir', '')}`",
        f"- best model: `{best['experiment_name']} / {best['model_name']}`",
        f"- best validation macro_f1: `{float(best['validation_macro_f1']):.4f}`",
        f"- best test macro_f1: `{float(best['test_macro_f1']):.4f}`",
        "",
        "## Metric table",
        "",
        _markdown_table(metrics),
        "",
    ]
    return "\n".join(lines) + "\n"


def _markdown_table(frame: pd.DataFrame) -> str:
    headers = [str(column) for column in frame.columns]
    rows = [[str(value) for value in row] for row in frame.to_numpy().tolist()]
    table_rows = [headers] + rows
    widths = [max(len(str(row[index])) for row in table_rows) for index in range(len(headers))]

    def _format_row(values: list[str]) -> str:
        return "| " + " | ".join(value.ljust(widths[index]) for index, value in enumerate(values)) + " |"

    separator = "| " + " | ".join("-" * widths[index] for index in range(len(headers))) + " |"
    lines = [_format_row(headers), separator]
    lines.extend(_format_row(row) for row in rows)
    return "\n".join(lines)
