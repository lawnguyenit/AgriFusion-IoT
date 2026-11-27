from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def write_embedding_outputs(
    *,
    output_dir: Path,
    run_manifest: dict[str, object],
    metrics: pd.DataFrame,
    per_class: pd.DataFrame,
    confusion: pd.DataFrame,
    predictions: pd.DataFrame,
    strata: pd.DataFrame,
    embeddings: pd.DataFrame,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(output_dir / "training_metrics.csv", index=False)
    per_class.to_csv(output_dir / "per_class_metrics.csv", index=False)
    confusion.to_csv(output_dir / "confusion_matrix.csv", index=False)
    predictions.to_parquet(output_dir / "heldout_predictions.parquet", index=False)
    strata.to_csv(output_dir / "stratum_metrics.csv", index=False)
    embeddings.to_parquet(output_dir / "embeddings.parquet", index=False)
    (output_dir / "run_manifest.json").write_text(json.dumps(run_manifest, ensure_ascii=True, indent=2, allow_nan=True), encoding="utf-8")
    (output_dir / "report.md").write_text(
        _build_report(run_manifest=run_manifest, metrics=metrics, strata=strata),
        encoding="utf-8",
    )


def _build_report(*, run_manifest: dict[str, object], metrics: pd.DataFrame, strata: pd.DataFrame) -> str:
    test_metrics = metrics.loc[metrics["partition"].eq("test")].copy()
    test_strata = strata.loc[
        strata["partition"].eq("test") & strata["provenance_stratum"].isin(["LOW", "U_K_succ", "U_K_fail"])
    ].copy()
    lines = [
        "# Causal sequence embedding to XGBoost benchmark",
        "",
        f"- run_id: `{run_manifest['run_id']}`",
        f"- sequence length: `{run_manifest['sequence_length']}`",
        f"- embedding size: `{run_manifest['embedding_size']}`",
        f"- fold/seed: `{run_manifest['fold_policy']}` / `{run_manifest['random_seed']}`",
        "",
        "## Representation",
        "",
        "The GRU consumes a fixed-length causal sequence ending at the anchor. It uses only sensor values at or before t, train-only normalization, missing-value indicators, row-presence masks, and lag ages. The frozen GRU hidden state is then used as a fixed-size embedding for XGBoost.",
        "",
        "No support depth, eventual run length, point label, provenance stratum, or future row is part of the sequence input.",
        "",
        "## Held-out embedding-to-XGBoost metrics",
        "",
        _markdown_table(test_metrics, ["variant_id", "target_view_id", "feature_count", "balanced_accuracy", "macro_f1", "weighted_f1", "macro_pr_auc_ovr", "low_recall", "unres_recall", "ref_recall", "encoder_best_epoch", "encoder_best_validation_macro_f1"]),
        "",
        "## U_K_succ / U_K_fail decomposition",
        "",
        _markdown_table(test_strata, ["variant_id", "target_view_id", "provenance_stratum", "depth_bin", "prediction_rows", "hard_low_rate", "mean_p_low", "online_accuracy", "event_accuracy"]),
        "",
        "## Interpretation",
        "",
        "The embedding experiment is a representation probe, not a new native benchmark release. The encoder is fit on train only and the XGBoost stage sees only frozen embeddings. Results must be compared with the 9-feature and 179-feature baselines using the same Fold 01/seed protocol.",
        "",
        "One fold/seed, weak labels, and small U_K cells remain insufficient for a generalization or agronomic-validity claim.",
    ]
    return "\n".join(lines) + "\n"


def _markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    if frame.empty:
        return "_empty_"
    view = frame.loc[:, [column for column in columns if column in frame.columns]].copy()
    for column in view.columns:
        if pd.api.types.is_float_dtype(view[column]):
            view[column] = view[column].map(lambda value: "" if pd.isna(value) else f"{float(value):.4f}")
        else:
            view[column] = view[column].astype("string").fillna("")
    headers = [str(value) for value in view.columns]
    rows = [headers] + [[str(value) for value in row] for row in view.itertuples(index=False, name=None)]
    widths = [max(len(row[index]) for row in rows) for index in range(len(headers))]
    format_row = lambda row: "| " + " | ".join(value.ljust(widths[index]) for index, value in enumerate(row)) + " |"
    return "\n".join([format_row(headers), "| " + " | ".join("-" * width for width in widths) + " |"] + [format_row(row) for row in rows[1:]])
