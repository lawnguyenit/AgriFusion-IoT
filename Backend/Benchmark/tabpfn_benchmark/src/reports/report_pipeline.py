from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import re

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from Backend.Benchmark.common.paths import TABPFN_BENCHMARK_ROOT
from Backend.Benchmark.tabpfn_benchmark.src.scientific_artifacts import TOP1_CALIBRATION_LABEL
from Backend.Benchmark.pretrain_supervised.pretrain.src.utils.artifacts import create_run_directory, write_json


@dataclass
class TrainingRunSpec:
    run_label: str
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


def _ensure_report_root() -> Path:
    return (TABPFN_BENCHMARK_ROOT / "reports").resolve()


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower())
    return slug.strip("_") or "run"


def _save_figure(fig: plt.Figure, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def _extract_histories(training_report: dict[str, object], run_label: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for experiment in training_report.get("experiment_reports", []):
        experiment_name = str(experiment.get("experiment_name"))
        for model in experiment.get("model_results", []):
            history = model.get("metrics", {}).get("history")
            if not isinstance(history, list):
                continue
            model_name = str(model.get("model_name"))
            for item in history:
                row = dict(item)
                row["run_label"] = run_label
                row["experiment_name"] = experiment_name
                row["model_name"] = model_name
                rows.append(row)
    return rows


def _extract_scientific_specs(training_report: dict[str, object], run_label: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for experiment in training_report.get("experiment_reports", []):
        experiment_name = str(experiment.get("experiment_name"))
        for model in experiment.get("model_results", []):
            scientific_artifacts = model.get("scientific_artifacts")
            if not isinstance(scientific_artifacts, dict):
                continue
            manifest_path = scientific_artifacts.get("manifest_path")
            if not manifest_path:
                continue
            rows.append(
                {
                    "run_label": run_label,
                    "experiment_name": experiment_name,
                    "model_name": str(model.get("model_name")),
                    "manifest_path": str(manifest_path),
                }
            )
    return rows


def _metric_bar_plot(
    frame: pd.DataFrame,
    *,
    metric_column: str,
    title: str,
    output_path: Path,
) -> None:
    if frame.empty:
        return
    plot_df = frame.copy()
    plot_df["series_label"] = plot_df["run_label"] + " | " + plot_df["experiment_name"] + " | " + plot_df["model_name"]
    plot_df = plot_df.sort_values(metric_column, ascending=False)
    fig, ax = plt.subplots(figsize=(15, 7))
    ax.bar(plot_df["series_label"], plot_df[metric_column], color="#1b7f3b")
    ax.set_title(title)
    ax.set_ylabel(metric_column)
    ax.set_ylim(0.0, 1.05)
    ax.tick_params(axis="x", labelrotation=45)
    ax.grid(axis="y", alpha=0.25)
    _save_figure(fig, output_path)


def _feature_ladder_plot(
    frame: pd.DataFrame,
    *,
    run_label: str,
    metric_column: str,
    output_path: Path,
) -> None:
    plot_df = frame[frame["run_label"] == run_label].copy()
    plot_df = plot_df[plot_df["experiment_name"].isin(["v0", "v1", "v2", "v3", "v4", "v5"])]
    if plot_df.empty:
        return
    order = ["v0", "v1", "v2", "v3", "v4", "v5"]
    fig, ax = plt.subplots(figsize=(11, 6))
    for model_name, group in plot_df.groupby("model_name"):
        group = group.set_index("experiment_name").reindex(order).reset_index()
        ax.plot(
            group["experiment_name"],
            group[metric_column],
            marker="o",
            linewidth=2.4,
            label=model_name,
        )
    ax.set_title(f"{run_label} - {metric_column} theo feature ladder")
    ax.set_ylabel(metric_column)
    ax.set_ylim(0.0, 1.05)
    ax.grid(alpha=0.25)
    ax.legend(title="Model")
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

    if "train_loss" in history_df and history_df["train_loss"].notna().any():
        axes[0].plot(history_df["epoch"], history_df["train_loss"], marker="o", label="train_loss")
    if "validation_loss" in history_df and history_df["validation_loss"].notna().any():
        axes[0].plot(history_df["epoch"], history_df["validation_loss"], marker="o", label="validation_loss")
    axes[0].set_title(f"{title} - Loss curve")
    axes[0].set_xlabel("Epoch")
    axes[0].set_ylabel("Loss")
    axes[0].grid(alpha=0.25)
    if axes[0].get_legend_handles_labels()[0]:
        axes[0].legend()

    if "validation_macro_f1" in history_df:
        axes[1].plot(history_df["epoch"], history_df["validation_macro_f1"], marker="o", label="validation_macro_f1")
    if "test_macro_f1" in history_df:
        axes[1].plot(history_df["epoch"], history_df["test_macro_f1"], marker="o", label="test_macro_f1")
    axes[1].set_title(f"{title} - Macro-F1 curve")
    axes[1].set_xlabel("Epoch")
    axes[1].set_ylabel("Macro-F1")
    axes[1].set_ylim(0.0, 1.05)
    axes[1].grid(alpha=0.25)
    if axes[1].get_legend_handles_labels()[0]:
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


def _write_markdown_summary(
    *,
    combined_metrics: pd.DataFrame,
    scientific_metrics: pd.DataFrame | None,
    output_path: Path,
) -> None:
    lines: list[str] = []
    lines.append("# TabPFN Benchmark Report")
    lines.append("")
    lines.append("## Tong quan")
    lines.append("")
    for run_label in combined_metrics["run_label"].drop_duplicates().tolist():
        run_df = combined_metrics[combined_metrics["run_label"] == run_label]
        if run_df.empty:
            continue
        best = run_df.sort_values("test_macro_f1", ascending=False).iloc[0]
        lines.append(
            f"- `{run_label}`: tot nhat la `{best['experiment_name']} / {best['model_name']}` voi `test_macro_f1 = {best['test_macro_f1']:.4f}`"
        )
    lines.append("")
    lines.append("## Bang metric")
    lines.append("")
    display_columns = [
        "run_label",
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
    if scientific_metrics is not None and not scientific_metrics.empty:
        lines.append("")
        lines.append("## Chi so khoa hoc bo sung")
        lines.append("")
        lines.append("Cac chi so duoi day duoc rut ra tu scientific artifact cua benchmark TabPFN.")
        lines.append("")
        display_scientific_columns = [
            "run_label",
            "experiment_name",
            "model_name",
            "split",
            "macro_f1",
            "ovr_macro_roc_auc",
            "ovr_macro_average_precision",
            "log_loss",
            "multiclass_brier",
            "top1_ece_15bins",
        ]
        existing_columns = [column for column in display_scientific_columns if column in scientific_metrics.columns]
        if existing_columns:
            lines.append(_markdown_table_from_frame(scientific_metrics[existing_columns]))
    output_path.write_text("\n".join(lines), encoding="utf-8")


def run_report_pipeline(*, run_specs: list[TrainingRunSpec]) -> dict[str, object]:
    report_root = _ensure_report_root()
    run_id, output_dir = create_run_directory(report_root, prefix="tabpfn_report")

    combined_frames: list[pd.DataFrame] = []
    history_rows: list[dict[str, object]] = []
    scientific_specs: list[dict[str, str]] = []
    source_runs: list[dict[str, object]] = []

    for spec in run_specs:
        training_report = _load_training_report(spec.run_dir)
        metrics_df = _load_aggregate_metrics(spec.run_dir)
        metrics_df["run_label"] = spec.run_label
        combined_frames.append(metrics_df)
        history_rows.extend(_extract_histories(training_report, spec.run_label))
        scientific_specs.extend(_extract_scientific_specs(training_report, spec.run_label))
        source_runs.append(
            {
                "run_label": spec.run_label,
                "run_dir": str(spec.run_dir),
                "benchmark_version": training_report.get("benchmark_version"),
            }
        )

    combined_metrics = pd.concat(combined_frames, ignore_index=True)
    combined_metrics_path = output_dir / "combined_model_metrics.csv"
    combined_metrics.to_csv(combined_metrics_path, index=False)

    summary_columns = [
        "run_label",
        "experiment_name",
        "model_name",
        "validation_accuracy",
        "validation_balanced_accuracy",
        "validation_macro_f1",
        "test_accuracy",
        "test_balanced_accuracy",
        "test_macro_f1",
    ]
    summary_metrics = combined_metrics[summary_columns].sort_values(
        by=["run_label", "test_macro_f1", "validation_macro_f1"],
        ascending=[True, False, False],
    )
    summary_metrics_path = output_dir / "summary_model_metrics.csv"
    summary_metrics.to_csv(summary_metrics_path, index=False)

    scientific_scalar_metrics: pd.DataFrame | None = None
    if scientific_specs:
        scientific_frames: list[pd.DataFrame] = []
        for scientific_spec in scientific_specs:
            manifest = _load_scientific_manifest(Path(scientific_spec["manifest_path"]))
            scientific_frame = _load_scientific_scalar_metrics(
                manifest=manifest,
                run_label=scientific_spec["run_label"],
                experiment_name=scientific_spec["experiment_name"],
                model_name=scientific_spec["model_name"],
            )
            if not scientific_frame.empty:
                scientific_frames.append(scientific_frame)

            chart_stem = (
                f"{_slugify(scientific_spec['run_label'])}_"
                f"{_slugify(scientific_spec['experiment_name'])}_"
                f"{_slugify(scientific_spec['model_name'])}"
            )
            _training_diagnostics_plot(
                manifest=manifest,
                title=f"{scientific_spec['run_label']} - {scientific_spec['experiment_name']} - {scientific_spec['model_name']}",
                output_path=output_dir / f"chart_{chart_stem}_diagnostics.png",
            )
            _confusion_plot(
                manifest=manifest,
                split_name="test",
                title=f"{scientific_spec['run_label']} - {scientific_spec['experiment_name']} - test confusion",
                output_path=output_dir / f"chart_{chart_stem}_test_confusion.png",
            )
            _probability_curve_plot(
                manifest=manifest,
                curve_kind="pr",
                split_name="test",
                title=f"{scientific_spec['run_label']} - {scientific_spec['experiment_name']} - test PR",
                output_path=output_dir / f"chart_{chart_stem}_test_pr_curve.png",
            )
            _probability_curve_plot(
                manifest=manifest,
                curve_kind="roc",
                split_name="test",
                title=f"{scientific_spec['run_label']} - {scientific_spec['experiment_name']} - test ROC",
                output_path=output_dir / f"chart_{chart_stem}_test_roc_curve.png",
            )
            _calibration_plot(
                manifest=manifest,
                split_name="test",
                title=f"{scientific_spec['run_label']} - {scientific_spec['experiment_name']} - test calibration",
                output_path=output_dir / f"chart_{chart_stem}_test_calibration.png",
            )

        if scientific_frames:
            scientific_scalar_metrics = pd.concat(scientific_frames, ignore_index=True)
            scientific_scalar_metrics_path = output_dir / "scientific_scalar_metrics.csv"
            scientific_scalar_metrics.to_csv(scientific_scalar_metrics_path, index=False)
        else:
            scientific_scalar_metrics_path = None
    else:
        scientific_scalar_metrics_path = None

    _metric_bar_plot(
        summary_metrics,
        metric_column="test_macro_f1",
        title="So sanh test_macro_f1 giua cac arm TabPFN benchmark",
        output_path=output_dir / "chart_test_macro_f1.png",
    )
    _metric_bar_plot(
        summary_metrics,
        metric_column="test_accuracy",
        title="So sanh test_accuracy giua cac arm TabPFN benchmark",
        output_path=output_dir / "chart_test_accuracy.png",
    )

    for run_label in summary_metrics["run_label"].drop_duplicates().tolist():
        run_slug = _slugify(run_label)
        _feature_ladder_plot(
            summary_metrics,
            run_label=run_label,
            metric_column="test_macro_f1",
            output_path=output_dir / f"chart_{run_slug}_feature_ladder_macro_f1.png",
        )
        _feature_ladder_plot(
            summary_metrics,
            run_label=run_label,
            metric_column="test_accuracy",
            output_path=output_dir / f"chart_{run_slug}_feature_ladder_accuracy.png",
        )

    for (run_label, experiment_name, model_name), group in pd.DataFrame(history_rows).groupby(
        ["run_label", "experiment_name", "model_name"]
    ):
        history_records = group.to_dict(orient="records")
        chart_name = f"chart_{_slugify(run_label)}_{_slugify(experiment_name)}_{_slugify(model_name)}_curves.png"
        _training_curve_plot(
            history_records,
            title=f"{run_label} - {experiment_name} - {model_name}",
            output_path=output_dir / chart_name,
        )

    report_summary_path = output_dir / "report_summary.md"
    _write_markdown_summary(
        combined_metrics=summary_metrics,
        scientific_metrics=scientific_scalar_metrics,
        output_path=report_summary_path,
    )

    manifest = {
        "report_kind": "tabpfn_benchmark_report",
        "run_id": run_id,
        "output_dir": str(output_dir),
        "source_runs": source_runs,
        "combined_metrics_path": str(combined_metrics_path),
        "summary_metrics_path": str(summary_metrics_path),
        "scientific_scalar_metrics_path": None if scientific_scalar_metrics_path is None else str(scientific_scalar_metrics_path),
        "report_summary_path": str(report_summary_path),
    }
    write_json(output_dir / "report_manifest.json", manifest)
    return manifest


def _load_scientific_manifest(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"Scientific manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _load_scientific_scalar_metrics(
    *,
    manifest: dict[str, object],
    run_label: str,
    experiment_name: str,
    model_name: str,
) -> pd.DataFrame:
    scalar_metrics_path = Path(str(manifest["scalar_metrics_path"]))
    if not scalar_metrics_path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(scalar_metrics_path)
    frame["run_label"] = run_label
    frame["experiment_name"] = experiment_name
    frame["model_name"] = model_name
    return frame


def _training_diagnostics_plot(*, manifest: dict[str, object], title: str, output_path: Path) -> None:
    history_path = Path(str(manifest["history_csv_path"]))
    if not history_path.exists():
        return
    history = pd.read_csv(history_path)
    if history.empty:
        return

    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    epochs = history["epoch"].astype(float).to_numpy()

    axes[0, 0].plot(epochs, history["train_loss"], label="train_loss", color="#1f77b4", linewidth=2.0)
    axes[0, 0].plot(epochs, history["validation_loss"], label="validation_loss", color="#ff7f0e", linewidth=2.0)
    best_rows = history.loc[history.get("is_best_epoch", False).astype(bool)]
    if not best_rows.empty:
        best_epoch = float(best_rows.iloc[-1]["epoch"])
        best_loss = float(best_rows.iloc[-1]["validation_loss"])
        axes[0, 0].scatter([best_epoch], [best_loss], color="#2ca02c", s=40, zorder=5, label="best_epoch")
    axes[0, 0].set_title("Loss curves")
    axes[0, 0].set_xlabel("Epoch")
    axes[0, 0].set_ylabel("Loss")
    axes[0, 0].grid(alpha=0.25)
    axes[0, 0].legend()

    axes[0, 1].plot(epochs, history["validation_macro_f1"], label="validation_macro_f1", color="#1f77b4", linewidth=2.0)
    axes[0, 1].plot(epochs, history["test_macro_f1"], label="test_macro_f1", color="#ff7f0e", linewidth=2.0)
    axes[0, 1].set_title("Macro-F1 curves")
    axes[0, 1].set_xlabel("Epoch")
    axes[0, 1].set_ylabel("Macro-F1")
    axes[0, 1].set_ylim(0.0, 1.05)
    axes[0, 1].grid(alpha=0.25)
    axes[0, 1].legend()

    axes[1, 0].plot(epochs, history["attention_entropy"], label="attention_entropy", color="#9467bd", linewidth=2.0)
    twin_axis = axes[1, 0].twinx()
    twin_axis.plot(epochs, history["grad_norm"], label="grad_norm", color="#d62728", linewidth=2.0, alpha=0.85)
    axes[1, 0].set_title("Attention entropy vs grad norm")
    axes[1, 0].set_xlabel("Epoch")
    axes[1, 0].set_ylabel("Attention entropy")
    twin_axis.set_ylabel("Grad norm")
    axes[1, 0].grid(alpha=0.25)
    lines_left, labels_left = axes[1, 0].get_legend_handles_labels()
    lines_right, labels_right = twin_axis.get_legend_handles_labels()
    axes[1, 0].legend(lines_left + lines_right, labels_left + labels_right, loc="best")

    axes[1, 1].plot(epochs, history["cls_norm"], label="cls_norm", color="#2ca02c", linewidth=2.0)
    axes[1, 1].plot(epochs, history["token_std"], label="token_std", color="#8c564b", linewidth=2.0)
    axes[1, 1].set_title("Representation diagnostics")
    axes[1, 1].set_xlabel("Epoch")
    axes[1, 1].set_ylabel("Magnitude")
    axes[1, 1].grid(alpha=0.25)
    axes[1, 1].legend()

    fig.suptitle(title, fontsize=15)
    _save_figure(fig, output_path)


def _confusion_plot(*, manifest: dict[str, object], split_name: str, title: str, output_path: Path) -> None:
    confusion_path = Path(str(manifest["confusion_matrix_path"]))
    if not confusion_path.exists():
        return
    frame = pd.read_csv(confusion_path)
    frame = frame.loc[frame["split"].astype(str) == split_name].copy()
    if frame.empty:
        return

    true_labels = frame["true_class_name"].drop_duplicates().tolist()
    pred_labels = frame["pred_class_name"].drop_duplicates().tolist()
    matrix = np.zeros((len(true_labels), len(pred_labels)), dtype=float)
    true_index = {label: index for index, label in enumerate(true_labels)}
    pred_index = {label: index for index, label in enumerate(pred_labels)}
    for _, row in frame.iterrows():
        matrix[true_index[str(row["true_class_name"])]][pred_index[str(row["pred_class_name"])]] = float(row["count"])

    fig, ax = plt.subplots(figsize=(8, 6))
    image = ax.imshow(matrix, cmap="Blues")
    ax.set_xticks(np.arange(len(pred_labels)))
    ax.set_xticklabels(pred_labels, rotation=30, ha="right")
    ax.set_yticks(np.arange(len(true_labels)))
    ax.set_yticklabels(true_labels)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title(title)
    for row_index in range(matrix.shape[0]):
        for col_index in range(matrix.shape[1]):
            ax.text(col_index, row_index, f"{int(matrix[row_index, col_index])}", ha="center", va="center", color="black")
    fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    _save_figure(fig, output_path)


def _probability_curve_plot(
    *,
    manifest: dict[str, object],
    curve_kind: str,
    split_name: str,
    title: str,
    output_path: Path,
) -> None:
    if curve_kind == "pr":
        curve_path = Path(str(manifest["pr_curve_path"]))
        x_column = "recall"
        y_column = "precision"
        score_column = "average_precision"
        baseline = None
    else:
        curve_path = Path(str(manifest["roc_curve_path"]))
        x_column = "fpr"
        y_column = "tpr"
        score_column = "roc_auc"
        baseline = ((0.0, 1.0), (0.0, 1.0))

    if not curve_path.exists():
        return
    frame = pd.read_csv(curve_path)
    frame = frame.loc[frame["split"].astype(str) == split_name].copy()
    if frame.empty:
        return

    fig, ax = plt.subplots(figsize=(9, 7))
    for class_name, group in frame.groupby("class_name"):
        group = group.sort_values("point_index")
        score = group[score_column].dropna().iloc[0] if not group[score_column].dropna().empty else float("nan")
        label = f"{class_name} ({score_column}={score:.3f})" if not np.isnan(score) else str(class_name)
        ax.plot(group[x_column], group[y_column], linewidth=2.0, label=label)
    if baseline is not None:
        ax.plot(baseline[0], baseline[1], linestyle="--", color="#888888", linewidth=1.5, label="chance")
    ax.set_title(title)
    ax.set_xlabel(x_column.upper())
    ax.set_ylabel(y_column.upper())
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.05)
    ax.grid(alpha=0.25)
    ax.legend(loc="best")
    _save_figure(fig, output_path)


def _calibration_plot(*, manifest: dict[str, object], split_name: str, title: str, output_path: Path) -> None:
    calibration_path = Path(str(manifest["calibration_curve_path"]))
    if not calibration_path.exists():
        return
    frame = pd.read_csv(calibration_path)
    frame = frame.loc[frame["split"].astype(str) == split_name].copy()
    if frame.empty:
        return

    top1_rows = frame.loc[frame["class_name"].astype(str) == TOP1_CALIBRATION_LABEL].copy()
    fig, ax = plt.subplots(figsize=(8, 6))
    if not top1_rows.empty:
        top1_rows = top1_rows.sort_values("bin_index")
        ax.plot(
            top1_rows["mean_predicted_probability"],
            top1_rows["fraction_positive"],
            marker="o",
            linewidth=2.0,
            label="top1 correctness",
        )
    else:
        for class_name, group in frame.groupby("class_name"):
            group = group.sort_values("bin_index")
            ax.plot(
                group["mean_predicted_probability"],
                group["fraction_positive"],
                marker="o",
                linewidth=2.0,
                label=str(class_name),
            )
    ax.plot([0.0, 1.0], [0.0, 1.0], linestyle="--", color="#888888", linewidth=1.5, label="perfect calibration")
    ax.set_title(title)
    ax.set_xlabel("Mean predicted probability")
    ax.set_ylabel("Observed frequency")
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.05)
    ax.grid(alpha=0.25)
    ax.legend(loc="best")
    _save_figure(fig, output_path)
