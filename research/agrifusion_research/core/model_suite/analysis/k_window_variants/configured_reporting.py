from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .configured_runner import ConfiguredVariant


def write_configured_outputs(
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
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    distribution = _build_label_distribution(target_frame=target_frame, variants=variants)
    target_frame.to_parquet(output_dir / "target_configured_frame.parquet", index=False)
    distribution.to_csv(output_dir / "label_distribution.csv", index=False)
    metrics.to_csv(output_dir / "training_metrics.csv", index=False)
    per_class.to_csv(output_dir / "per_class_metrics.csv", index=False)
    confusion.to_csv(output_dir / "confusion_matrix.csv", index=False)
    predictions.to_parquet(output_dir / "heldout_predictions.parquet", index=False)
    strata.to_csv(output_dir / "stratum_metrics.csv", index=False)
    (output_dir / "feature_contract.json").write_text(
        json.dumps(run_manifest["representation_contract"], ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
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
            strata=strata,
        ),
        encoding="utf-8",
    )


def _build_label_distribution(*, target_frame: pd.DataFrame, variants: tuple[ConfiguredVariant, ...]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for variant in variants:
        trainable = target_frame["final_trainability"].fillna(False).astype(bool)
        selected_label = target_frame[variant.label_column].astype("string")
        for scope, mask in (
            ("eligible_pool", trainable),
            ("train", trainable & target_frame["partition"].astype("string").eq("train")),
            ("validation", trainable & target_frame["partition"].astype("string").eq("validation")),
            ("test", trainable & target_frame["partition"].astype("string").eq("test")),
        ):
            labels = selected_label.loc[mask]
            for label_name, count in labels.value_counts(dropna=False).items():
                rows.append({
                    "variant_id": variant.variant_id,
                    "representation_id": variant.representation_id,
                    "target_view_id": variant.target_view_id,
                    "k": variant.k,
                    "scope": scope,
                    "label_name": str(label_name),
                    "count": int(count),
                    "share_pct": 100.0 * int(count) / len(labels) if len(labels) else float("nan"),
                    "scope_total": int(len(labels)),
                })
    return pd.DataFrame(rows).convert_dtypes()


def _build_report(
    *,
    run_manifest: dict[str, object],
    distribution: pd.DataFrame,
    metrics: pd.DataFrame,
    per_class: pd.DataFrame,
    strata: pd.DataFrame,
) -> str:
    lines = [
        "# Configured R/K benchmark",
        "",
        f"- run_id: `{run_manifest['run_id']}`",
        f"- model: `{run_manifest['model_key']}`",
        f"- fold/seed: `{run_manifest['fold_policy']}` / `{run_manifest['random_seed']}`",
        "",
        "## Experimental schedule",
        "",
        "K=1 runs R00 as the primary snapshot baseline and R11 as the optional control. K=3 runs R00, R10, R01, and R11 separately for the causal online target and the retrospective event target.",
        "",
        _markdown_table(pd.DataFrame(run_manifest["schedule"]), ["variant_id", "target_view_id", "k", "representation_id", "feature_count", "target_semantics"]),
        "",
        "## Representation contract",
        "",
        "R00 = snapshot; R10 = snapshot plus the existing causal 3h summary block; R01 = snapshot plus ordered causal flatten additions; R11 = R10 plus the ordered additions. No support depth, eventual run length, point label, provenance stratum, or future row is a model feature.",
        "",
        _markdown_table(pd.DataFrame(run_manifest["representation_contract"]["representations"]), ["representation_id", "display_name", "feature_count", "summary_count", "ordered_addition_count"]),
        "",
        "## Trainable label counts",
        "",
        _markdown_table(distribution.loc[distribution["scope"].eq("eligible_pool")], ["variant_id", "target_view_id", "k", "representation_id", "label_name", "count", "share_pct"]),
        "",
        "## Held-out imbalance-aware metrics",
        "",
        _markdown_table(metrics.loc[metrics["partition"].eq("test")], ["variant_id", "target_view_id", "k", "representation_id", "feature_count", "evaluation_count", "balanced_accuracy", "macro_f1", "weighted_f1", "macro_pr_auc_ovr", "low_recall", "unres_recall", "ref_recall"]),
        "",
        "## K>1 provenance decomposition",
        "",
        "`U_K_succ` and `U_K_fail` are reported only as post-hoc strata. They are not model labels or features.",
        "",
        _markdown_table(
            strata.loc[
                strata["partition"].eq("test")
                & strata["provenance_stratum"].isin(["LOW", "U_K_succ", "U_K_fail"])
            ] if not strata.empty else strata,
            ["variant_id", "target_view_id", "representation_id", "provenance_stratum", "depth_bin", "prediction_rows", "hard_low_rate", "mean_p_low", "online_accuracy", "event_accuracy"],
        ),
        "",
        "## Interpretation and limitations",
        "",
        "- The representation contrast is controlled within each target view and Fold 01/seed.",
        "- K1 is additive analysis-only; native Q10-K3 artifacts are unchanged.",
        "- Y_online is causal current-state recognition. Y_event is retrospective and non-deployable.",
        "- One fold/seed, weak labels, and small U_K strata do not support generalization or agronomic-validity claims.",
    ]
    if not per_class.empty:
        lines.extend([
            "",
            "## Per-class test metrics",
            "",
            _markdown_table(per_class.loc[per_class["partition"].eq("test")], ["variant_id", "target_view_id", "representation_id", "k", "class_name", "precision", "recall", "f1_score", "support"]),
        ])
    return "\n".join(lines) + "\n"


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
    rows = [headers] + [[str(value) for value in row] for row in view.itertuples(index=False, name=None)]
    widths = [max(len(row[index]) for row in rows) for index in range(len(headers))]
    format_row = lambda row: "| " + " | ".join(value.ljust(widths[index]) for index, value in enumerate(row)) + " |"
    return "\n".join(
        [format_row(headers), "| " + " | ".join("-" * width for width in widths) + " |"]
        + [format_row(row) for row in rows[1:]]
    )
