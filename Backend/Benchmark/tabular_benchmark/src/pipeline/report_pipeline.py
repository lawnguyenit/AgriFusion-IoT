from __future__ import annotations

import json
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import confusion_matrix

from Backend.Benchmark.models.ft_transformer_classifier import (
    FTTransformerClassifier,
    FTTransformerClassifierConfig,
)
from Backend.Benchmark.models.tabnet_classifier import (
    DirectTabNetClassifier,
    DirectTabNetClassifierConfig,
)
from Backend.Benchmark.shared.artifacts import create_run_directory, write_json
from Backend.Benchmark.tabular_benchmark.src.config.settings import default_report_output_root

FOCUS_EXPERIMENTS = ("v0", "v1", "v2")
MODEL_ORDER = ("xgboost", "tabnet_classifier", "ft_transformer_classifier")
MODEL_COLORS = {
    "xgboost": "#2d6a4f",
    "tabnet_classifier": "#d6a33b",
    "ft_transformer_classifier": "#4d95bf",
}


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
    metrics["experiment_name"] = metrics["experiment_name"].astype(str)
    metrics["model_name"] = metrics["model_name"].astype(str)
    training_report = json.loads(report_path.read_text(encoding="utf-8"))
    metrics.to_csv(output_dir / "combined_model_metrics.csv", index=False)

    focus_metrics = _select_focus_metrics(metrics)
    best_by_experiment = (
        focus_metrics.groupby("experiment_name", as_index=False)[
            ["validation_macro_f1", "test_macro_f1", "validation_balanced_accuracy", "test_balanced_accuracy"]
        ]
        .max()
        .sort_values("test_macro_f1", ascending=False)
    )
    best_by_experiment.to_csv(output_dir / "summary_model_metrics.csv", index=False)

    focus_metrics.to_csv(output_dir / "focus_model_metrics.csv", index=False)
    focus_selected = _build_focus_selected_summary(training_run_dir=training_run_dir, focus_metrics=focus_metrics)
    focus_selected.to_csv(output_dir / "focus_selected_models.csv", index=False)
    version_reports = _build_version_report_bundle(
        training_run_dir=training_run_dir,
        label_mode=label_mode,
        focus_metrics=focus_metrics,
        output_dir=output_dir,
    )

    summary_md = output_dir / "report_summary.md"
    summary_md.write_text(
        _build_markdown_summary(
            metrics=metrics,
            training_report=training_report,
            label_mode=label_mode,
            focus_metrics=focus_metrics,
            focus_selected=focus_selected,
            version_reports=version_reports,
        ),
        encoding="utf-8",
    )
    write_json(
        output_dir / "report_manifest.json",
        {
            "run_id": run_id,
            "label_mode": label_mode,
            "training_run_dir": str(training_run_dir),
            "output_dir": str(output_dir),
            "focus_experiments": list(_resolve_focus_experiments(metrics)),
            "version_reports": version_reports,
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


def _build_version_report_bundle(
    *,
    training_run_dir: Path,
    label_mode: str,
    focus_metrics: pd.DataFrame,
    output_dir: Path,
) -> list[dict[str, object]]:
    reports: list[dict[str, object]] = []
    for experiment_name in _resolve_focus_experiments(focus_metrics):
        version_metrics = focus_metrics[focus_metrics["experiment_name"] == experiment_name].copy()
        if version_metrics.empty:
            continue
        version_dir = output_dir / experiment_name
        version_dir.mkdir(parents=True, exist_ok=True)
        version_metrics.to_csv(version_dir / "model_metrics.csv", index=False)
        _model_comparison_bar_plot(
            version_metrics,
            metric_column="test_macro_f1",
            title=f"{label_mode} {experiment_name.upper()} - test macro F1",
            output_path=version_dir / "chart_compare_test_macro_f1.png",
        )
        _model_comparison_line_plot(
            version_metrics,
            metric_column="test_macro_f1",
            title=f"{label_mode} {experiment_name.upper()} - test macro F1",
            output_path=version_dir / "chart_compare_test_macro_f1_line.png",
        )
        _model_comparison_bar_plot(
            version_metrics,
            metric_column="test_balanced_accuracy",
            title=f"{label_mode} {experiment_name.upper()} - test balanced accuracy",
            output_path=version_dir / "chart_compare_test_balanced_accuracy.png",
        )
        _model_comparison_line_plot(
            version_metrics,
            metric_column="test_balanced_accuracy",
            title=f"{label_mode} {experiment_name.upper()} - test balanced accuracy",
            output_path=version_dir / "chart_compare_test_balanced_accuracy_line.png",
        )
        _model_comparison_bar_plot(
            version_metrics,
            metric_column="test_accuracy",
            title=f"{label_mode} {experiment_name.upper()} - test accuracy",
            output_path=version_dir / "chart_compare_test_accuracy.png",
        )
        confusion_outputs = _build_version_confusion_charts(
            training_run_dir=training_run_dir,
            label_mode=label_mode,
            experiment_name=experiment_name,
            version_metrics=version_metrics,
            output_dir=version_dir,
        )
        reports.append(
            {
                "experiment_name": experiment_name,
                "output_dir": str(version_dir),
                "generated_files": sorted(path.name for path in version_dir.iterdir() if path.is_file()),
                "confusion_outputs": confusion_outputs,
            }
        )
    return reports


def _model_comparison_bar_plot(frame: pd.DataFrame, *, metric_column: str, title: str, output_path: Path) -> None:
    plot_df = frame.copy()
    plot_df["model_order"] = plot_df["model_name"].map({name: index for index, name in enumerate(MODEL_ORDER)}).fillna(99)
    plot_df = plot_df.sort_values("model_order").drop(columns=["model_order"])
    labels = [_friendly_model_name(name) for name in plot_df["model_name"]]
    values = pd.to_numeric(plot_df[metric_column], errors="coerce").fillna(0.0).tolist()
    colors = [MODEL_COLORS.get(str(name), "#6c757d") for name in plot_df["model_name"]]
    fig, ax = plt.subplots(figsize=(8.6, 5.5))
    fig.patch.set_facecolor("#fbfbf8")
    ax.set_facecolor("#fbfbf8")
    bars = ax.bar(labels, values, color=colors, width=0.62)
    ax.set_title(title, fontsize=15, fontweight="bold", pad=14)
    ax.set_ylabel(metric_column)
    ax.set_ylim(0.0, max(1.0, max(values, default=0.0) + 0.08))
    ax.grid(axis="y", alpha=0.18, linewidth=1.0)
    ax.tick_params(axis="x", rotation=8, labelsize=10.5)
    ax.tick_params(axis="y", labelsize=10.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for bar, value in zip(bars, values, strict=False):
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            value + 0.015,
            f"{value:.3f}",
            ha="center",
            va="bottom",
            fontsize=10,
        )
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _model_comparison_line_plot(frame: pd.DataFrame, *, metric_column: str, title: str, output_path: Path) -> None:
    plot_df = frame.copy()
    plot_df["model_order"] = plot_df["model_name"].map({name: index for index, name in enumerate(MODEL_ORDER)}).fillna(99)
    plot_df = plot_df.sort_values("model_order").drop(columns=["model_order"])
    labels = [_friendly_model_name(name) for name in plot_df["model_name"]]
    values = pd.to_numeric(plot_df[metric_column], errors="coerce").fillna(0.0).tolist()
    colors = [MODEL_COLORS.get(str(name), "#6c757d") for name in plot_df["model_name"]]
    x_positions = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(8.6, 5.5))
    fig.patch.set_facecolor("#fbfbf8")
    ax.set_facecolor("#fbfbf8")
    ax.plot(x_positions, values, color="#274c77", linewidth=2.4, alpha=0.8, zorder=2)
    ax.scatter(x_positions, values, s=180, c=colors, edgecolors="#ffffff", linewidths=1.8, zorder=3)
    for x_pos, value, label in zip(x_positions, values, labels, strict=False):
        ax.text(
            x_pos,
            value + 0.03,
            f"{label}\n{value:.3f}",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
        )
    ax.set_xticks(x_positions, labels)
    ax.set_title(f"{title} (line)", fontsize=15, fontweight="bold", pad=14)
    ax.set_ylabel(metric_column)
    ax.set_ylim(0.0, max(1.0, max(values, default=0.0) + 0.12))
    ax.grid(axis="y", alpha=0.18, linewidth=1.0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="x", rotation=8, labelsize=10.5)
    ax.tick_params(axis="y", labelsize=10.5)
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _resolve_focus_experiments(frame: pd.DataFrame) -> list[str]:
    available = [str(name) for name in frame["experiment_name"].dropna().unique().tolist()]
    preferred = [name for name in FOCUS_EXPERIMENTS if name in available]
    return preferred if preferred else sorted(available)


def _select_focus_metrics(metrics: pd.DataFrame) -> pd.DataFrame:
    focus_experiments = _resolve_focus_experiments(metrics)
    focus = metrics[metrics["experiment_name"].isin(focus_experiments)].copy()
    focus["model_name"] = focus["model_name"].astype(str)
    focus["model_order"] = focus["model_name"].map({name: index for index, name in enumerate(MODEL_ORDER)}).fillna(99)
    focus = focus.sort_values(["experiment_name", "model_order"]).drop(columns=["model_order"])
    return focus.reset_index(drop=True)


def _build_focus_selected_summary(*, training_run_dir: Path, focus_metrics: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for experiment_name in _resolve_focus_experiments(focus_metrics):
        report_path = training_run_dir / "experiments" / experiment_name / "training_report.json"
        if not report_path.exists():
            continue
        experiment_report = json.loads(report_path.read_text(encoding="utf-8"))
        selected_model = experiment_report.get("selected_model", {})
        model_name = str(selected_model.get("model_name", "")).strip()
        if not model_name:
            continue
        selected_row = focus_metrics[
            (focus_metrics["experiment_name"] == experiment_name) & (focus_metrics["model_name"] == model_name)
        ]
        if selected_row.empty:
            continue
        metric_row = selected_row.iloc[0]
        rows.append(
            {
                "experiment_name": experiment_name,
                "selected_model_name": model_name,
                "validation_macro_f1": float(metric_row["validation_macro_f1"]),
                "test_macro_f1": float(metric_row["test_macro_f1"]),
                "test_balanced_accuracy": float(metric_row["test_balanced_accuracy"]),
                "test_accuracy": float(metric_row["test_accuracy"]),
            }
        )
    return pd.DataFrame(rows)


def _build_version_confusion_charts(
    *,
    training_run_dir: Path,
    label_mode: str,
    experiment_name: str,
    version_metrics: pd.DataFrame,
    output_dir: Path,
) -> dict[str, object]:
    if version_metrics.empty:
        return {}

    experiment_dir = training_run_dir / "experiments" / experiment_name
    experiment_report = json.loads((experiment_dir / "training_report.json").read_text(encoding="utf-8"))
    class_names = [str(name) for name in experiment_report.get("class_names", [])]
    display_class_names = [_display_class_name(label_mode=label_mode, class_name=name) for name in class_names]
    if not class_names:
        return {}

    raw_matrices: list[tuple[str, np.ndarray]] = []
    normalized_matrices: list[tuple[str, np.ndarray]] = []
    output_map: dict[str, object] = {"per_model": {}}
    for model_name in MODEL_ORDER:
        if model_name not in version_metrics["model_name"].astype(str).tolist():
            continue
        confusion = _evaluate_confusion_matrix(
            experiment_dir=experiment_dir,
            model_name=model_name,
            class_names=class_names,
        )
        normalized = confusion.astype(np.float64)
        row_sums = normalized.sum(axis=1, keepdims=True)
        normalized = np.divide(normalized, row_sums, out=np.zeros_like(normalized), where=row_sums > 0)
        raw_matrices.append((model_name, confusion))
        normalized_matrices.append((model_name, normalized))
        normalized_model_path = output_dir / f"chart_{model_name}_confusion_matrix_normalized.png"
        raw_model_path = output_dir / f"chart_{model_name}_confusion_matrix_raw.png"
        _confusion_single_matrix_plot(
            normalized,
            model_name=model_name,
            class_names=display_class_names,
            title=f"{experiment_name.upper()} - normalized confusion matrix ({_friendly_model_name(model_name)})",
            output_path=normalized_model_path,
            value_format="float",
        )
        _confusion_single_matrix_plot(
            confusion,
            model_name=model_name,
            class_names=display_class_names,
            title=f"{experiment_name.upper()} - raw confusion matrix ({_friendly_model_name(model_name)})",
            output_path=raw_model_path,
            value_format="int",
        )
        output_map["per_model"][model_name] = {
            "normalized": str(normalized_model_path),
            "raw": str(raw_model_path),
        }

    normalized_path = output_dir / "chart_compare_confusion_matrix_normalized.png"
    raw_path = output_dir / "chart_compare_confusion_matrix_raw.png"
    _confusion_model_panel_plot(
        normalized_matrices,
        class_names=display_class_names,
        title=f"{experiment_name.upper()} - normalized confusion matrix by model",
        output_path=normalized_path,
        value_format="float",
    )
    _confusion_model_panel_plot(
        raw_matrices,
        class_names=display_class_names,
        title=f"{experiment_name.upper()} - raw confusion matrix by model",
        output_path=raw_path,
        value_format="int",
    )
    output_map["compare_normalized"] = str(normalized_path)
    output_map["compare_raw"] = str(raw_path)
    return output_map


def _evaluate_confusion_matrix(*, experiment_dir: Path, model_name: str, class_names: list[str]) -> np.ndarray:
    dataset = pd.read_csv(experiment_dir / "direct_dataset.csv")
    test_frame = dataset.loc[dataset["direct_split"] == "test"].copy()
    if test_frame.empty:
        raise ValueError(f"No test rows found for {experiment_dir}")
    feature_schema = json.loads((experiment_dir / "feature_schema.json").read_text(encoding="utf-8"))
    feature_columns = [str(column) for column in feature_schema.get("feature_columns", [])]
    features = test_frame[feature_columns].to_numpy(dtype=np.float32)
    labels = test_frame["selected_label_id"].to_numpy(dtype=np.int64)
    predictions = _predict_labels(
        model_name=model_name,
        model_dir=experiment_dir / "models",
        feature_matrix=features,
    )
    return confusion_matrix(labels, predictions, labels=list(range(len(class_names))))


def _predict_labels(*, model_name: str, model_dir: Path, feature_matrix: np.ndarray) -> np.ndarray:
    if model_name == "xgboost":
        model = joblib.load(model_dir / "xgboost.joblib")
        return np.asarray(model.predict(feature_matrix), dtype=np.int64)
    if model_name == "tabnet_classifier":
        checkpoint = torch.load(model_dir / "tabnet_classifier.pt", map_location="cpu")
        config = DirectTabNetClassifierConfig(**checkpoint["config"])
        model = DirectTabNetClassifier(
            input_dim=int(checkpoint["input_dim"]),
            output_dim=int(checkpoint["output_dim"]),
            config=config,
        )
        model.load_state_dict(checkpoint["state_dict"])
        model.eval()
        with torch.no_grad():
            logits, _ = model(torch.tensor(feature_matrix, dtype=torch.float32))
        return logits.argmax(dim=1).cpu().numpy().astype(np.int64)
    if model_name == "ft_transformer_classifier":
        checkpoint = torch.load(model_dir / "ft_transformer_classifier.pt", map_location="cpu")
        config = FTTransformerClassifierConfig(**checkpoint["config"])
        model = FTTransformerClassifier(
            input_dim=int(checkpoint["input_dim"]),
            output_dim=int(checkpoint["output_dim"]),
            config=config,
        )
        model.load_state_dict(checkpoint["state_dict"])
        model.eval()
        with torch.no_grad():
            logits, _ = model(torch.tensor(feature_matrix, dtype=torch.float32))
        return logits.argmax(dim=1).cpu().numpy().astype(np.int64)
    raise ValueError(f"Unsupported model_name for confusion export: {model_name}")


def _confusion_model_panel_plot(
    matrices: list[tuple[str, np.ndarray]],
    *,
    class_names: list[str],
    title: str,
    output_path: Path,
    value_format: str,
) -> None:
    if not matrices:
        return
    fig, axes = plt.subplots(1, len(matrices), figsize=(5.2 * len(matrices), 4.8), constrained_layout=True)
    axes_list = axes if isinstance(axes, np.ndarray) else np.asarray([axes])
    last_image = None
    color_max = 1.0 if value_format == "float" else max(float(np.max(matrix)) for _, matrix in matrices)
    text_threshold = color_max * 0.55
    for axis, (model_name, matrix) in zip(axes_list, matrices, strict=False):
        image = axis.imshow(matrix, cmap="Blues", vmin=0.0, vmax=color_max)
        last_image = image
        axis.set_title(_friendly_model_name(model_name), fontsize=12, fontweight="bold")
        axis.set_xticks(range(len(class_names)), class_names, rotation=25, ha="right")
        axis.set_yticks(range(len(class_names)), class_names)
        axis.set_xticks(np.arange(-0.5, len(class_names), 1.0), minor=True)
        axis.set_yticks(np.arange(-0.5, len(class_names), 1.0), minor=True)
        axis.grid(which="minor", color="#d9e2ec", linestyle="-", linewidth=1.2)
        axis.tick_params(which="minor", bottom=False, left=False)
        for row_index in range(matrix.shape[0]):
            for column_index in range(matrix.shape[1]):
                value = matrix[row_index, column_index]
                text = f"{int(value)}" if value_format == "int" else f"{value:.2f}"
                text_color = "#f8fafc" if value >= text_threshold else "#0f172a"
                axis.text(column_index, row_index, text, ha="center", va="center", fontsize=9.5, fontweight="bold", color=text_color)
        axis.set_xlabel("Predicted")
        axis.set_ylabel("True")
    if last_image is not None:
        fig.colorbar(last_image, ax=list(axes_list), fraction=0.03, pad=0.02)
    fig.suptitle(title, fontsize=15, fontweight="bold")
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _confusion_single_matrix_plot(
    matrix: np.ndarray,
    *,
    model_name: str,
    class_names: list[str],
    title: str,
    output_path: Path,
    value_format: str,
) -> None:
    fig, axis = plt.subplots(figsize=(6.2, 5.2))
    fig.patch.set_facecolor("#fbfbf8")
    axis.set_facecolor("#fbfbf8")
    color_max = 1.0 if value_format == "float" else max(1.0, float(np.max(matrix)))
    text_threshold = color_max * 0.55
    image = axis.imshow(matrix, cmap="Blues", vmin=0.0, vmax=color_max)
    axis.set_title(_friendly_model_name(model_name), fontsize=12.5, fontweight="bold")
    axis.set_xticks(range(len(class_names)), class_names, rotation=25, ha="right")
    axis.set_yticks(range(len(class_names)), class_names)
    axis.set_xticks(np.arange(-0.5, len(class_names), 1.0), minor=True)
    axis.set_yticks(np.arange(-0.5, len(class_names), 1.0), minor=True)
    axis.grid(which="minor", color="#d9e2ec", linestyle="-", linewidth=1.2)
    axis.tick_params(which="minor", bottom=False, left=False)
    for row_index in range(matrix.shape[0]):
        for column_index in range(matrix.shape[1]):
            value = matrix[row_index, column_index]
            text = f"{int(value)}" if value_format == "int" else f"{value:.2f}"
            text_color = "#f8fafc" if value >= text_threshold else "#0f172a"
            axis.text(column_index, row_index, text, ha="center", va="center", fontsize=10, fontweight="bold", color=text_color)
    axis.set_xlabel("Predicted")
    axis.set_ylabel("True")
    fig.colorbar(image, ax=axis, fraction=0.046, pad=0.04)
    fig.suptitle(title, fontsize=15, fontweight="bold")
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _build_markdown_summary(
    *,
    metrics: pd.DataFrame,
    training_report: dict[str, object],
    label_mode: str,
    focus_metrics: pd.DataFrame,
    focus_selected: pd.DataFrame,
    version_reports: list[dict[str, object]],
) -> str:
    if focus_metrics.empty:
        best = metrics.iloc[0]
    else:
        best = focus_metrics.sort_values(["validation_macro_f1", "test_macro_f1"], ascending=False).iloc[0]
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
        "## Focus scope",
        "",
        "- Report chinh render `v0`, `v1`, `v2` khi cac version nay co trong training run.",
        "- Moi version du lieu co folder rieng va chua chart so sanh truc tiep giua `xgboost`, `tabnet_classifier`, `ft_transformer_classifier`.",
        "- Metric chinh: `test_macro_f1`; metric phu: `test_balanced_accuracy`.",
        "",
        "## Metric table",
        "",
        _markdown_table(focus_metrics if not focus_metrics.empty else metrics),
        "",
        "## Selected model per focus version",
        "",
        _markdown_table(focus_selected),
        "",
        "## Version folders",
        "",
    ]
    if not version_reports:
        lines.append("- Khong co version focus nao du dieu kien de sinh chart.")
    else:
        for report in version_reports:
            experiment_name = str(report["experiment_name"])
            lines.extend(
                [
                    f"- `{experiment_name}/chart_compare_test_macro_f1.png`: so sanh `test_macro_f1` cua 3 model trong cung version.",
                    f"- `{experiment_name}/chart_compare_test_macro_f1_line.png`: line chart cung metric de doi chieu voi bar chart.",
                    f"- `{experiment_name}/chart_compare_test_balanced_accuracy.png`: so sanh `test_balanced_accuracy` cua 3 model trong cung version.",
                    f"- `{experiment_name}/chart_compare_test_balanced_accuracy_line.png`: line chart cung metric de doi chieu voi bar chart.",
                    f"- `{experiment_name}/chart_compare_confusion_matrix_normalized.png`: confusion matrix normalize cho ca 3 model.",
                    f"- `{experiment_name}/chart_compare_test_accuracy.png`: chart phu de doi chieu khi can.",
                    f"- `{experiment_name}/chart_compare_confusion_matrix_raw.png`: confusion matrix raw count de truy vet support.",
                    f"- `{experiment_name}/chart_<model>_confusion_matrix_normalized.png`: confusion matrix normalize rieng cho tung model.",
                    f"- `{experiment_name}/chart_<model>_confusion_matrix_raw.png`: confusion matrix raw count rieng cho tung model.",
                ]
            )
    lines.append("")
    return "\n".join(lines) + "\n"


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows_"
    headers = [str(column) for column in frame.columns]
    rows = [[_stringify_table_value(value) for value in row] for row in frame.to_numpy().tolist()]
    table_rows = [headers] + rows
    widths = [max(len(str(row[index])) for row in table_rows) for index in range(len(headers))]

    def _format_row(values: list[str]) -> str:
        return "| " + " | ".join(value.ljust(widths[index]) for index, value in enumerate(values)) + " |"

    separator = "| " + " | ".join("-" * widths[index] for index in range(len(headers))) + " |"
    lines = [_format_row(headers), separator]
    lines.extend(_format_row(row) for row in rows)
    return "\n".join(lines)


def _stringify_table_value(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _friendly_model_name(model_name: str) -> str:
    mapping = {
        "xgboost": "XGBoost",
        "tabnet_classifier": "TabNet",
        "ft_transformer_classifier": "FT-Transformer",
    }
    return mapping.get(str(model_name), str(model_name))


def _display_class_name(*, label_mode: str, class_name: str) -> str:
    if str(label_mode) == "binary":
        if class_name == "normal":
            return "normal_context"
        if class_name == "abnormal":
            return "non_normal_context"
    return class_name
