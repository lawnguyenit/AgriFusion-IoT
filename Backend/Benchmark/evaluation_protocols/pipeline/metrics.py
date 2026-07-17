from __future__ import annotations

import math

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)


def summarize_protocol_classification(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    class_names: list[str],
) -> dict[str, object]:
    label_indices = list(range(len(class_names)))
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=label_indices,
        average=None,
        zero_division=0,
    )
    class_rows: dict[str, dict[str, object]] = {}
    supported_f1_values: list[float] = []
    supported_recall_values: list[float] = []
    weighted_numerator = 0.0
    total_support = int(np.sum(support))
    unsupported_classes: list[str] = []

    for index, class_name in enumerate(class_names):
        class_support = int(support[index])
        estimable = class_support > 0
        if estimable:
            supported_f1_values.append(float(f1[index]))
            supported_recall_values.append(float(recall[index]))
            weighted_numerator += float(f1[index]) * class_support
        else:
            unsupported_classes.append(class_name)
        class_rows[class_name] = {
            "precision": float(precision[index]) if estimable else None,
            "recall": float(recall[index]) if estimable else None,
            "f1_score": float(f1[index]) if estimable else None,
            "support": class_support,
            "estimable": estimable,
        }

    fixed_ontology_macro_f1 = float(np.mean(f1)) if len(f1) > 0 else math.nan
    supported_class_macro_f1 = (
        float(np.mean(supported_f1_values))
        if supported_f1_values
        else math.nan
    )
    supported_class_balanced_accuracy = (
        float(np.mean(supported_recall_values))
        if supported_recall_values
        else math.nan
    )
    weighted_f1 = (
        float(weighted_numerator / total_support)
        if total_support > 0
        else math.nan
    )

    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "supported_class_balanced_accuracy": supported_class_balanced_accuracy,
        "supported_class_macro_f1": supported_class_macro_f1,
        "fixed_ontology_macro_f1": fixed_ontology_macro_f1,
        "weighted_f1": weighted_f1,
        "supported_classes": [class_name for class_name in class_names if class_name not in unsupported_classes],
        "unsupported_classes": unsupported_classes,
        "ontology_all_classes_supported": len(unsupported_classes) == 0,
        "class_count_supported": int(len(class_names) - len(unsupported_classes)),
        "class_count_total": int(len(class_names)),
        "class_metrics": class_rows,
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=label_indices).tolist(),
    }
