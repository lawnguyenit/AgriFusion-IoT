from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pandas.errors import EmptyDataError

from Backend.Benchmark.context_benchmark.src.scientific_artifacts import TOP1_CALIBRATION_LABEL
from Backend.Benchmark.shared.artifacts import write_json


def render_scientific_charts(
    *,
    manifest: dict[str, object],
    title_prefix: str,
) -> dict[str, str]:
    artifact_root = Path(str(manifest["artifact_root"]))
    chart_paths: dict[str, str] = {}

    diagnostics_path = artifact_root / "chart_diagnostics.png"
    if _training_diagnostics_plot(manifest=manifest, title=title_prefix, output_path=diagnostics_path):
        chart_paths["diagnostics"] = str(diagnostics_path)

    test_confusion_path = artifact_root / "chart_test_confusion.png"
    if _confusion_plot(
        manifest=manifest,
        split_name="test",
        title=f"{title_prefix} - test confusion",
        output_path=test_confusion_path,
    ):
        chart_paths["test_confusion"] = str(test_confusion_path)

    test_pr_path = artifact_root / "chart_test_pr_curve.png"
    if _probability_curve_plot(
        manifest=manifest,
        curve_kind="pr",
        split_name="test",
        title=f"{title_prefix} - test PR",
        output_path=test_pr_path,
    ):
        chart_paths["test_pr_curve"] = str(test_pr_path)

    test_roc_path = artifact_root / "chart_test_roc_curve.png"
    if _probability_curve_plot(
        manifest=manifest,
        curve_kind="roc",
        split_name="test",
        title=f"{title_prefix} - test ROC",
        output_path=test_roc_path,
    ):
        chart_paths["test_roc_curve"] = str(test_roc_path)

    test_calibration_path = artifact_root / "chart_test_calibration.png"
    if _calibration_plot(
        manifest=manifest,
        split_name="test",
        title=f"{title_prefix} - test calibration",
        output_path=test_calibration_path,
    ):
        chart_paths["test_calibration"] = str(test_calibration_path)

    manifest["chart_paths"] = chart_paths
    manifest_path = Path(str(manifest["manifest_path"]))
    write_json(manifest_path, manifest)
    return chart_paths


def _save_figure(fig: plt.Figure, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def _training_diagnostics_plot(*, manifest: dict[str, object], title: str, output_path: Path) -> bool:
    history_path = Path(str(manifest["history_csv_path"]))
    if not history_path.exists():
        return False
    try:
        history = pd.read_csv(history_path)
    except EmptyDataError:
        return False
    if history.empty or "epoch" not in history.columns:
        return False

    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    epochs = history["epoch"].astype(float).to_numpy()

    axes[0, 0].plot(epochs, history["train_loss"], label="train_loss", color="#1f77b4", linewidth=2.0)
    if "validation_loss" in history.columns:
        axes[0, 0].plot(epochs, history["validation_loss"], label="validation_loss", color="#ff7f0e", linewidth=2.0)
    if "is_best_epoch" in history.columns:
        best_rows = history.loc[history["is_best_epoch"].astype(bool)]
        if not best_rows.empty and "validation_loss" in best_rows.columns:
            best_epoch = float(best_rows.iloc[-1]["epoch"])
            best_loss = float(best_rows.iloc[-1]["validation_loss"])
            axes[0, 0].scatter([best_epoch], [best_loss], color="#2ca02c", s=40, zorder=5, label="best_epoch")
    axes[0, 0].set_title("Loss curves")
    axes[0, 0].set_xlabel("Epoch")
    axes[0, 0].set_ylabel("Loss")
    axes[0, 0].grid(alpha=0.25)
    axes[0, 0].legend()

    if "validation_macro_f1" in history.columns:
        axes[0, 1].plot(epochs, history["validation_macro_f1"], label="validation_macro_f1", color="#1f77b4", linewidth=2.0)
    if "test_macro_f1" in history.columns:
        axes[0, 1].plot(epochs, history["test_macro_f1"], label="test_macro_f1", color="#ff7f0e", linewidth=2.0)
    axes[0, 1].set_title("Macro-F1 curves")
    axes[0, 1].set_xlabel("Epoch")
    axes[0, 1].set_ylabel("Macro-F1")
    axes[0, 1].set_ylim(0.0, 1.05)
    axes[0, 1].grid(alpha=0.25)
    handles, labels = axes[0, 1].get_legend_handles_labels()
    if handles:
        axes[0, 1].legend()

    if "attention_entropy" in history.columns:
        axes[1, 0].plot(epochs, history["attention_entropy"], label="attention_entropy", color="#9467bd", linewidth=2.0)
    elif "mask_density" in history.columns:
        axes[1, 0].plot(epochs, history["mask_density"], label="mask_density", color="#9467bd", linewidth=2.0)
    twin_axis = axes[1, 0].twinx()
    if "grad_norm" in history.columns:
        twin_axis.plot(epochs, history["grad_norm"], label="grad_norm", color="#d62728", linewidth=2.0, alpha=0.85)
    axes[1, 0].set_title("Training diagnostics")
    axes[1, 0].set_xlabel("Epoch")
    axes[1, 0].grid(alpha=0.25)
    lines_left, labels_left = axes[1, 0].get_legend_handles_labels()
    lines_right, labels_right = twin_axis.get_legend_handles_labels()
    if lines_left or lines_right:
        axes[1, 0].legend(lines_left + lines_right, labels_left + labels_right, loc="best")

    plotted_right = False
    if "cls_norm" in history.columns:
        axes[1, 1].plot(epochs, history["cls_norm"], label="cls_norm", color="#2ca02c", linewidth=2.0)
        plotted_right = True
    if "token_std" in history.columns:
        axes[1, 1].plot(epochs, history["token_std"], label="token_std", color="#8c564b", linewidth=2.0)
        plotted_right = True
    if "mask_density" in history.columns:
        axes[1, 1].plot(epochs, history["mask_density"], label="mask_density", color="#17becf", linewidth=2.0)
        plotted_right = True
    if "epoch_seconds" in history.columns:
        axes[1, 1].plot(epochs, history["epoch_seconds"], label="epoch_seconds", color="#bcbd22", linewidth=2.0)
        plotted_right = True
    axes[1, 1].set_title("Representation / runtime diagnostics")
    axes[1, 1].set_xlabel("Epoch")
    axes[1, 1].grid(alpha=0.25)
    if plotted_right:
        axes[1, 1].legend()

    fig.suptitle(title, fontsize=15)
    _save_figure(fig, output_path)
    return True


def _confusion_plot(*, manifest: dict[str, object], split_name: str, title: str, output_path: Path) -> bool:
    confusion_path = Path(str(manifest["confusion_matrix_path"]))
    if not confusion_path.exists():
        return False
    frame = pd.read_csv(confusion_path)
    frame = frame.loc[frame["split"].astype(str) == split_name].copy()
    if frame.empty:
        return False

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
    return True


def _probability_curve_plot(
    *,
    manifest: dict[str, object],
    curve_kind: str,
    split_name: str,
    title: str,
    output_path: Path,
) -> bool:
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
        return False
    frame = pd.read_csv(curve_path)
    frame = frame.loc[frame["split"].astype(str) == split_name].copy()
    if frame.empty:
        return False

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
    return True


def _calibration_plot(*, manifest: dict[str, object], split_name: str, title: str, output_path: Path) -> bool:
    calibration_path = Path(str(manifest["calibration_curve_path"]))
    if not calibration_path.exists():
        return False
    frame = pd.read_csv(calibration_path)
    frame = frame.loc[frame["split"].astype(str) == split_name].copy()
    if frame.empty:
        return False

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
    return True
