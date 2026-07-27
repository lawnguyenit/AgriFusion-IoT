from __future__ import annotations

import pandas as pd


def build_model_comparison_table(summary_df: pd.DataFrame) -> pd.DataFrame:
    if summary_df.empty:
        return pd.DataFrame().convert_dtypes()
    trained = summary_df.loc[summary_df["status"].astype("string") == "trained"].copy()
    if trained.empty:
        return pd.DataFrame().convert_dtypes()
    columns = [
        "model_key",
        "stage_id",
        "feature_view_id",
        "fold_id",
        "validation_supported_class_macro_f1",
        "test_supported_class_macro_f1",
        "validation_supported_class_balanced_accuracy",
        "test_supported_class_balanced_accuracy",
        "selected_feature_count",
    ]
    available_columns = [column for column in columns if column in trained.columns]
    return trained.loc[:, available_columns].reset_index(drop=True).convert_dtypes()
