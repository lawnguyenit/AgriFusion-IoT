from __future__ import annotations

import zlib
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score


def build_temporal_bootstrap_metrics(
    predictions: pd.DataFrame,
    source_labels_path: Path,
    *,
    repetitions: int = 1000,
    seed: int = 20261001,
) -> pd.DataFrame:
    """Estimate per-head intervals by resampling whole UTC calendar-day clusters."""
    if repetitions < 100:
        raise ValueError("Use at least 100 bootstrap repetitions.")
    source = pd.read_parquet(source_labels_path)
    if "timestamp" not in source.columns:
        return pd.DataFrame()
    source = source.loc[:, ["sample_id", "timestamp"]]
    source["sample_id"] = source["sample_id"].astype("string")
    joined = predictions.merge(source, on="sample_id", how="left", validate="many_to_one")
    if joined["timestamp"].isna().any():
        raise ValueError("Some prediction rows do not resolve to source timestamps.")
    joined["_day"] = pd.to_datetime(joined["timestamp"], utc=True).dt.floor("D")
    rows: list[dict[str, object]] = []
    for (fold_id, partition, target), frame in joined.groupby(
        ["fold_id", "partition", "target"], sort=True
    ):
        known = frame["y_true"].notna()
        predictable = (
            frame["prediction_status"].astype("string").ne("MODEL_ABSTAIN_NO_X").fillna(False)
            if "prediction_status" in frame
            else pd.Series(True, index=frame.index)
        )
        frame = frame.loc[known & predictable].copy()
        truth = frame["y_true"].astype(int).to_numpy()
        score = frame["positive_probability"].astype(float).to_numpy()
        day_groups = [g.index.to_numpy() for _, g in frame.groupby("_day", sort=True)]
        if len(frame) and len(day_groups) >= 2:
            rng = np.random.default_rng(_stable_seed(seed, fold_id, partition, target))
            draws: dict[str, list[float]] = {name: [] for name in ("log_loss", "brier_score", "average_precision", "roc_auc")}
            index_groups = [np.searchsorted(frame.index.to_numpy(), group) for group in day_groups]
            for _ in range(repetitions):
                sampled_groups = rng.integers(0, len(index_groups), size=len(index_groups))
                indices = np.concatenate([index_groups[index] for index in sampled_groups])
                y = truth[indices]
                p = score[indices]
                draws["log_loss"].append(float(log_loss(y, p, labels=[0, 1])))
                draws["brier_score"].append(float(brier_score_loss(y, p)))
                if len(np.unique(y)) == 2:
                    draws["average_precision"].append(float(average_precision_score(y, p)))
                    draws["roc_auc"].append(float(roc_auc_score(y, p)))
            point = {
                "log_loss": float(log_loss(truth, score, labels=[0, 1])) if len(truth) else np.nan,
                "brier_score": float(brier_score_loss(truth, score)) if len(truth) else np.nan,
                "average_precision": float(average_precision_score(truth, score)) if len(np.unique(truth)) == 2 else np.nan,
                "roc_auc": float(roc_auc_score(truth, score)) if len(np.unique(truth)) == 2 else np.nan,
            }
            intervals = {
                name: (float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5)))
                if values else (np.nan, np.nan)
                for name, values in draws.items()
            }
            status = "complete"
        else:
            point = {name: np.nan for name in ("log_loss", "brier_score", "average_precision", "roc_auc")}
            intervals = {name: (np.nan, np.nan) for name in point}
            status = "insufficient_temporal_clusters"
            draws = {name: [] for name in point}
        row: dict[str, object] = {
            "fold_id": str(fold_id),
            "partition": str(partition),
            "target": str(target),
            "known_sample_count": int(len(truth)),
            "partition_row_count": int(len(joined.loc[
                joined["fold_id"].eq(fold_id) & joined["partition"].eq(partition) & joined["target"].eq(target)
            ])),
            "target_known_count": int(known.sum()),
            "no_x_abstention_count": int((~predictable).sum()),
            "known_truth_no_x_count": int((known & ~predictable).sum()),
            "positive_prevalence": float((truth == 1).mean()) if len(truth) else pd.NA,
            "temporal_cluster_unit": "UTC_calendar_day",
            "temporal_cluster_count": int(len(day_groups)),
            "bootstrap_repetitions": int(repetitions),
            "bootstrap_status": status,
        }
        for metric, value in point.items():
            row[metric] = value
            row[f"{metric}_ci_low"] = intervals[metric][0]
            row[f"{metric}_ci_high"] = intervals[metric][1]
            row[f"{metric}_valid_bootstrap_repetitions"] = len(draws[metric])
        rows.append(row)
    return pd.DataFrame(rows).convert_dtypes()


def _stable_seed(seed: int, *parts: object) -> int:
    token = "|".join([str(seed), *map(str, parts)])
    return int((seed + zlib.crc32(token.encode("utf-8"))) % (2**32 - 1))
