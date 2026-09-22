from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def write_semantic_outputs(
    *,
    output_dir: Path,
    run_manifest: dict[str, object],
    target_frame: pd.DataFrame,
    metrics: pd.DataFrame,
    per_class: pd.DataFrame,
    confusion: pd.DataFrame,
    predictions: pd.DataFrame,
    strata: pd.DataFrame,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    distributions = _label_distributions(target_frame)
    target_frame.to_parquet(output_dir / "target_semantics_frame.parquet", index=False)
    distributions.to_csv(output_dir / "label_distribution.csv", index=False)
    metrics.to_csv(output_dir / "training_metrics.csv", index=False)
    per_class.to_csv(output_dir / "per_class_metrics.csv", index=False)
    confusion.to_csv(output_dir / "confusion_matrix.csv", index=False)
    predictions.to_parquet(output_dir / "heldout_predictions.parquet", index=False)
    strata.to_csv(output_dir / "stratum_metrics.csv", index=False)
    (output_dir / "feature_contract.json").write_text(
        json.dumps(
            {
                "future_forbidden_in_features": run_manifest.get("future_forbidden_in_features"),
                "support_depth_forbidden_in_features": run_manifest.get("support_depth_forbidden_in_features"),
                "eventual_run_length_forbidden_in_features": run_manifest.get("eventual_run_length_forbidden_in_features"),
                "feature_bundles": run_manifest.get("feature_bundles"),
            },
            ensure_ascii=True,
            indent=2,
        ),
        encoding="utf-8",
    )
    (output_dir / "run_manifest.json").write_text(json.dumps(run_manifest, ensure_ascii=True, indent=2, allow_nan=True), encoding="utf-8")
    (output_dir / "report.md").write_text(
        _build_report(run_manifest=run_manifest, distributions=distributions, metrics=metrics, strata=strata),
        encoding="utf-8",
    )


def _label_distributions(target_frame: pd.DataFrame) -> pd.DataFrame:
    trainable = target_frame["final_trainability"].fillna(False).astype(bool)
    rows: list[dict[str, object]] = []
    for target_view_id, label_column in (("temporal_online_3h", "label_online"), ("temporal_event_3h", "label_event")):
        for scope, mask in (
            ("eligible_pool", trainable),
            ("train", trainable & target_frame["partition"].astype("string").eq("train")),
            ("validation", trainable & target_frame["partition"].astype("string").eq("validation")),
            ("test", trainable & target_frame["partition"].astype("string").eq("test")),
        ):
            selected = target_frame.loc[mask, label_column].astype("string")
            for label_name, count in selected.value_counts(dropna=False).items():
                rows.append({
                    "target_view_id": target_view_id,
                    "scope": scope,
                    "label_name": str(label_name),
                    "count": int(count),
                    "share_pct": 100.0 * int(count) / len(selected) if len(selected) else float("nan"),
                    "scope_total": int(len(selected)),
                })
    return pd.DataFrame(rows).convert_dtypes()


def _build_report(*, run_manifest: dict[str, object], distributions: pd.DataFrame, metrics: pd.DataFrame, strata: pd.DataFrame) -> str:
    lines = [
        "# K>1 causal-history and online/event semantic benchmark",
        "",
        f"- run_id: `{run_manifest['run_id']}`",
        f"- model: `{run_manifest['model_key']}`",
        f"- fold/seed: `{run_manifest['fold_policy']}` / `{run_manifest['random_seed']}`",
        "- K: `3`",
        "",
        "## Corrected feature contract",
        "",
        "The history-enriched representation contains the existing causal 3h aggregate features plus strictly-past ordered sensor lags and history-quality features. It does not contain support depth, eventual run length, point labels, U_K_succ/U_K_fail, or future rows.",
        "",
        "`Y_online` and `Y_event` are trained as separate target views on the same causal feature matrix. `Y_event` is retrospective and is not a deployable target.",
        "",
        "## Label distributions",
        "",
        _markdown_table(distributions.loc[distributions["scope"].eq("eligible_pool")], ["target_view_id", "label_name", "count", "share_pct"]),
        "",
        "## Aligned held-out metrics",
        "",
        _markdown_table(metrics.loc[metrics["partition"].eq("test")], ["variant_id", "target_view_id", "feature_count", "evaluation_count", "balanced_accuracy", "macro_f1", "weighted_f1", "macro_pr_auc_ovr", "low_recall", "unres_recall", "ref_recall"]),
        "",
        "## K-state test decomposition",
        "",
        "`U_K_succ` and `U_K_fail` share the online label UNRES at d<3. Their eventual outcome is retained only for post-hoc stratification.",
        "",
        _markdown_table(
            strata.loc[
                strata["partition"].eq("test")
                & strata["provenance_stratum"].isin(["LOW", "U_K_succ", "U_K_fail"])
            ],
            ["variant_id", "target_view_id", "provenance_stratum", "depth_bin", "prediction_rows", "hard_low_rate", "mean_p_low", "online_accuracy", "event_accuracy"],
        ),
        "",
        "## Interpretation and limitations",
        "",
        "- The primary comparison is history-enriched online versus history-enriched event; snapshot variants are baselines.",
        "- A higher LOW probability for U_K_succ than U_K_fail is an observational early-persistence signal, not causal proof.",
        "- d>=3 is a gate-confirmation state by construction and must not be counted as independent early-warning evidence.",
        "- The run uses one Fold 01/seed and weak labels; repeated folds/seeds and independent agronomic ground truth remain required.",
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
