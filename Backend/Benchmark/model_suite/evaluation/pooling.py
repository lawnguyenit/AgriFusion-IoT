from __future__ import annotations

import json

import pandas as pd

from Backend.Benchmark.model_suite.evaluation.metrics import summarize_protocol_classification


def build_pooled_prediction_summary(predictions_df: pd.DataFrame) -> pd.DataFrame:
    if predictions_df.empty:
        return pd.DataFrame().convert_dtypes()
    rows: list[dict[str, object]] = []
    group_columns = [
        "model_key",
        "stage_id",
        "run_scope",
        "comparison_id",
        "comparison_side",
        "feature_view_id",
        "feature_source_view_id",
        "partition",
    ]
    for keys, frame in predictions_df.groupby(group_columns, dropna=False, sort=False):
        class_names_values = frame["class_names_json"].astype("string").dropna().unique().tolist()
        if len(class_names_values) != 1:
            raise ValueError(
                "Pooled prediction group must resolve exactly one class_names_json value: "
                f"{dict(zip(group_columns, keys, strict=True))}"
            )
        class_names = json.loads(class_names_values[0])
        metrics = summarize_protocol_classification(
            frame["y_true_index"].astype(int).to_numpy(),
            frame["y_pred_index"].astype(int).to_numpy(),
            class_names,
            environment_ids=frame.get("environment_id", pd.Series(dtype="string")).astype("string").dropna().tolist(),
        )
        row = {column: value for column, value in zip(group_columns, keys, strict=True)}
        row.update(
            {
                "pooled_row_count": int(len(frame)),
                "fold_count": int(frame["fold_id"].astype("string").nunique()),
                "class_names_json": class_names_values[0],
                "accuracy": float(metrics["accuracy"]),
                "supported_class_balanced_accuracy": float(metrics["supported_class_balanced_accuracy"]),
                "supported_class_macro_f1": float(metrics["supported_class_macro_f1"]),
                "fixed_ontology_macro_f1": float(metrics["fixed_ontology_macro_f1"]),
                "weighted_f1": float(metrics["weighted_f1"]),
                "unsupported_classes_json": json.dumps(metrics["unsupported_classes"], ensure_ascii=True, separators=(",", ":")),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows).convert_dtypes()
