from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .runner import VariantDefinition


def write_analysis_outputs(
    *,
    output_dir: Path,
    run_manifest: dict[str, object],
    target_frame: pd.DataFrame,
    variants: tuple[VariantDefinition, ...],
    metrics: pd.DataFrame,
    per_class: pd.DataFrame,
    confusion: pd.DataFrame,
    predictions: pd.DataFrame,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    distribution = _build_label_distribution(target_frame=target_frame, variants=variants)
    target_frame.to_parquet(output_dir / "target_variant_frame.parquet", index=False)
    distribution.to_csv(output_dir / "label_distribution.csv", index=False)
    metrics.to_csv(output_dir / "training_metrics.csv", index=False)
    per_class.to_csv(output_dir / "per_class_metrics.csv", index=False)
    confusion.to_csv(output_dir / "confusion_matrix.csv", index=False)
    predictions.to_parquet(output_dir / "heldout_predictions.parquet", index=False)
    (output_dir / "run_manifest.json").write_text(
        json.dumps(run_manifest, ensure_ascii=True, indent=2, allow_nan=True),
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(
        _build_report(
            run_manifest=run_manifest,
            distribution=distribution,
            metrics=metrics,
            per_class=per_class,
        ),
        encoding="utf-8",
    )


def _build_label_distribution(*, target_frame: pd.DataFrame, variants: tuple[VariantDefinition, ...]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for variant in variants:
        labels = target_frame[variant.label_column].astype("string")
        for scope in ("all_rows", "eligible_pool", "train", "validation", "test"):
            if scope == "all_rows":
                selected = target_frame
            elif scope == "eligible_pool":
                selected = target_frame.loc[target_frame["final_trainability"].fillna(False).astype(bool)]
            else:
                selected = target_frame.loc[
                    target_frame["final_trainability"].fillna(False).astype(bool)
                    & target_frame["partition"].astype("string").eq(scope)
                ]
            counts = labels.loc[selected.index].value_counts(dropna=False)
            total = int(len(selected))
            for label_name, count in counts.items():
                rows.append(
                    {
                        "variant_id": variant.variant_id,
                        "representation": variant.representation,
                        "k": variant.k,
                        "scope": scope,
                        "label_name": str(label_name),
                        "count": int(count),
                        "share_pct": (100.0 * int(count) / total) if total else float("nan"),
                        "scope_total": total,
                    }
                )
    return pd.DataFrame(rows).convert_dtypes()


def _build_report(*, run_manifest: dict[str, object], distribution: pd.DataFrame, metrics: pd.DataFrame, per_class: pd.DataFrame) -> str:
    lines = [
        "# Four-way full-9 / 3h-window × K benchmark",
        "",
        f"- run_id: `{run_manifest['run_id']}`",
        f"- target semantics: `{run_manifest['target_semantics']}`",
        f"- model: `{run_manifest['model_key']}`",
        f"- fold/seed: `{run_manifest['fold_policy']}` / `{run_manifest['random_seed']}`",
        "",
        "## Interpretation",
        "",
        "K is the temporal persistence threshold. Both representations use the same temporal-3h target and the same protocol partitions; only the feature representation and K-derived labels differ. K1 is an additive analysis target and does not replace the native Q10-K3 release.",
        "",
        "## Variant matrix",
        "",
        "| Variant | Representation | K | Feature count |",
        "|---|---|---:|---:|",
        "| snapshot_9_k1 | 9 current attributes | 1 | 9 |",
        "| snapshot_9_k3 | 9 current attributes | 3 | 9 |",
        "| window_3h_9_k1 | 9 current attributes + causal 3h stats | 1 | 54 |",
        "| window_3h_9_k3 | 9 current attributes + causal 3h stats | 3 | 54 |",
        "",
        "## Trainable label counts",
        "",
    ]
    trainable = distribution.loc[distribution["scope"].eq("eligible_pool")].copy()
    lines.append(_markdown_table(trainable, ["variant_id", "k", "label_name", "count", "share_pct"]))
    lines.extend(["", "## Held-out imbalance-aware metrics", ""])
    test_metrics = metrics.loc[metrics["partition"].eq("test")].copy()
    lines.append(_markdown_table(test_metrics, [
        "variant_id", "k", "feature_count", "evaluation_count", "balanced_accuracy",
        "macro_f1", "weighted_f1", "macro_pr_auc_ovr", "low_recall", "unres_recall", "ref_recall",
    ]))
    lines.extend(["", "Accuracy is retained only as a secondary reference. The primary reading is balanced accuracy, macro-F1, macro one-vs-rest PR-AUC, and per-class recall, especially LOW and UNRES.", "", "## Validation and limitations", "", "- K3 derivation was checked against the existing temporal protocol on all trainable rows.", "- Feature artifacts and native labels were read without mutation.", "- The first run uses the current Fold 01 / one-seed protocol and is diagnostic, not a multi-fold generalization result.", "- Independent agronomic ground truth is not established by this benchmark.", ""])
    if not per_class.empty:
        lines.extend(["## Per-class test metrics", "", _markdown_table(per_class.loc[per_class["partition"].eq("test")], ["variant_id", "k", "class_name", "precision", "recall", "f1_score", "support"]), ""])
    return "\n".join(lines)


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
