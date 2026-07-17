from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def write_benchmark_readiness_report(
    *,
    protocol_run_dir: Path,
    full_output_dir: Path,
    readiness_report: dict[str, object],
) -> Path:
    run_metadata_dir = protocol_run_dir / "run_metadata"
    report_path = run_metadata_dir / "benchmark_readiness_report.md"
    validation_payload = _load_json(run_metadata_dir / "protocol_validation_report.json")
    pooled_metrics = _load_csv(full_output_dir / "pooled_oof_metrics.csv")
    fold_manifest = _load_csv(protocol_run_dir / "primary_protocol" / "folds" / "fold_manifest.csv")
    v2_coverage = _load_csv(protocol_run_dir / "temporal_diagnostics" / "v2_coverage" / "v2_coverage_range_summary.csv")

    status = "READY_FOR_FULL_BENCHMARK" if bool(readiness_report.get("ready_for_full_benchmark")) else "NOT_READY_FOR_FULL_BENCHMARK"
    threshold_value = validation_payload.get("primary_threshold_value_q10", "UNKNOWN")
    selected_folds = validation_payload.get("primary_protocol", {}).get("selected_fold_ids", [])

    lines = [
        "# Benchmark Readiness Report",
        "",
        f"- Status: `{status}`",
        f"- Protocol run: `{protocol_run_dir.name}`",
        f"- Primary threshold: frozen `q10 = {threshold_value}` from initial P1 train",
        f"- Primary folds: `{', '.join(str(fold) for fold in selected_folds)}`",
        "- P2 policy: untouched target holdout with no train or validation assignment",
        "",
        "## Scope",
        "",
        "- Benchmark-ready scope in this run: `V0`, `V1`, `V2 same-Y 3h`, `V2 same-Y 8h`.",
        "- `V6` is explicitly deferred and excluded from the current benchmark-ready conclusion.",
        "",
        "## Key Diagnostics",
        "",
    ]

    fold_note = _build_fold_note(fold_manifest)
    if fold_note is not None:
        lines.append(f"- {fold_note}")

    for line in _build_v2_coverage_notes(v2_coverage):
        lines.append(f"- {line}")

    lines.extend(
        [
            "",
            "## Primary Test Metrics",
            "",
        ]
    )
    lines.extend(_build_metric_table(pooled_metrics))
    lines.extend(
        [
            "",
            "## Authoritative Outputs",
            "",
            f"- Protocol gate summary: `{run_metadata_dir / 'protocol_validation_report.json'}`",
            f"- Runner manifest for task training: `{protocol_run_dir / 'primary_protocol' / 'runner' / 'task_training_manifest.parquet'}`",
            f"- Runner manifest for matched comparisons: `{protocol_run_dir / 'primary_protocol' / 'runner' / 'comparison_training_manifest.parquet'}`",
            f"- Full benchmark validation: `{full_output_dir / 'full_training_validation.csv'}`",
            f"- Full benchmark pooled metrics: `{full_output_dir / 'pooled_oof_metrics.csv'}`",
            f"- V2 coverage diagnostic: `{protocol_run_dir / 'temporal_diagnostics' / 'v2_coverage' / 'v2_coverage_report.md'}`",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def _build_fold_note(fold_manifest: pd.DataFrame) -> str | None:
    if fold_manifest.empty or "unsupported_class_reporting_required" not in fold_manifest.columns:
        return None
    mask = (
        fold_manifest["partition"].astype("string").eq("test")
        & fold_manifest["unsupported_class_reporting_required"].astype(bool)
    )
    flagged = fold_manifest.loc[mask].copy()
    if flagged.empty:
        return "All primary test partitions have full class support with no unsupported-class override."
    first_row = flagged.iloc[0]
    views = json.loads(str(first_row.get("unsupported_views_json", "[]")))
    return (
        f"{first_row['fold_id']} test stays in the primary benchmark with unsupported-class reporting "
        f"for {', '.join(str(view) for view in views)}."
    )


def _build_v2_coverage_notes(v2_coverage: pd.DataFrame) -> list[str]:
    if v2_coverage.empty:
        return ["V2 coverage diagnostic was not available."]
    notes: list[str] = []
    for range_name in ("P1_LATE_CHAIN", "P2_TARGET_DEPLOYMENT"):
        subset = v2_coverage.loc[v2_coverage["range_name"].astype("string") == range_name].copy()
        if subset.empty:
            continue
        row_3h = subset.loc[subset["window_horizon_name"].astype("string") == "3h"].iloc[0]
        row_8h = subset.loc[subset["window_horizon_name"].astype("string") == "8h"].iloc[0]
        notes.append(
            (
                f"{range_name}: 3h eligible {int(row_3h['eligible_count'])}/{int(row_3h['row_count'])} "
                f"({float(row_3h['eligible_ratio']):.3f}) versus 8h {int(row_8h['eligible_count'])}/{int(row_8h['row_count'])} "
                f"({float(row_8h['eligible_ratio']):.3f}); the dominant extra loss is `insufficient_history` "
                f"({int(row_3h['insufficient_history_count'])} -> {int(row_8h['insufficient_history_count'])})."
            )
        )
    return notes


def _build_metric_table(pooled_metrics: pd.DataFrame) -> list[str]:
    if pooled_metrics.empty:
        return ["No pooled metric output was generated."]
    task_rows = pooled_metrics.loc[
        (pooled_metrics["stage_id"].astype("string") == "primary_task_matrix")
        & (pooled_metrics["partition"].astype("string") == "test")
    ].copy()
    if task_rows.empty:
        return ["No primary task test metrics were generated."]
    task_rows = task_rows.sort_values("feature_view_id", kind="stable")
    lines = [
        "| Feature view | Rows | Accuracy | Supported macro F1 | Balanced accuracy |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in task_rows.itertuples(index=False):
        lines.append(
            "| "
            f"{row.feature_view_id} | "
            f"{int(row.pooled_row_count)} | "
            f"{float(row.accuracy):.4f} | "
            f"{float(row.supported_class_macro_f1):.4f} | "
            f"{float(row.supported_class_balanced_accuracy):.4f} |"
        )
    return lines


def _load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame().convert_dtypes()
    return pd.read_csv(path).convert_dtypes()


def _load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
