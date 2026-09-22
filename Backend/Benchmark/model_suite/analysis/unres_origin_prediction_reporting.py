"""Reports for the post-hoc UNRES-origin prediction join."""

from __future__ import annotations

from typing import Any

import pandas as pd


def build_readme(manifest: dict[str, Any], report_path_name: str) -> str:
    return f"""# UNRES-origin prediction join

This directory is a post-hoc analysis of the existing model-suite run
`{manifest['source_model_run_id']}`.  It joins by `{manifest['join_key']}` to
the derived UNRES-origin artifact and does not change labels, weights, model
inputs, or the target ontology.  The human-readable report is
`{report_path_name}`.

`UNRES_K` and `UNRES_A` are provenance slices of the existing true UNRES
rows.  They are not new model classes in this analysis.
"""


def build_report(manifest: dict[str, Any], confusion: pd.DataFrame, coverage: pd.DataFrame) -> str:
    lines = [
        "# UNRES-origin prediction join — post-hoc report",
        "",
        "> Existing held-out predictions were reused. No retraining, weight",
        "> loading, new inference, label mutation, or target-ontology change was performed.",
        "",
        "## Lineage and scope",
        "",
        f"- Source model run: `{manifest['source_model_run_id']}`",
        f"- Source prediction file: `{manifest['source_predictions_path']}`",
        f"- Source origin artifact: `{manifest['source_unres_origin_artifact_id']}`",
        f"- Join key: `{manifest['join_key']}`",
        f"- Feature views: `{', '.join(manifest['feature_view_ids'])}`",
        f"- Partitions: `{', '.join(manifest['partitions'])}`",
        "- New model training: `false`",
        "- New model inference: `false`",
        "- Native labels mutated: `false`",
        "",
        "## Interpretation",
        "",
        "The model still predicts the original three classes `LOW`, `UNRES`, and `REF`.",
        "`UNRES_K` and `UNRES_A` only stratify rows whose true model label is UNRES.",
        "Therefore the reported recall is `Pred UNRES / support` separately for each",
        "origin. It measures whether the existing model recognizes each UNRES route;",
        "it does not claim that the model learned to distinguish K from A.",
        "",
        "## Requested test table",
        "",
        _markdown_table(
            confusion,
            ["feature_view_id", "partition", "true_origin", "pred_low", "pred_unres", "pred_ref", "support", "recall"],
            headings=["Feature view", "Partition", "True origin", "Pred LOW", "Pred UNRES", "Pred REF", "Support", "Recall"],
        ),
        "",
        "## Join coverage",
        "",
        _markdown_table(
            coverage,
            ["feature_view_id", "partition", "prediction_rows", "origin_rows_expected_in_prediction_scope", "origin_rows_joined", "join_rate"],
            headings=["Feature view", "Partition", "Prediction rows", "Origin rows expected", "Origin rows joined", "Join rate"],
        ),
        "",
        "## Machine-readable outputs",
        "",
        "- `unres_origin_prediction_rows.parquet`: one joined row per selected prediction and UNRES-origin anchor.",
        "- `unres_origin_prediction_confusion.csv`: requested origin-by-prediction counts and recall.",
        "- `unres_origin_prediction_join_coverage.csv`: join completeness by view and partition.",
        "- `run_metadata/run_manifest.json`: source hashes and post-hoc/no-retrain flags.",
    ]
    return "\n".join(lines) + "\n"


def _markdown_table(frame: pd.DataFrame, columns: list[str], headings: list[str] | None = None) -> str:
    if frame.empty:
        return "_empty_"
    display = frame.loc[:, columns].copy()
    display = display.astype("string").fillna("")
    names = headings or columns
    header = "| " + " | ".join(names) + " |"
    separator = "| " + " | ".join("---" for _ in names) + " |"
    rows = [
        "| " + " | ".join(str(value) for value in row) + " |"
        for row in display.itertuples(index=False, name=None)
    ]
    return "\n".join([header, separator, *rows])
