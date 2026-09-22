from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .configured_runner import ConfiguredVariant


def write_ordered_outputs(
    *,
    output_dir: Path,
    run_manifest: dict[str, object],
    target_frame: pd.DataFrame,
    variants: tuple[ConfiguredVariant, ...],
    metrics: pd.DataFrame,
    per_class: pd.DataFrame,
    confusion: pd.DataFrame,
    predictions: pd.DataFrame,
    strata: pd.DataFrame,
    oracle_rows: pd.DataFrame,
    oracle_summary: pd.DataFrame,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    distribution = _build_label_distribution(target_frame, variants)
    target_frame.to_parquet(output_dir / "target_ordered_frame.parquet", index=False)
    distribution.to_csv(output_dir / "label_distribution.csv", index=False)
    metrics.to_csv(output_dir / "training_metrics.csv", index=False)
    per_class.to_csv(output_dir / "per_class_metrics.csv", index=False)
    confusion.to_csv(output_dir / "confusion_matrix.csv", index=False)
    predictions.to_parquet(output_dir / "heldout_predictions.parquet", index=False)
    strata.to_csv(output_dir / "stratum_metrics.csv", index=False)
    oracle_rows.to_parquet(output_dir / "oracle_rows.parquet", index=False)
    oracle_summary.to_csv(output_dir / "oracle_summary.csv", index=False)
    (output_dir / "representation_contract.json").write_text(
        json.dumps(run_manifest["representation_contract"], ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    (output_dir / "run_manifest.json").write_text(
        json.dumps(run_manifest, ensure_ascii=True, indent=2, allow_nan=True),
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(
        _build_report(run_manifest, distribution, metrics, per_class, oracle_summary),
        encoding="utf-8",
    )


def _build_label_distribution(target_frame: pd.DataFrame, variants: tuple[ConfiguredVariant, ...]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for variant in variants:
        trainable = target_frame["final_trainability"].fillna(False).astype(bool)
        labels = target_frame[variant.label_column].astype("string")
        for scope, mask in (
            ("eligible_pool", trainable),
            ("train", trainable & target_frame["partition"].astype("string").eq("train")),
            ("validation", trainable & target_frame["partition"].astype("string").eq("validation")),
            ("test", trainable & target_frame["partition"].astype("string").eq("test")),
        ):
            selected = labels.loc[mask]
            for label_name, count in selected.value_counts(dropna=False).items():
                rows.append(
                    {
                        "sequence_order": _sequence_order(variant.representation_id),
                        "representation_id": variant.representation_id,
                        "target_view_id": variant.target_view_id,
                        "k": variant.k,
                        "scope": scope,
                        "label_name": str(label_name),
                        "count": int(count),
                        "share_pct": 100.0 * int(count) / len(selected) if len(selected) else float("nan"),
                        "scope_total": int(len(selected)),
                    }
                )
    return pd.DataFrame(rows).convert_dtypes()


def _build_report(
    run_manifest: dict[str, object],
    distribution: pd.DataFrame,
    metrics: pd.DataFrame,
    per_class: pd.DataFrame,
    oracle_summary: pd.DataFrame,
) -> str:
    test_metrics = metrics.loc[metrics["partition"].astype("string").eq("test")].copy()
    test_metrics["sequence_order"] = test_metrics["representation_id"].map(_sequence_order)
    test_metrics = test_metrics.sort_values(["target_view_id", "sequence_order"])
    label_rows = distribution.loc[distribution["scope"].eq("eligible_pool")].copy()
    label_rows["sequence_order"] = label_rows["representation_id"].map(_sequence_order)
    label_rows = label_rows.sort_values(["target_view_id", "sequence_order", "label_name"])
    lines = [
        "# Ordered representation progression",
        "",
        f"- run_id: `{run_manifest['run_id']}`",
        f"- model: `{run_manifest['model_key']}`",
        f"- fold/seed: `{run_manifest['fold_policy']}` / `{run_manifest['random_seed']}`",
        "",
        "## Requested order",
        "",
        "`Oracle → M_t → X_t → M-history → X-history → X-history+context`",
        "",
        "Oracle is a deterministic positive control. The five following steps are XGBoost models trained separately for K3 online and K3 event.",
        "",
        _markdown_table(pd.DataFrame(run_manifest["sequence"]), ["order", "stage", "trainable", "feature_count", "definition"]),
        "",
        "## Label distribution",
        "",
        _markdown_table(label_rows, ["sequence_order", "representation_id", "target_view_id", "label_name", "count", "share_pct", "scope_total"]),
        "",
        "## Held-out test metrics",
        "",
        _markdown_table(
            test_metrics,
            ["sequence_order", "representation_id", "target_view_id", "k", "feature_count", "train_count", "evaluation_count", "balanced_accuracy", "macro_f1", "weighted_f1", "macro_pr_auc_ovr", "low_recall", "unres_recall", "ref_recall"],
        ),
        "",
        "## Oracle control",
        "",
        _markdown_table(oracle_summary, ["oracle", "target", "sample_count", "oracle_positive_count", "target_low_count", "coverage_all_three_finite", "coverage_three_step_causal_within_3h", "precision_low", "recall_low", "f1_low", "balanced_accuracy", "agreement_with_target"]),
        "",
        "## Interpretation constraints",
        "",
        "- `Y_online` is the causal current-state target; `Y_event` is retrospective and non-deployable.",
        "- The new Firebase candidate is not included because its new rows do not yet have an approved matching label release.",
        "- `X-history+context` excludes acquisition/history-quality metadata; it is not the 179-feature all-in representation.",
        "- Results are Fold 01/one-seed diagnostics and do not establish cross-fold or agronomic generalization.",
    ]
    if not per_class.empty:
        lines.extend([
            "",
            "## Per-class test metrics",
            "",
            _markdown_table(
                per_class.loc[per_class["partition"].astype("string").eq("test")].assign(
                    sequence_order=lambda frame: frame["representation_id"].map(_sequence_order)
                ).sort_values(["target_view_id", "sequence_order", "class_name"]),
                ["sequence_order", "representation_id", "target_view_id", "class_name", "precision", "recall", "f1_score", "support"],
            ),
        ])
    return "\n".join(lines) + "\n"


def _sequence_order(value: object) -> int:
    return {
        "Oracle": 1,
        "M_t": 2,
        "X_t": 3,
        "M_history": 4,
        "X_history": 5,
        "X_history_context": 6,
    }.get(str(value), 99)


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
    rows = [[str(value) for value in row] for row in view.itertuples(index=False, name=None)]
    headers = [str(value) for value in view.columns]
    all_rows = [headers, *rows]
    widths = [max(len(row[index]) for row in all_rows) for index in range(len(headers))]
    fmt = lambda row: "| " + " | ".join(value.ljust(widths[index]) for index, value in enumerate(row)) + " |"
    return "\n".join([fmt(headers), "| " + " | ".join("-" * width for width in widths) + " |", *[fmt(row) for row in rows]])
