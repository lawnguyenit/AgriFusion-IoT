from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from Backend.Benchmark.context_classifier.src.config.settings import CONTEXT_CLASSIFIER_ROOT
from Backend.Benchmark.pretrain_supervised.pretrain.src.utils.artifacts import create_run_directory, write_json


@dataclass
class TrainingRunSpec:
    label_scheme: str
    run_dir: Path


def _load_training_report(run_dir: Path) -> dict[str, object]:
    report_path = run_dir / "training_report.json"
    if not report_path.exists():
        raise FileNotFoundError(f"training_report.json not found: {report_path}")
    return json.loads(report_path.read_text(encoding="utf-8"))


def _load_aggregate_metrics(run_dir: Path) -> pd.DataFrame:
    metrics_path = run_dir / "aggregate_model_metrics.csv"
    if not metrics_path.exists():
        raise FileNotFoundError(f"aggregate_model_metrics.csv not found: {metrics_path}")
    return pd.read_csv(metrics_path)


def _load_context_label_summary(build_run_dir: Path) -> dict[str, object]:
    summary_path = build_run_dir / "context_label_summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"context_label_summary.json not found: {summary_path}")
    return json.loads(summary_path.read_text(encoding="utf-8"))


def _ensure_report_root() -> Path:
    return (CONTEXT_CLASSIFIER_ROOT / "reports").resolve()


def _save_figure(fig: plt.Figure, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def _bar_metric_by_scheme(
    frame: pd.DataFrame,
    *,
    metric_column: str,
    title: str,
    output_path: Path,
) -> None:
    if frame.empty:
        return
    plot_df = frame.copy()
    plot_df["scheme_label"] = plot_df["label_scheme"].map(
        {
            "five_class_v1": "5 nhan",
            "option2_4class": "4 nhan",
        }
    ).fillna(plot_df["label_scheme"])
    plot_df["series_label"] = plot_df["scheme_label"] + " | " + plot_df["experiment_name"] + " | " + plot_df["model_name"]
    plot_df = plot_df.sort_values(metric_column, ascending=False)

    fig, ax = plt.subplots(figsize=(14, 7))
    ax.bar(plot_df["series_label"], plot_df[metric_column], color="#2d6a4f")
    ax.set_title(title)
    ax.set_ylabel(metric_column)
    ax.set_ylim(0.0, 1.05)
    ax.tick_params(axis="x", labelrotation=45)
    ax.grid(axis="y", alpha=0.25)
    _save_figure(fig, output_path)


def _grouped_metric_plot(
    frame: pd.DataFrame,
    *,
    metric_column: str,
    title: str,
    output_path: Path,
) -> None:
    plot_df = frame.copy()
    plot_df = plot_df[plot_df["experiment_name"].isin(["v0", "v1", "v2", "v3", "sequence"])]
    if plot_df.empty:
        return
    plot_df["scheme_label"] = plot_df["label_scheme"].map(
        {
            "five_class_v1": "5 nhan",
            "option2_4class": "4 nhan",
        }
    ).fillna(plot_df["label_scheme"])
    plot_df["category"] = plot_df["experiment_name"] + " | " + plot_df["model_name"]
    pivot = plot_df.pivot_table(
        index="category",
        columns="scheme_label",
        values=metric_column,
        aggfunc="max",
    ).fillna(0.0)

    fig, ax = plt.subplots(figsize=(14, 7))
    pivot.plot(kind="bar", ax=ax, color=["#4d908e", "#f4a261"])
    ax.set_title(title)
    ax.set_ylabel(metric_column)
    ax.set_ylim(0.0, 1.05)
    ax.tick_params(axis="x", labelrotation=35)
    ax.grid(axis="y", alpha=0.25)
    ax.legend(title="Scheme")
    _save_figure(fig, output_path)


def _feature_ladder_plot(
    frame: pd.DataFrame,
    *,
    model_name: str,
    metric_column: str,
    output_path: Path,
) -> None:
    plot_df = frame[frame["model_name"] == model_name].copy()
    plot_df = plot_df[plot_df["experiment_name"].isin(["v0", "v1", "v2", "v3"])]
    if plot_df.empty:
        return
    order = ["v0", "v1", "v2", "v3"]
    fig, ax = plt.subplots(figsize=(10, 6))
    for label_scheme, group in plot_df.groupby("label_scheme"):
        group = group.set_index("experiment_name").reindex(order).reset_index()
        ax.plot(
            group["experiment_name"],
            group[metric_column],
            marker="o",
            linewidth=2.5,
            label=label_scheme,
        )
    ax.set_title(f"{model_name} - {metric_column} theo feature ladder")
    ax.set_ylabel(metric_column)
    ax.set_ylim(0.0, 1.05)
    ax.grid(alpha=0.25)
    ax.legend(title="Label scheme")
    _save_figure(fig, output_path)


def _label_mapping_plot(output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.axis("off")

    ax.text(
        0.18,
        0.68,
        "rain_humid_context",
        ha="center",
        va="center",
        fontsize=14,
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#8ecae6", edgecolor="#264653", alpha=0.95),
    )
    ax.text(
        0.18,
        0.32,
        "fertigation_spike",
        ha="center",
        va="center",
        fontsize=14,
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#90be6d", edgecolor="#264653", alpha=0.95),
    )
    ax.text(
        0.72,
        0.50,
        "moisture_or_intervention_context",
        ha="center",
        va="center",
        fontsize=14,
        bbox=dict(boxstyle="round,pad=0.65", facecolor="#f4a261", edgecolor="#7f5539", alpha=0.95),
    )
    arrow_style = dict(arrowstyle="->", linewidth=2.5, color="#2d6a4f")
    ax.annotate("", xy=(0.56, 0.56), xytext=(0.28, 0.66), arrowprops=arrow_style)
    ax.annotate("", xy=(0.56, 0.44), xytext=(0.28, 0.34), arrowprops=arrow_style)
    ax.text(
        0.5,
        0.88,
        "Option 2: gop 2 nhan mong thanh 1 nhan lon hon",
        ha="center",
        va="center",
        fontsize=16,
        fontweight="bold",
    )
    ax.text(
        0.5,
        0.14,
        "Muc tieu: tang do phu abnormal trong validation/test va on dinh macro-F1",
        ha="center",
        va="center",
        fontsize=12,
    )
    _save_figure(fig, output_path)


def _distribution_plot(
    distribution_rows: list[dict[str, object]],
    *,
    output_path: Path,
) -> None:
    dist_df = pd.DataFrame(distribution_rows)
    if dist_df.empty:
        return
    dist_df = (
        dist_df.groupby(["context_label", "label_scheme"], as_index=False)["row_count"]
        .max()
        .sort_values(["context_label", "label_scheme"])
    )
    fig, ax = plt.subplots(figsize=(12, 7))
    pivot = dist_df.pivot(index="context_label", columns="label_scheme", values="row_count").fillna(0)
    pivot.plot(kind="bar", ax=ax, color=["#577590", "#f8961e"])
    ax.set_title("Phan bo nhan sau khi merge real + synthetic")
    ax.set_ylabel("So dong")
    ax.set_xlabel("Nhan")
    ax.tick_params(axis="x", labelrotation=20)
    ax.grid(axis="y", alpha=0.25)
    _save_figure(fig, output_path)


def _training_curve_plot(
    history_rows: list[dict[str, object]],
    *,
    title: str,
    output_path: Path,
) -> None:
    history_df = pd.DataFrame(history_rows)
    if history_df.empty:
        return
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    if history_df["train_loss"].notna().any():
        axes[0].plot(history_df["epoch"], history_df["train_loss"], marker="o", label="train_loss")
    if history_df["validation_loss"].notna().any():
        axes[0].plot(history_df["epoch"], history_df["validation_loss"], marker="o", label="validation_loss")
    axes[0].set_title(f"{title} - Loss curve")
    axes[0].set_xlabel("Epoch")
    axes[0].set_ylabel("Loss")
    axes[0].grid(alpha=0.25)
    handles, labels = axes[0].get_legend_handles_labels()
    if handles:
        axes[0].legend()

    axes[1].plot(history_df["epoch"], history_df["validation_macro_f1"], marker="o", label="validation_macro_f1")
    axes[1].plot(history_df["epoch"], history_df["test_macro_f1"], marker="o", label="test_macro_f1")
    axes[1].set_title(f"{title} - Macro-F1 curve")
    axes[1].set_xlabel("Epoch")
    axes[1].set_ylabel("Macro-F1")
    axes[1].set_ylim(0.0, 1.05)
    axes[1].grid(alpha=0.25)
    axes[1].legend()
    _save_figure(fig, output_path)


def _markdown_table_from_frame(frame: pd.DataFrame) -> str:
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


def _extract_histories(training_report: dict[str, object], label_scheme: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for experiment in training_report.get("experiment_reports", []):
        experiment_name = str(experiment.get("experiment_name"))
        for model in experiment.get("models", []):
            history = model.get("history")
            if not isinstance(history, list):
                continue
            model_name = str(model.get("model_name"))
            for item in history:
                row = dict(item)
                row["label_scheme"] = label_scheme
                row["experiment_name"] = experiment_name
                row["model_name"] = model_name
                rows.append(row)
    return rows


def _write_markdown_summary(
    *,
    combined_metrics: pd.DataFrame,
    distribution_rows: list[dict[str, object]],
    output_path: Path,
) -> None:
    lines: list[str] = []
    lines.append("# Context Classifier Report")
    lines.append("")
    lines.append("## Tong quan")
    lines.append("")
    for label_scheme in ["five_class_v1", "option2_4class"]:
        scheme_df = combined_metrics[combined_metrics["label_scheme"] == label_scheme]
        if scheme_df.empty:
            continue
        best = scheme_df.sort_values("test_macro_f1", ascending=False).iloc[0]
        lines.append(f"- `{label_scheme}`: tot nhat la `{best['experiment_name']} / {best['model_name']}` voi `test_macro_f1 = {best['test_macro_f1']:.4f}`")
    lines.append("")
    lines.append("## Bang metric")
    lines.append("")
    display_columns = [
        "label_scheme",
        "experiment_name",
        "model_name",
        "validation_accuracy",
        "validation_balanced_accuracy",
        "validation_macro_f1",
        "test_accuracy",
        "test_balanced_accuracy",
        "test_macro_f1",
    ]
    lines.append(_markdown_table_from_frame(combined_metrics[display_columns]))
    lines.append("")
    lines.append("## Phan bo nhan")
    lines.append("")
    dist_df = pd.DataFrame(distribution_rows)
    if not dist_df.empty:
        dist_df = (
            dist_df.groupby(["label_scheme", "context_label"], as_index=False)["row_count"]
            .max()
            .sort_values(["label_scheme", "context_label"])
        )
        lines.append(_markdown_table_from_frame(dist_df))
    output_path.write_text("\n".join(lines), encoding="utf-8")


def run_report_pipeline(
    *,
    run_specs: list[TrainingRunSpec],
) -> dict[str, object]:
    report_root = _ensure_report_root()
    run_id, output_dir = create_run_directory(report_root, prefix="context_report")

    combined_frames: list[pd.DataFrame] = []
    history_rows: list[dict[str, object]] = []
    distribution_rows: list[dict[str, object]] = []
    source_runs: list[dict[str, object]] = []

    for spec in run_specs:
        training_report = _load_training_report(spec.run_dir)
        metrics_df = _load_aggregate_metrics(spec.run_dir)
        metrics_df["label_scheme"] = spec.label_scheme
        combined_frames.append(metrics_df)
        history_rows.extend(_extract_histories(training_report, spec.label_scheme))

        build_run_dir = Path(str(training_report["build_run_dir"]))
        label_summary = _load_context_label_summary(build_run_dir)
        for context_label, row_count in label_summary.get("context_label_counts", {}).items():
            distribution_rows.append(
                {
                    "label_scheme": spec.label_scheme,
                    "context_label": str(context_label),
                    "row_count": int(row_count),
                }
            )

        source_runs.append(
            {
                "label_scheme": spec.label_scheme,
                "training_run_dir": str(spec.run_dir),
                "build_run_dir": str(build_run_dir),
            }
        )

    combined_metrics = pd.concat(combined_frames, ignore_index=True)
    combined_metrics.to_csv(output_dir / "combined_model_metrics.csv", index=False)

    summary_rows = (
        combined_metrics.groupby(["label_scheme", "model_name", "experiment_name"], as_index=False)[
            [
                "validation_accuracy",
                "validation_balanced_accuracy",
                "validation_macro_f1",
                "test_accuracy",
                "test_balanced_accuracy",
                "test_macro_f1",
            ]
        ]
        .max()
        .sort_values(["label_scheme", "test_macro_f1"], ascending=[True, False])
    )
    summary_rows.to_csv(output_dir / "summary_model_metrics.csv", index=False)

    history_df = pd.DataFrame(history_rows)
    if not history_df.empty:
        history_df.to_csv(output_dir / "epoch_history_rows.csv", index=False)

    _bar_metric_by_scheme(
        combined_metrics,
        metric_column="test_macro_f1",
        title="So sanh test macro-F1 giua cac nhanh benchmark",
        output_path=output_dir / "chart_test_macro_f1.png",
    )
    _bar_metric_by_scheme(
        combined_metrics,
        metric_column="test_accuracy",
        title="So sanh test accuracy giua cac nhanh benchmark",
        output_path=output_dir / "chart_test_accuracy.png",
    )
    _grouped_metric_plot(
        combined_metrics,
        metric_column="test_macro_f1",
        title="Test macro-F1 theo model va feature set",
        output_path=output_dir / "chart_test_macro_f1_grouped.png",
    )
    _grouped_metric_plot(
        combined_metrics,
        metric_column="test_accuracy",
        title="Test accuracy theo model va feature set",
        output_path=output_dir / "chart_test_accuracy_grouped.png",
    )
    _grouped_metric_plot(
        combined_metrics,
        metric_column="validation_macro_f1",
        title="Validation macro-F1 theo model va feature set",
        output_path=output_dir / "chart_validation_macro_f1_grouped.png",
    )
    _grouped_metric_plot(
        combined_metrics,
        metric_column="test_balanced_accuracy",
        title="Test balanced accuracy theo model va feature set",
        output_path=output_dir / "chart_test_balanced_accuracy_grouped.png",
    )
    _feature_ladder_plot(
        combined_metrics,
        model_name="xgboost",
        metric_column="test_macro_f1",
        output_path=output_dir / "chart_xgboost_feature_ladder.png",
    )
    _feature_ladder_plot(
        combined_metrics,
        model_name="tabnet_classifier",
        metric_column="test_macro_f1",
        output_path=output_dir / "chart_tabnet_feature_ladder.png",
    )
    _distribution_plot(
        distribution_rows,
        output_path=output_dir / "chart_label_distribution.png",
    )
    _label_mapping_plot(output_dir / "chart_option2_label_mapping.png")

    if not history_df.empty:
        for (label_scheme, experiment_name, model_name), history_group in history_df.groupby(
            ["label_scheme", "experiment_name", "model_name"]
        ):
            if history_group.empty:
                continue
            title = f"{label_scheme} - {experiment_name} - {model_name}"
            output_name = f"chart_{label_scheme}_{experiment_name}_{model_name}_curves.png"
            _training_curve_plot(
                history_group.sort_values("epoch"),
                title=title,
                output_path=output_dir / output_name,
            )

    _write_markdown_summary(
        combined_metrics=combined_metrics.sort_values(["label_scheme", "test_macro_f1"], ascending=[True, False]),
        distribution_rows=distribution_rows,
        output_path=output_dir / "report_summary.md",
    )

    write_json(
        output_dir / "report_manifest.json",
        {
            "run_id": run_id,
            "output_dir": str(output_dir),
            "source_runs": source_runs,
            "generated_files": sorted([path.name for path in output_dir.iterdir() if path.is_file()]),
        },
    )

    return {
        "run_id": run_id,
        "output_dir": str(output_dir),
        "combined_metrics_path": str(output_dir / "combined_model_metrics.csv"),
        "summary_metrics_path": str(output_dir / "summary_model_metrics.csv"),
        "report_summary_path": str(output_dir / "report_summary.md"),
    }
