from __future__ import annotations

from pathlib import Path

import numpy as np
from sklearn.metrics import ConfusionMatrixDisplay, PrecisionRecallDisplay, RocCurveDisplay


def planned_plot_outputs() -> list[str]:
    return ["confusion_matrix_test.png", "roc_pr_curves_test.png"]


def write_classification_plots(
    *,
    y_true: list[int] | np.ndarray,
    y_pred: list[int] | np.ndarray,
    probabilities: list[list[float]] | np.ndarray | None,
    class_names: list[str],
    output_dir: Path,
    partition: str,
) -> list[Path]:
    """Write plots from already computed evaluation outputs; never refits a model."""
    if not class_names:
        return []
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    output_dir.mkdir(parents=True, exist_ok=True)
    truth = np.asarray(y_true, dtype=int)
    predicted = np.asarray(y_pred, dtype=int)
    if len(truth) != len(predicted):
        raise ValueError("Plot inputs must have matching truth and prediction row counts.")
    paths: list[Path] = []

    confusion_path = output_dir / f"confusion_matrix_{partition}.png"
    figure, axis = plt.subplots(figsize=(7, 6))
    ConfusionMatrixDisplay.from_predictions(
        truth,
        predicted,
        labels=list(range(len(class_names))),
        display_labels=class_names,
        cmap="Blues",
        colorbar=False,
        ax=axis,
    )
    axis.set_title(f"Confusion matrix · {partition} · n={len(truth)}")
    figure.tight_layout()
    figure.savefig(confusion_path, dpi=160, bbox_inches="tight")
    plt.close(figure)
    paths.append(confusion_path)

    if probabilities is None:
        return paths
    scores = np.asarray(probabilities, dtype=float)
    if scores.ndim != 2 or scores.shape != (len(truth), len(class_names)):
        raise ValueError("Probability matrix shape does not match rows and class names.")
    if not np.isfinite(scores).all():
        raise ValueError("Probability matrix contains NaN or infinite values.")
    curve_path = output_dir / f"roc_pr_curves_{partition}.png"
    figure, axes = plt.subplots(1, 2, figsize=(12, 5))
    estimable = 0
    for class_index, class_name in enumerate(class_names):
        binary_truth = truth == class_index
        if binary_truth.all() or not binary_truth.any():
            continue
        RocCurveDisplay.from_predictions(
            binary_truth,
            scores[:, class_index],
            name=class_name,
            ax=axes[0],
        )
        PrecisionRecallDisplay.from_predictions(
            binary_truth,
            scores[:, class_index],
            name=class_name,
            ax=axes[1],
        )
        estimable += 1
    if estimable:
        axes[0].plot([0, 1], [0, 1], linestyle="--", color="grey", linewidth=1)
        axes[0].set_title("One-vs-rest ROC")
        axes[1].set_title("One-vs-rest precision-recall")
        axes[0].legend(loc="lower right", fontsize="small")
        axes[1].legend(loc="lower left", fontsize="small")
    else:
        for axis in axes:
            axis.text(0.5, 0.5, "Curves not estimable: test partition has one class", ha="center", va="center")
            axis.set_axis_off()
    figure.suptitle(f"{partition} · n={len(truth)}")
    figure.tight_layout()
    figure.savefig(curve_path, dpi=160, bbox_inches="tight")
    plt.close(figure)
    paths.append(curve_path)
    return paths
