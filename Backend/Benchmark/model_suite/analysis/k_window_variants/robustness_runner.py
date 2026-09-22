from __future__ import annotations

from pathlib import Path

import pandas as pd

from .configured_runner import ConfiguredVariant, run_configured_variants
from .representations import RepresentationBundle
from .runner import REPORT_LABELS


AUDIT_REPRESENTATIONS = (
    "R01",
    "R_pure_lag",
    "R_meta",
    "R_pure_lag_disrupted",
    "R01_disrupted",
)


def build_audit_variants(
    *,
    representations: dict[str, RepresentationBundle],
    representation_ids: tuple[str, ...] = AUDIT_REPRESENTATIONS,
) -> tuple[ConfiguredVariant, ...]:
    variants: list[ConfiguredVariant] = []
    for target_view_id, label_column, semantics in (
        ("temporal_online_3h", "label_online", "K3_ONLINE_CAUSAL"),
        ("temporal_event_3h", "label_event", "K3_EVENT_RETROSPECTIVE"),
    ):
        for representation_id in representation_ids:
            representation = representations[representation_id]
            variants.append(
                ConfiguredVariant(
                    variant_id=f"audit_{target_view_id.removeprefix('temporal_')}_{representation_id}",
                    representation_id=representation_id,
                    target_view_id=target_view_id,
                    target_semantics=semantics,
                    k=3,
                    label_column=label_column,
                    representation=representation,
                )
            )
    return tuple(variants)


def run_single_fold_audit(
    *,
    variants: tuple[ConfiguredVariant, ...],
    target_frame: pd.DataFrame,
    output_dir: Path,
    random_seed: int,
    thread_count: int,
) -> dict[str, pd.DataFrame]:
    metrics, per_class, confusion, predictions, strata = run_configured_variants(
        variants=variants,
        target_frame=target_frame,
        output_dir=output_dir,
        random_seed=random_seed,
        thread_count=thread_count,
    )
    return {
        "metrics": metrics,
        "per_class": per_class,
        "confusion": confusion,
        "predictions": predictions,
        "strata": strata,
    }


def build_temporal_fold_frames(
    *,
    target_frame: pd.DataFrame,
    assignment_path: Path,
    view_id: str,
    fold_ids: tuple[str, ...],
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, dict[str, dict[str, object]]]:
    """Apply protocol-owned effective 5-day assignments to semantic labels."""

    assignments = pd.read_parquet(assignment_path)
    assignments = assignments.loc[
        assignments["view_id"].astype("string").eq(view_id)
        & assignments["fold_id"].astype("string").isin(fold_ids)
        & assignments["eligibility_status"].astype("string").eq("eligible")
    ].copy()
    assignments = assignments.loc[:, ["sample_id", "fold_id", "effective_partition"]]
    if assignments.duplicated(["fold_id", "sample_id"]).any():
        raise ValueError("Selected temporal fold assignments must be unique by sample_id within each fold.")
    frames: dict[str, pd.DataFrame] = {}
    support_rows: list[dict[str, object]] = []
    for fold_id in fold_ids:
        fold_assignments = assignments.loc[assignments["fold_id"].astype("string").eq(fold_id)].copy()
        joined = fold_assignments.merge(target_frame, on="sample_id", how="inner", validate="one_to_one")
        if len(joined) != len(fold_assignments):
            raise ValueError(f"Semantic target frame does not cover temporal assignments for {fold_id}.")
        joined["partition"] = joined["effective_partition"].astype("string")
        joined["final_trainability"] = True
        joined["fold_id"] = fold_id
        joined = joined.drop(columns=["effective_partition"])
        for partition in ("train", "validation", "test"):
            subset = joined.loc[joined["partition"].eq(partition)]
            for label_column in ("label_online", "label_event"):
                counts = subset[label_column].astype("string").value_counts(dropna=False)
                for label_name in REPORT_LABELS:
                    support_rows.append(
                        {
                            "fold_id": fold_id,
                            "partition": partition,
                            "target": label_column,
                            "label_name": label_name,
                            "count": int(counts.get(label_name, 0)),
                            "fold_row_count": len(subset),
                        }
                    )
        frames[fold_id] = joined.convert_dtypes()
    return frames, pd.DataFrame(support_rows).convert_dtypes(), _fold_statuses(assignment_path, fold_ids)


def run_temporal_cv(
    *,
    variants: tuple[ConfiguredVariant, ...],
    fold_frames: dict[str, pd.DataFrame],
    output_dir: Path,
    random_seed: int,
    thread_count: int,
) -> dict[str, pd.DataFrame]:
    metric_frames: list[pd.DataFrame] = []
    per_class_frames: list[pd.DataFrame] = []
    confusion_frames: list[pd.DataFrame] = []
    prediction_frames: list[pd.DataFrame] = []
    strata_frames: list[pd.DataFrame] = []
    for fold_id, target_frame in fold_frames.items():
        result = run_single_fold_audit(
            variants=variants,
            target_frame=target_frame,
            output_dir=output_dir / fold_id,
            random_seed=random_seed,
            thread_count=thread_count,
        )
        for key, destination in (
            ("metrics", metric_frames),
            ("per_class", per_class_frames),
            ("confusion", confusion_frames),
            ("predictions", prediction_frames),
            ("strata", strata_frames),
        ):
            frame = result[key].copy()
            if not frame.empty:
                frame.insert(0, "fold_id", fold_id)
            destination.append(frame)
    return {
        "metrics": _concat(metric_frames),
        "per_class": _concat(per_class_frames),
        "confusion": _concat(confusion_frames),
        "predictions": _concat(prediction_frames),
        "strata": _concat(strata_frames),
    }


def summarize_cv_metrics(metrics: pd.DataFrame) -> pd.DataFrame:
    if metrics.empty:
        return pd.DataFrame()
    grouped = (
        metrics.groupby(["variant_id", "target_view_id", "representation_id", "partition"], sort=True)
        .agg(
            fold_count=("fold_id", "nunique"),
            evaluation_count_mean=("evaluation_count", "mean"),
            balanced_accuracy_mean=("balanced_accuracy", "mean"),
            balanced_accuracy_std=("balanced_accuracy", "std"),
            macro_f1_mean=("macro_f1", "mean"),
            macro_f1_std=("macro_f1", "std"),
            weighted_f1_mean=("weighted_f1", "mean"),
            weighted_f1_std=("weighted_f1", "std"),
            macro_pr_auc_mean=("macro_pr_auc_ovr", "mean"),
            macro_pr_auc_std=("macro_pr_auc_ovr", "std"),
            low_recall_mean=("low_recall", "mean"),
            low_recall_std=("low_recall", "std"),
            unres_recall_mean=("unres_recall", "mean"),
            unres_recall_std=("unres_recall", "std"),
            ref_recall_mean=("ref_recall", "mean"),
            ref_recall_std=("ref_recall", "std"),
        )
        .reset_index()
    )
    return grouped.convert_dtypes()


def _concat(frames: list[pd.DataFrame]) -> pd.DataFrame:
    nonempty = [frame for frame in frames if not frame.empty]
    if not nonempty:
        return pd.DataFrame()
    return pd.concat(nonempty, ignore_index=True).convert_dtypes()


def _fold_statuses(assignment_path: Path, fold_ids: tuple[str, ...]) -> dict[str, dict[str, object]]:
    manifest = pd.read_csv(assignment_path.parent / "fold_manifest.csv")
    result: dict[str, dict[str, object]] = {}
    for fold_id in fold_ids:
        rows = manifest.loc[manifest["fold_id"].astype("string").eq(fold_id)]
        result[fold_id] = {
            "fold_status": ";".join(sorted(rows["fold_status"].astype("string").unique().tolist())),
            "primary_benchmark_eligible": bool(rows["primary_benchmark_eligible"].astype(bool).all()),
            "stress_analysis_eligible": bool(rows["stress_analysis_eligible"].astype(bool).all()),
            "status_reason": ";".join(sorted(rows["status_reason"].astype("string").unique().tolist())),
        }
    return result
