from __future__ import annotations

import pandas as pd


def build_run_summary_table(summary_df: pd.DataFrame) -> pd.DataFrame:
    if summary_df.empty:
        return pd.DataFrame().convert_dtypes()
    preferred_columns = [
        "model_key",
        "stage_id",
        "run_scope",
        "comparison_id",
        "comparison_side",
        "feature_view_id",
        "fold_id",
        "status",
        "train_count",
        "validation_count",
        "test_count",
        "validation_supported_class_macro_f1",
        "test_supported_class_macro_f1",
        "validation_supported_class_balanced_accuracy",
        "test_supported_class_balanced_accuracy",
    ]
    available = [column for column in preferred_columns if column in summary_df.columns]
    return summary_df.loc[:, available].copy().convert_dtypes()
