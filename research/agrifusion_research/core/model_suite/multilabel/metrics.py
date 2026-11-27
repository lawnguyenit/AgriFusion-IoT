from __future__ import annotations

import math

import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, recall_score, roc_auc_score


def binary_metrics(y_true: np.ndarray, y_pred: np.ndarray, probability: np.ndarray) -> dict[str, object]:
    truth = np.asarray(y_true, dtype=int)
    predicted = np.asarray(y_pred, dtype=int)
    score = np.asarray(probability, dtype=float)
    tn = int(((truth == 0) & (predicted == 0)).sum())
    fp = int(((truth == 0) & (predicted == 1)).sum())
    fn = int(((truth == 1) & (predicted == 0)).sum())
    tp = int(((truth == 1) & (predicted == 1)).sum())
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    specificity = _ratio(tn, tn + fp)
    f1 = _ratio(2 * precision * recall, precision + recall) if math.isfinite(precision) and math.isfinite(recall) else math.nan
    estimable_curves = len(np.unique(truth)) == 2
    recalls = recall_score(truth, predicted, labels=[0, 1], average=None, zero_division=0)
    supported_classes = np.unique(truth)
    return {
        "sample_count": int(len(truth)),
        "positive_support": int((truth == 1).sum()),
        "negative_support": int((truth == 0).sum()),
        "positive_prevalence": float((truth == 1).mean()) if len(truth) else math.nan,
        "accuracy": float((truth == predicted).mean()) if len(truth) else math.nan,
        "supported_class_balanced_accuracy": float(np.mean(recalls[supported_classes])) if len(truth) else math.nan,
        "precision_positive": precision,
        "recall_positive": recall,
        "specificity_negative": specificity,
        "f1_positive": f1,
        "roc_auc": float(roc_auc_score(truth, score)) if estimable_curves else math.nan,
        "average_precision": float(average_precision_score(truth, score)) if estimable_curves else math.nan,
        "brier_score": float(brier_score_loss(truth, score)) if len(truth) else math.nan,
        "log_loss": float(log_loss(truth, score, labels=[0, 1])) if len(truth) else math.nan,
        "confusion_matrix_labels_0_1": [[tn, fp], [fn, tp]],
        "curve_estimable": estimable_curves,
    }


def _ratio(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else math.nan
