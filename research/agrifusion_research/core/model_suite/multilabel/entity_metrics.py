from __future__ import annotations

from pathlib import Path

import pandas as pd

from .metrics import binary_metrics


def build_entity_metrics(predictions: pd.DataFrame, source_labels_path: Path) -> pd.DataFrame:
    source = pd.read_parquet(source_labels_path)
    if "entity_id" not in source.columns:
        return pd.DataFrame()
    keys = ["sample_id", "entity_id", *(["timestamp"] if "timestamp" in source.columns else [])]
    meta = source.loc[:, keys].drop_duplicates("sample_id")
    joined = predictions.merge(meta, on="sample_id", how="left", validate="many_to_one")
    if joined["entity_id"].isna().any():
        raise ValueError("Some model prediction rows have no source entity identity.")
    rows: list[dict[str, object]] = []
    for (fold_id, partition, target, entity_id), group in joined.groupby(
        ["fold_id", "partition", "target", "entity_id"], sort=True, dropna=False
    ):
        target_known = group["y_true"].notna()
        x_observable = (
            group["x_observable"].fillna(False).astype(bool)
            if "x_observable" in group
            else pd.Series(True, index=group.index)
        )
        predicts = (
            group["prediction_status"].astype("string").ne("MODEL_ABSTAIN_NO_X")
            if "prediction_status" in group
            else pd.Series(True, index=group.index)
        )
        metric_rows = target_known & predicts
        truth = group.loc[metric_rows, "y_true"].astype(int).to_numpy()
        score = group.loc[metric_rows, "positive_probability"].astype(float).to_numpy()
        target_truth = group.loc[target_known, "y_true"].astype(int).to_numpy()
        support = {str(value): int(count) for value, count in pd.Series(truth).value_counts().sort_index().items()}
        target_support = {str(value): int(count) for value, count in pd.Series(target_truth).value_counts().sort_index().items()}
        estimable = set(truth.tolist()) == {0, 1}
        metrics = binary_metrics(
            truth,
            (score >= float(group["probability_threshold"].iloc[0])).astype(int),
            score,
        ) if len(truth) else {}
        if not estimable:
            for key in ("supported_class_balanced_accuracy", "precision_positive", "recall_positive", "specificity_negative", "f1_positive", "roc_auc", "average_precision", "curve_estimable"):
                metrics[key] = pd.NA
        rows.append({
            "fold_id": str(fold_id),
            "partition": str(partition),
            "target": str(target),
            "entity_id": str(entity_id),
            "row_count": int(len(group)),
            "known_truth_count": int(target_known.sum()),
            "unknown_truth_count": int((~target_known).sum()),
            "x_observable_count": int(x_observable.sum()),
            "known_but_no_x_count": int((target_known & ~x_observable).sum()),
            "model_abstention_count": int((~predicts).sum()),
            "evaluated_known_count": int(metric_rows.sum()),
            "target_positive_support": target_support.get("1", 0),
            "target_negative_support": target_support.get("0", 0),
            "positive_support": support.get("1", 0),
            "negative_support": support.get("0", 0),
            "positive_prevalence": float((truth == 1).mean()) if len(truth) else pd.NA,
            "within_entity_discrimination_estimable": estimable,
            "within_entity_estimable": estimable,
            "probabilistic_loss_estimable": bool(len(truth) > 0),
            "estimability_status": "discrimination_estimable" if estimable else ("probabilistic_losses_only" if len(truth) else "not_estimable_no_observable_known_truth"),
            **{key: metrics.get(key, pd.NA) for key in (
                "supported_class_balanced_accuracy", "f1_positive", "roc_auc", "average_precision", "brier_score", "log_loss"
            )},
        })
    return pd.DataFrame(rows).convert_dtypes()
