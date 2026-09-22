from __future__ import annotations

import zlib

import numpy as np
import pandas as pd

from .runner import LOW_LABEL, REF_LABEL, UNRES_LABEL


PR_LABELS = (LOW_LABEL, UNRES_LABEL, REF_LABEL)


def add_temporal_order_columns(predictions: pd.DataFrame, row_index: pd.DataFrame) -> pd.DataFrame:
    lookup = row_index.loc[:, ["record.id", "record.node_id", "record.segment_id", "record.ts_sample"]].copy()
    lookup = lookup.rename(columns={"record.id": "sample_id"})
    lookup["sample_id"] = lookup["sample_id"].astype("string")
    output = predictions.copy()
    output["sample_id"] = output["sample_id"].astype("string")
    output = output.merge(lookup, on="sample_id", how="left", validate="many_to_one")
    if output[["record.node_id", "record.segment_id", "record.ts_sample"]].isna().any().any():
        raise ValueError("RQ1 predictions could not be aligned to temporal row metadata.")
    return output


def build_per_anchor_losses(predictions: pd.DataFrame) -> pd.DataFrame:
    required = {"target_view_id", "partition", "sample_id", "label_true", "p_low", "p_unres", "p_ref"}
    missing = sorted(required.difference(predictions.columns))
    if missing:
        raise ValueError(f"Prediction rows are missing probability fields: {missing}")
    output = predictions.copy()
    probability_columns = ["p_low", "p_unres", "p_ref"]
    probabilities = output.loc[:, probability_columns].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    probabilities = np.nan_to_num(probabilities, nan=1.0 / 3.0, posinf=1.0, neginf=0.0)
    probabilities = np.clip(probabilities, 1e-12, 1.0)
    probabilities = probabilities / probabilities.sum(axis=1, keepdims=True)
    labels = output["label_true"].astype("string").tolist()
    label_indices = {label: index for index, label in enumerate(PR_LABELS)}
    y = np.asarray([label_indices.get(label, -1) for label in labels], dtype=int)
    if (y < 0).any():
        raise ValueError("Per-anchor loss rows contain a label outside the fixed three-class ontology.")
    output["log_loss"] = -np.log(probabilities[np.arange(len(output)), y])
    one_hot = np.eye(len(PR_LABELS), dtype=float)[y]
    output["brier_loss"] = np.square(probabilities - one_hot).sum(axis=1)
    return output


def build_paired_contrasts(
    *,
    losses: pd.DataFrame,
    arrows: tuple[tuple[str, str, str], ...],
    block_length: int,
    bootstrap_reps: int,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    loss_keys = ["fold_id", "target_view_id", "partition", "sample_id"]
    test_losses = losses.loc[losses["partition"].astype("string").eq("test")].copy()
    for arrow_name, previous_id, next_id in arrows:
        previous = test_losses.loc[test_losses["representation_id"].astype("string").eq(previous_id), loss_keys + ["log_loss", "brier_loss", "record.node_id", "record.segment_id", "record.ts_sample"]]
        next_frame = test_losses.loc[test_losses["representation_id"].astype("string").eq(next_id), loss_keys + ["log_loss", "brier_loss"]]
        joined = previous.merge(
            next_frame,
            on=loss_keys,
            how="inner",
            validate="one_to_one",
            suffixes=("_previous", "_next"),
        )
        joined["delta_log_loss"] = joined["log_loss_previous"] - joined["log_loss_next"]
        joined["delta_brier_loss"] = joined["brier_loss_previous"] - joined["brier_loss_next"]
        for (fold_id, target_view_id), group in joined.groupby(["fold_id", "target_view_id"], sort=True):
            delta_log = group["delta_log_loss"].to_numpy(dtype=float)
            delta_brier = group["delta_brier_loss"].to_numpy(dtype=float)
            bootstrap_log = _block_bootstrap(
                group,
                value_column="delta_log_loss",
                block_length=block_length,
                repetitions=bootstrap_reps,
                seed=_stable_seed(seed, arrow_name, fold_id, target_view_id, "log"),
            )
            bootstrap_brier = _block_bootstrap(
                group,
                value_column="delta_brier_loss",
                block_length=block_length,
                repetitions=bootstrap_reps,
                seed=_stable_seed(seed, arrow_name, fold_id, target_view_id, "brier"),
            )
            rows.append(
                {
                    "arrow": arrow_name,
                    "previous_representation_id": previous_id,
                    "next_representation_id": next_id,
                    "fold_id": str(fold_id),
                    "target_view_id": str(target_view_id),
                    "anchor_count": int(len(group)),
                    "delta_log_loss": float(delta_log.mean()),
                    "delta_log_loss_ci_low": float(np.percentile(bootstrap_log, 2.5)),
                    "delta_log_loss_ci_high": float(np.percentile(bootstrap_log, 97.5)),
                    "delta_brier_loss": float(delta_brier.mean()),
                    "delta_brier_loss_ci_low": float(np.percentile(bootstrap_brier, 2.5)),
                    "delta_brier_loss_ci_high": float(np.percentile(bootstrap_brier, 97.5)),
                    "block_length": block_length,
                    "bootstrap_repetitions": bootstrap_reps,
                }
            )
    fold_contrasts = pd.DataFrame(rows).convert_dtypes()
    summary = _summarize_contrasts(
        joined_losses=losses,
        fold_contrasts=fold_contrasts,
        arrows=arrows,
        block_length=block_length,
        bootstrap_reps=bootstrap_reps,
        seed=seed,
    )
    return fold_contrasts, summary


def _summarize_contrasts(
    *,
    joined_losses: pd.DataFrame,
    fold_contrasts: pd.DataFrame,
    arrows: tuple[tuple[str, str, str], ...],
    block_length: int,
    bootstrap_reps: int,
    seed: int,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    test_losses = joined_losses.loc[joined_losses["partition"].astype("string").eq("test")].copy()
    keys = ["fold_id", "target_view_id", "partition", "sample_id"]
    for arrow_name, previous_id, next_id in arrows:
        previous = test_losses.loc[test_losses["representation_id"].astype("string").eq(previous_id), keys + ["log_loss", "brier_loss", "record.node_id", "record.segment_id", "record.ts_sample"]]
        next_frame = test_losses.loc[test_losses["representation_id"].astype("string").eq(next_id), keys + ["log_loss", "brier_loss"]]
        joined = previous.merge(next_frame, on=keys, how="inner", validate="one_to_one", suffixes=("_previous", "_next"))
        joined["delta_log_loss"] = joined["log_loss_previous"] - joined["log_loss_next"]
        joined["delta_brier_loss"] = joined["brier_loss_previous"] - joined["brier_loss_next"]
        for target_view_id, group in joined.groupby("target_view_id", sort=True):
            fold_rows = fold_contrasts.loc[
                (fold_contrasts["arrow"].astype("string") == arrow_name)
                & (fold_contrasts["target_view_id"].astype("string") == str(target_view_id))
            ]
            pooled_log = _block_bootstrap(
                group,
                value_column="delta_log_loss",
                block_length=block_length,
                repetitions=bootstrap_reps,
                seed=_stable_seed(seed, arrow_name, target_view_id, "pooled", "log"),
            )
            pooled_brier = _block_bootstrap(
                group,
                value_column="delta_brier_loss",
                block_length=block_length,
                repetitions=bootstrap_reps,
                seed=_stable_seed(seed, arrow_name, target_view_id, "pooled", "brier"),
            )
            rows.append(
                {
                    "arrow": arrow_name,
                    "previous_representation_id": previous_id,
                    "next_representation_id": next_id,
                    "target_view_id": str(target_view_id),
                    "fold_count": int(fold_rows["fold_id"].nunique()),
                    "anchor_count": int(len(group)),
                    "delta_log_loss_mean_across_folds": _finite_or_nan(fold_rows["delta_log_loss"].mean()),
                    "delta_log_loss_sd_across_folds": _sample_sd(fold_rows["delta_log_loss"]),
                    "delta_brier_loss_mean_across_folds": _finite_or_nan(fold_rows["delta_brier_loss"].mean()),
                    "delta_brier_loss_sd_across_folds": _sample_sd(fold_rows["delta_brier_loss"]),
                    "pooled_delta_log_loss": float(group["delta_log_loss"].mean()),
                    "pooled_delta_log_loss_ci_low": float(np.percentile(pooled_log, 2.5)),
                    "pooled_delta_log_loss_ci_high": float(np.percentile(pooled_log, 97.5)),
                    "pooled_delta_brier_loss": float(group["delta_brier_loss"].mean()),
                    "pooled_delta_brier_loss_ci_low": float(np.percentile(pooled_brier, 2.5)),
                    "pooled_delta_brier_loss_ci_high": float(np.percentile(pooled_brier, 97.5)),
                    "block_length": block_length,
                    "bootstrap_repetitions": bootstrap_reps,
                }
            )
    return pd.DataFrame(rows).convert_dtypes()


def _block_bootstrap(
    frame: pd.DataFrame,
    *,
    value_column: str,
    block_length: int,
    repetitions: int,
    seed: int,
) -> np.ndarray:
    if frame.empty:
        return np.asarray([np.nan])
    rng = np.random.default_rng(seed)
    groups: list[np.ndarray] = []
    group_columns = ["record.node_id", "record.segment_id"]
    if "fold_id" in frame.columns:
        group_columns.insert(0, "fold_id")
    sort_columns = [*group_columns, "record.ts_sample", "sample_id"]
    for _, group in frame.sort_values(sort_columns, kind="stable").groupby(
        group_columns, sort=False, dropna=False
    ):
        values = group[value_column].to_numpy(dtype=float)
        if len(values):
            groups.append(values)
    if not groups:
        return np.asarray([np.nan])
    weights = np.asarray([len(values) for values in groups], dtype=float)
    weights /= weights.sum()
    sample_count = len(frame)
    estimates = np.empty(repetitions, dtype=float)
    for repetition in range(repetitions):
        sampled: list[float] = []
        while len(sampled) < sample_count:
            group = groups[int(rng.choice(len(groups), p=weights))]
            length = min(max(1, block_length), len(group))
            start = int(rng.integers(0, len(group)))
            indices = (start + np.arange(length)) % len(group)
            sampled.extend(group[indices].tolist())
        estimates[repetition] = float(np.mean(sampled[:sample_count]))
    return estimates


def _stable_seed(seed: int, *parts: object) -> int:
    value = "|".join([str(seed), *[str(part) for part in parts]])
    return int((seed + zlib.crc32(value.encode("utf-8"))) % (2**32 - 1))


def _sample_sd(values: pd.Series) -> float:
    numeric = pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype=float)
    if len(numeric) < 2:
        return float("nan")
    return float(np.std(numeric, ddof=1))


def _finite_or_nan(value: object) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return numeric if np.isfinite(numeric) else float("nan")
