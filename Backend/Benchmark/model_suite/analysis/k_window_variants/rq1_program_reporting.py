from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def write_program_outputs(
    *,
    output_dir: Path,
    run_manifest: dict[str, object],
    target_frame: pd.DataFrame,
    primary_cv: dict[str, pd.DataFrame],
    primary_summary: pd.DataFrame,
    primary_losses: pd.DataFrame,
    primary_contrasts: pd.DataFrame,
    factorial_by_fold: pd.DataFrame,
    factorial_summary: pd.DataFrame,
    module_a_groups: pd.DataFrame,
    alias_pairs: pd.DataFrame,
    alias_summary: pd.DataFrame,
    probe: dict[str, pd.DataFrame],
    probe_summary: pd.DataFrame,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_frame.to_parquet(output_dir / "target_program_frame.parquet", index=False)
    primary_cv["metrics"].to_csv(output_dir / "primary_cv_metrics.csv", index=False)
    primary_summary.to_csv(output_dir / "primary_cv_summary.csv", index=False)
    primary_cv["per_class"].to_csv(output_dir / "primary_per_class_metrics.csv", index=False)
    primary_cv["confusion"].to_csv(output_dir / "primary_confusion_matrix.csv", index=False)
    primary_cv["predictions"].to_parquet(output_dir / "primary_heldout_predictions.parquet", index=False)
    primary_cv["strata"].to_csv(output_dir / "primary_strata.csv", index=False)
    primary_losses.to_parquet(output_dir / "primary_per_anchor_losses.parquet", index=False)
    primary_contrasts.to_csv(output_dir / "primary_paired_contrasts.csv", index=False)
    factorial_by_fold.to_parquet(output_dir / "factorial_contrasts_by_anchor.parquet", index=False)
    factorial_summary.to_csv(output_dir / "factorial_contrast_summary.csv", index=False)
    module_a_groups.to_csv(output_dir / "module_a_s0_group_metrics.csv", index=False)
    alias_pairs.to_parquet(output_dir / "module_a_snapshot_alias_pairs.parquet", index=False)
    alias_summary.to_csv(output_dir / "module_a_snapshot_alias_summary.csv", index=False)
    probe["metrics"].to_csv(output_dir / "module_c_probe_metrics.csv", index=False)
    probe_summary.to_csv(output_dir / "module_c_probe_summary.csv", index=False)
    probe["per_class"].to_csv(output_dir / "module_c_probe_per_class.csv", index=False)
    probe["confusion"].to_csv(output_dir / "module_c_probe_confusion.csv", index=False)
    probe["predictions"].to_parquet(output_dir / "module_c_probe_predictions.parquet", index=False)
    (output_dir / "run_manifest.json").write_text(json.dumps(run_manifest, ensure_ascii=True, indent=2, allow_nan=True), encoding="utf-8")
    (output_dir / "feature_contract.json").write_text(json.dumps(run_manifest["block_contract"], ensure_ascii=True, indent=2, allow_nan=True), encoding="utf-8")
    (output_dir / "report.md").write_text(_build_report(run_manifest, primary_summary, primary_contrasts, factorial_summary, module_a_groups, alias_summary, probe_summary), encoding="utf-8")


def _build_report(manifest: dict[str, object], primary_summary: pd.DataFrame, contrasts: pd.DataFrame, factorial: pd.DataFrame, module_a: pd.DataFrame, alias: pd.DataFrame, probe: pd.DataFrame) -> str:
    test = primary_summary.loc[primary_summary["partition"].astype("string").eq("test")].copy() if not primary_summary.empty else primary_summary
    lines = [
        "# RQ1 structured experimental program",
        "",
        f"- run_id: `{manifest['run_id']}`",
        f"- model: `{manifest['model_key']}`",
        f"- folds: `{', '.join(manifest['cv_folds'])}`",
        f"- seed: `{manifest['random_seed']}`",
        "",
        "## Information blocks",
        "",
        "`D=M_t`, `C=X_t\\D`, `H_D=moisture lags`, `H_C=lags of eight supporting sensors`, `W=engineered causal 3h summaries`, `T=timestamp/age/gap/continuity`, `A=available acquisition/quality evidence`.",
        "`W` is a representation of sensor history; it is not treated as true temporal context. Unsupported RSSI/replay/buffer/server-upload fields are not fabricated.",
        "",
        _markdown_table(pd.DataFrame(manifest["program_schedule"]), ["module", "condition", "representation_id", "feature_count", "target"]),
        "",
        "## Module A — S0 group error and snapshot aliasing",
        "",
        _markdown_table(module_a, ["fold_id", "target_view_id", "group", "sample_count", "error_rate", "accuracy", "macro_f1_fixed_3class", "mean_moisture", "mean_support_depth"]),
        "",
        _markdown_table(alias, ["epsilon", "pair_count", "depth_difference_rate", "online_label_difference_rate", "event_label_difference_rate", "median_moisture_abs_diff"]),
        "",
        "## Module B and primary risk contrasts",
        "",
        "Positive log-loss delta means the richer condition reduced held-out loss. The paired comparisons are refit-based and use common test anchors.",
        "",
        _markdown_table(contrasts, ["arrow", "target_view_id", "fold_count", "anchor_count", "delta_log_loss_mean_across_folds", "pooled_delta_log_loss_ci_low", "pooled_delta_log_loss_ci_high", "delta_brier_loss_mean_across_folds", "pooled_delta_brier_loss_ci_low", "pooled_delta_brier_loss_ci_high"]),
        "",
        "## Module C — persistence-state probe",
        "",
        "The probe target is the diagnostic state `d_0/d_1/d_2/d_ge_3` derived from support depth. It is not the final target and is not a feature.",
        "",
        _markdown_table(probe.loc[probe["partition"].astype("string").eq("test")].copy() if not probe.empty else probe, ["variant_id", "representation_id", "fold_count", "macro_f1_mean", "macro_f1_std", "balanced_accuracy_mean", "macro_pr_auc_mean"]),
        "",
        "## Module D — factorial lag/window decomposition",
        "",
        "F00=X_t, F10=X_t+H_X, F01=X_t+W_X, F11=X_t+H_X+W_X. Gamma is an empirical complementarity/redundancy contrast, not a causal interaction.",
        "",
        _markdown_table(factorial, ["target_view_id", "fold_count", "anchor_count", "delta_H_log_loss_mean_across_folds", "delta_W_log_loss_mean_across_folds", "delta_HW_log_loss_mean_across_folds", "gamma_log_loss_mean_across_folds", "pooled_delta_H_log_loss_ci_low", "pooled_delta_H_log_loss_ci_high", "pooled_delta_W_log_loss_ci_low", "pooled_delta_W_log_loss_ci_high", "pooled_delta_HW_log_loss_ci_low", "pooled_delta_HW_log_loss_ci_high", "pooled_gamma_log_loss_ci_low", "pooled_gamma_log_loss_ci_high"]),
        "",
        "## Cross-fold primary metrics",
        "",
        "Macro AP is macro one-vs-rest Average Precision, not trapezoidal PR area. Macro-F1, balanced accuracy, AP, and recalls are descriptive; log loss is the primary paired risk.",
        "",
        _markdown_table(test, ["representation_id", "target_view_id", "fold_count", "macro_f1_mean", "macro_f1_std", "balanced_accuracy_mean", "macro_pr_auc_mean", "low_recall_mean", "unres_recall_mean", "ref_recall_mean"]),
        "",
        "## Limitations",
        "",
        "- Three folds and one seed remain diagnostic rather than universal inference.",
        "- Fold 03 retains its protocol partial/stress status.",
        "- Acquisition evidence is limited to missingness, validity, window coverage, resets, and gaps; RSSI, replay/buffer, and server-upload timing are unsupported in the locked benchmark.",
        "- The Firebase candidate was not mixed into this labeled benchmark run.",
    ]
    return "\n".join(lines) + "\n"


def _markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    if frame.empty:
        return "_empty_"
    selected = [column for column in columns if column in frame.columns]
    view = frame.loc[:, selected].copy()
    for column in view.columns:
        if pd.api.types.is_numeric_dtype(view[column]):
            view[column] = view[column].map(lambda value: "" if pd.isna(value) else f"{float(value):.4f}" if isinstance(value, (float, int)) or pd.api.types.is_number(value) else str(value))
        else:
            view[column] = view[column].astype("string").fillna("")
    headers = [str(value) for value in view.columns]
    rows = [[str(value) for value in row] for row in view.itertuples(index=False, name=None)]
    all_rows = [headers, *rows]
    widths = [max(len(row[index]) for row in all_rows) for index in range(len(headers))]
    fmt = lambda row: "| " + " | ".join(value.ljust(widths[index]) for index, value in enumerate(row)) + " |"
    return "\n".join([fmt(headers), "| " + " | ".join("-" * width for width in widths) + " |", *[fmt(row) for row in rows]])
