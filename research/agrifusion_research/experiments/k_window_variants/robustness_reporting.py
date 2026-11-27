from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def write_robustness_outputs(
    *,
    output_dir: Path,
    run_manifest: dict[str, object],
    target_frame: pd.DataFrame,
    single: dict[str, pd.DataFrame],
    cv: dict[str, pd.DataFrame],
    label_distribution: pd.DataFrame,
    fold_support: pd.DataFrame,
    fold_status: dict[str, dict[str, object]],
    unres_audit: pd.DataFrame,
    oracle_rows: pd.DataFrame,
    oracle_summary: pd.DataFrame,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_frame.to_parquet(output_dir / "target_frame_primary.parquet", index=False)
    label_distribution.to_csv(output_dir / "label_distribution.csv", index=False)
    fold_support.to_csv(output_dir / "cv_fold_support.csv", index=False)
    pd.DataFrame(
        [{"fold_id": fold_id, **status} for fold_id, status in fold_status.items()]
    ).to_csv(output_dir / "cv_fold_status.csv", index=False)
    unres_audit.to_csv(output_dir / "unres_provenance_audit.csv", index=False)
    oracle_rows.to_parquet(output_dir / "threshold_history_oracle_rows.parquet", index=False)
    oracle_summary.to_csv(output_dir / "threshold_history_oracle_summary.csv", index=False)
    disruption_comparison = _build_disruption_comparison(single["metrics"])
    disruption_comparison.to_csv(output_dir / "disruption_comparison.csv", index=False)
    for prefix, payload in (("single_fold", single), ("cv", cv)):
        for key, frame in payload.items():
            suffix = "parquet" if key == "predictions" else "csv"
            frame.to_parquet(output_dir / f"{prefix}_{key}.{suffix}", index=False) if suffix == "parquet" else frame.to_csv(output_dir / f"{prefix}_{key}.{suffix}", index=False)
    (output_dir / "feature_contract.json").write_text(
        json.dumps(run_manifest["feature_contract"], ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    (output_dir / "run_manifest.json").write_text(
        json.dumps(run_manifest, ensure_ascii=True, indent=2, allow_nan=True),
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(
        _build_report(
            run_manifest=run_manifest,
            label_distribution=label_distribution,
            single_metrics=single["metrics"],
            disruption_comparison=disruption_comparison,
            cv_metrics=cv["metrics"],
            cv_summary=cv.get("summary", pd.DataFrame()),
            fold_support=fold_support,
            fold_status=fold_status,
            unres_audit=unres_audit,
            oracle_summary=oracle_summary,
        ),
        encoding="utf-8",
    )


def _build_report(
    *,
    run_manifest: dict[str, object],
    label_distribution: pd.DataFrame,
    single_metrics: pd.DataFrame,
    disruption_comparison: pd.DataFrame,
    cv_metrics: pd.DataFrame,
    cv_summary: pd.DataFrame,
    fold_support: pd.DataFrame,
    fold_status: dict[str, dict[str, object]],
    unres_audit: pd.DataFrame,
    oracle_summary: pd.DataFrame,
) -> str:
    test_metrics = single_metrics.loc[single_metrics["partition"].eq("test")].copy()
    lines = [
        "# Robustness and claim-audit suite",
        "",
        f"- run_id: `{run_manifest['run_id']}`",
        f"- model: `{run_manifest['model_key']}`",
        f"- primary fold/seed: `{run_manifest['primary_fold_policy']}` / `{run_manifest['random_seed']}`",
        "",
        "This report is additive and analysis-only. It does not mutate the canonical feature views or native label release.",
        "",
        "## Feature contracts",
        "",
        _markdown_table(pd.DataFrame(run_manifest["feature_contract"]["representations"]), ["representation_id", "display_name", "feature_count", "sensor_lag_count", "metadata_count", "temporal_order_disrupted"]),
        "",
        "## Label distributions",
        "",
        _markdown_table(label_distribution, ["target", "scope", "label_name", "count", "share_pct"]),
        "",
        "## Test 1 — pure sensor history versus metadata",
        "",
        "`R_pure_lag` is the current row plus 108 sensor lags. `R_meta` is only 12 lag-age plus 5 history-quality fields. The comparison is on the same target and held-out primary fold.",
        "",
        _markdown_table(test_metrics.loc[test_metrics["representation_id"].isin(["R01", "R_pure_lag", "R_meta"])] if not test_metrics.empty else test_metrics, ["variant_id", "target_view_id", "representation_id", "feature_count", "evaluation_count", "balanced_accuracy", "macro_f1", "weighted_f1", "macro_pr_auc_ovr", "low_recall", "unres_recall", "ref_recall"]),
        "",
        "## Test 2 — same-dimensional temporal-order disruption",
        "",
        "Each row keeps the same lag values and nine-channel alignment, but lag positions are randomly permuted as blocks. A drop relative to the corresponding clean representation is evidence that chronology contributes beyond static values.",
        "",
        _markdown_table(test_metrics.loc[test_metrics["representation_id"].isin(["R_pure_lag", "R_pure_lag_disrupted", "R01", "R01_disrupted"])] if not test_metrics.empty else test_metrics, ["variant_id", "target_view_id", "representation_id", "feature_count", "balanced_accuracy", "macro_f1", "macro_pr_auc_ovr", "low_recall", "unres_recall"]),
        "",
        _markdown_table(disruption_comparison.loc[disruption_comparison["partition"].eq("test")] if not disruption_comparison.empty else disruption_comparison, ["target_view_id", "clean_representation", "disrupted_representation", "macro_f1_clean", "macro_f1_disrupted", "delta_macro_f1", "balanced_accuracy_clean", "balanced_accuracy_disrupted", "delta_balanced_accuracy", "macro_pr_auc_clean", "macro_pr_auc_disrupted", "delta_macro_pr_auc"]),
        "",
        "## Test 3 — UNRES_K versus UNRES_A shortcut audit",
        "",
        "`UNRES_K` is reported as `U_K_succ` plus `U_K_fail`; `U_A` is acquisition/gap-related. These are post-hoc held-out strata, not model inputs.",
        "",
        _markdown_table(unres_audit.loc[unres_audit["condition"].isin(["exclude_U_A", "UNRES_K", "U_K_succ", "U_K_fail", "U_A"])] if not unres_audit.empty else unres_audit, ["variant_id", "target_view_id", "condition", "sample_count", "accuracy", "macro_f1_fixed_3class", "low_recall", "unres_recall", "ref_recall", "predicted_unres_rate"]),
        "",
        "## Test 4 — repeated temporal folds",
        "",
        _markdown_table(pd.DataFrame([{ "fold_id": fold_id, **status } for fold_id, status in fold_status.items()]), ["fold_id", "fold_status", "primary_benchmark_eligible", "stress_analysis_eligible", "status_reason"]),
        "",
        _markdown_table(fold_support.loc[fold_support["partition"].eq("test")] if not fold_support.empty else fold_support, ["fold_id", "partition", "target", "label_name", "count", "fold_row_count"]),
        "",
        _markdown_table(cv_summary.loc[cv_summary["partition"].eq("test")] if not cv_summary.empty else cv_summary, ["variant_id", "target_view_id", "representation_id", "fold_count", "balanced_accuracy_mean", "balanced_accuracy_std", "macro_f1_mean", "macro_f1_std", "macro_pr_auc_mean", "macro_pr_auc_std", "low_recall_mean", "low_recall_std", "unres_recall_mean", "unres_recall_std"]),
        "",
        "## Test 5 — deterministic reconstruction oracle",
        "",
        "The positive control directly evaluates the threshold gate from M_t, M_t-1, and M_t-2. It measures reconstruction ceiling/agreement; it is not an independent ground-truth replacement or a deployable feature set.",
        "",
        _markdown_table(oracle_summary, ["oracle", "target", "sample_count", "oracle_positive_count", "target_low_count", "coverage_all_three_finite", "coverage_three_step_causal_within_3h", "precision_low", "recall_low", "f1_low", "balanced_accuracy", "agreement_with_target"]),
        "",
        "## Interpretation guardrails",
        "",
        "- A pure-lag gain over R_meta supports sensor-history information, but does not by itself prove causal agronomic validity.",
        "- A disrupted-order drop supports temporal-order dependence only under this fixed permutation and seed; repeated disruptions/seeds remain useful for a publication claim.",
        "- UNRES_A exclusion is a conditional evaluation, not a retrained acquisition-free model.",
        "- Fold 03 is included as a usable temporal diagnostic but is protocol-marked partial/stress; folds 01--02 are full candidates, so the mean is still a multi-fold diagnostic rather than a final transport/generalization estimate.",
        "- The oracle uses the same threshold-derived target context for validation and is therefore a positive control, not an independent label audit.",
    ]
    return "\n".join(lines) + "\n"


def _build_disruption_comparison(metrics: pd.DataFrame) -> pd.DataFrame:
    if metrics.empty:
        return pd.DataFrame()
    rows: list[dict[str, object]] = []
    pairs = (("R_pure_lag", "R_pure_lag_disrupted"), ("R01", "R01_disrupted"))
    for target_view_id in metrics["target_view_id"].astype("string").unique().tolist():
        for partition in metrics["partition"].astype("string").unique().tolist():
            subset = metrics.loc[(metrics["target_view_id"].eq(target_view_id)) & (metrics["partition"].eq(partition))].set_index("representation_id")
            for clean, disrupted in pairs:
                if clean not in subset.index or disrupted not in subset.index:
                    continue
                rows.append(
                    {
                        "target_view_id": target_view_id,
                        "partition": partition,
                        "clean_representation": clean,
                        "disrupted_representation": disrupted,
                        "macro_f1_clean": subset.loc[clean, "macro_f1"],
                        "macro_f1_disrupted": subset.loc[disrupted, "macro_f1"],
                        "delta_macro_f1": subset.loc[disrupted, "macro_f1"] - subset.loc[clean, "macro_f1"],
                        "balanced_accuracy_clean": subset.loc[clean, "balanced_accuracy"],
                        "balanced_accuracy_disrupted": subset.loc[disrupted, "balanced_accuracy"],
                        "delta_balanced_accuracy": subset.loc[disrupted, "balanced_accuracy"] - subset.loc[clean, "balanced_accuracy"],
                        "macro_pr_auc_clean": subset.loc[clean, "macro_pr_auc_ovr"],
                        "macro_pr_auc_disrupted": subset.loc[disrupted, "macro_pr_auc_ovr"],
                        "delta_macro_pr_auc": subset.loc[disrupted, "macro_pr_auc_ovr"] - subset.loc[clean, "macro_pr_auc_ovr"],
                    }
                )
    return pd.DataFrame(rows).convert_dtypes()


def _markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    if frame.empty:
        return "_empty_"
    selected = [column for column in columns if column in frame.columns]
    view = frame.loc[:, selected].copy()
    for column in view.columns:
        if pd.api.types.is_numeric_dtype(view[column]):
            view[column] = view[column].map(lambda value: "" if pd.isna(value) else f"{float(value):.4f}")
        else:
            view[column] = view[column].astype("string").fillna("")
    headers = [str(value) for value in view.columns]
    rows = [headers] + [[str(value) for value in row] for row in view.itertuples(index=False, name=None)]
    widths = [max(len(row[index]) for row in rows) for index in range(len(headers))]
    format_row = lambda row: "| " + " | ".join(value.ljust(widths[index]) for index, value in enumerate(row)) + " |"
    return "\n".join(
        [format_row(headers), "| " + " | ".join("-" * width for width in widths) + " |"]
        + [format_row(row) for row in rows[1:]]
    )
