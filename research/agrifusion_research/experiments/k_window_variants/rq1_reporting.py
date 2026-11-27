from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .configured_runner import ConfiguredVariant


def write_rq1_outputs(
    *,
    output_dir: Path,
    run_manifest: dict[str, object],
    target_frame: pd.DataFrame,
    variants: tuple[ConfiguredVariant, ...],
    cv: dict[str, pd.DataFrame],
    cv_summary: pd.DataFrame,
    fold_support: pd.DataFrame,
    fold_status: dict[str, dict[str, object]],
    losses: pd.DataFrame,
    fold_contrasts: pd.DataFrame,
    contrast_summary: pd.DataFrame,
    oracle_rows: pd.DataFrame,
    oracle_summary: pd.DataFrame,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_frame.to_parquet(output_dir / "target_rq1_frame.parquet", index=False)
    cv["metrics"].to_csv(output_dir / "cv_metrics.csv", index=False)
    cv_summary.to_csv(output_dir / "cv_summary.csv", index=False)
    cv["per_class"].to_csv(output_dir / "per_class_metrics.csv", index=False)
    cv["confusion"].to_csv(output_dir / "confusion_matrix.csv", index=False)
    cv["predictions"].to_parquet(output_dir / "heldout_predictions.parquet", index=False)
    cv["strata"].to_csv(output_dir / "stratum_metrics.csv", index=False)
    fold_support.to_csv(output_dir / "fold_support.csv", index=False)
    (output_dir / "fold_status.json").write_text(json.dumps(fold_status, ensure_ascii=True, indent=2), encoding="utf-8")
    losses.to_parquet(output_dir / "per_anchor_losses.parquet", index=False)
    fold_contrasts.to_csv(output_dir / "paired_contrasts_by_fold.csv", index=False)
    contrast_summary.to_csv(output_dir / "paired_contrast_summary.csv", index=False)
    oracle_rows.to_parquet(output_dir / "threshold_only_positive_control_rows.parquet", index=False)
    oracle_summary.to_csv(output_dir / "threshold_only_positive_control_summary.csv", index=False)
    label_distribution = _build_label_distribution(cv["predictions"])
    label_distribution.to_csv(output_dir / "heldout_label_distribution.csv", index=False)
    (output_dir / "feature_contract.json").write_text(
        json.dumps(run_manifest["representation_contract"], ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    (output_dir / "run_manifest.json").write_text(
        json.dumps(run_manifest, ensure_ascii=True, indent=2, allow_nan=True),
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(
        _build_report(run_manifest, cv_summary, fold_support, fold_status, contrast_summary, oracle_summary),
        encoding="utf-8",
    )


def _build_label_distribution(predictions: pd.DataFrame) -> pd.DataFrame:
    if predictions.empty:
        return pd.DataFrame()
    return (
        predictions.groupby(["fold_id", "target_view_id", "representation_id", "partition", "label_true"], sort=True)
        .size()
        .rename("count")
        .reset_index()
        .convert_dtypes()
    )


def _build_report(
    run_manifest: dict[str, object],
    cv_summary: pd.DataFrame,
    fold_support: pd.DataFrame,
    fold_status: dict[str, dict[str, object]],
    contrast_summary: pd.DataFrame,
    oracle_summary: pd.DataFrame,
) -> str:
    test_summary = cv_summary.loc[cv_summary["partition"].astype("string").eq("test")].copy()
    test_summary["sequence_order"] = test_summary["representation_id"].map(_sequence_order)
    test_summary = test_summary.sort_values(["target_view_id", "sequence_order"])
    lines = [
        "# RQ1 nested information progression",
        "",
        f"- run_id: `{run_manifest['run_id']}`",
        f"- model: `{run_manifest['model_key']}`",
        f"- folds: `{', '.join(run_manifest['cv_folds'])}`",
        f"- seed: `{run_manifest['random_seed']}`",
        "",
        "## Estimand",
        "",
        "`S0=M_t → S1=X_t → S2=X_t+H_M → S3=X_t+H_X → S4=X_t+H_X+C`.",
        "`B_M=M_t+H_M` is a diagnostic branch, not a main-chain transition.",
        "A positive paired delta is loss(previous) minus loss(next), so positive means the richer information set reduced observed predictive loss.",
        "",
        _markdown_table(pd.DataFrame(run_manifest["sequence"]), ["order", "stage", "role", "feature_count", "definition"]),
        "",
        "## Cross-fold test metrics",
        "",
        "Values are fold means ± standard deviation for the protocol-owned folds. PR is macro one-vs-rest Average Precision, not trapezoidal PR area.",
        "",
        _markdown_table(
            test_summary,
            ["sequence_order", "representation_id", "target_view_id", "fold_count", "evaluation_count_mean", "balanced_accuracy_mean", "balanced_accuracy_std", "macro_f1_mean", "macro_f1_std", "macro_pr_auc_mean", "macro_pr_auc_std", "low_recall_mean", "unres_recall_mean", "ref_recall_mean"],
        ),
        "",
        "## Paired predictive-risk contrasts",
        "",
        "Primary losses are multiclass log loss and multiclass Brier loss. CIs use a moving temporal block bootstrap with the configured block length within node/segment/fold groups.",
        "",
        _markdown_table(
            contrast_summary,
            ["arrow", "target_view_id", "fold_count", "anchor_count", "delta_log_loss_mean_across_folds", "delta_log_loss_sd_across_folds", "pooled_delta_log_loss_ci_low", "pooled_delta_log_loss_ci_high", "delta_brier_loss_mean_across_folds", "delta_brier_loss_sd_across_folds", "pooled_delta_brier_loss_ci_low", "pooled_delta_brier_loss_ci_high"],
        ),
        "",
        "## Threshold-only positive control",
        "",
        "The direct moisture-threshold control is not an exact oracle for the final target because it does not reconstruct continuity/acquisition semantics.",
        "",
        _markdown_table(oracle_summary, ["fold_id", "oracle", "target", "sample_count", "oracle_positive_count", "target_low_count", "precision_low", "recall_low", "f1_low", "agreement_with_target"]),
        "",
        "## Fold status and limitations",
        "",
        "\n".join(f"- {fold}: {status}" for fold, status in fold_status.items()),
        "",
        _markdown_table(fold_support, ["fold_id", "partition", "target", "label_name", "count", "fold_row_count"]),
        "",
        "- Fold 03 retains its protocol-marked partial/stress status.",
        "- Three folds and one seed are stronger than Fold 01 alone but remain diagnostic, not universal inference.",
        "- The new Firebase candidate was not mixed into this run because its new rows do not yet have an approved matching label release.",
    ]
    return "\n".join(lines) + "\n"


def _sequence_order(value: object) -> int:
    return {"S0_M_t": 0, "S1_X_t": 1, "S2_X_t_HM": 2, "S3_X_t_HX": 3, "S4_X_t_HX_C": 4, "B_M": 99}.get(str(value), 999)


def _markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    if frame.empty:
        return "_empty_"
    selected = [column for column in columns if column in frame.columns]
    view = frame.loc[:, selected].copy()
    for column in view.columns:
        if pd.api.types.is_float_dtype(view[column]):
            view[column] = view[column].map(lambda value: "" if pd.isna(value) else f"{float(value):.4f}")
        else:
            view[column] = view[column].astype("string").fillna("")
    headers = [str(value) for value in view.columns]
    rows = [[str(value) for value in row] for row in view.itertuples(index=False, name=None)]
    all_rows = [headers, *rows]
    widths = [max(len(row[index]) for row in all_rows) for index in range(len(headers))]
    fmt = lambda row: "| " + " | ".join(value.ljust(widths[index]) for index, value in enumerate(row)) + " |"
    return "\n".join([fmt(headers), "| " + " | ".join("-" * width for width in widths) + " |", *[fmt(row) for row in rows]])
