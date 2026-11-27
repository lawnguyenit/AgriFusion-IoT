from __future__ import annotations

import zlib

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score

from .rq1_statistics import _block_bootstrap, _finite_or_nan, _sample_sd
from .runner import REPORT_LABELS


def build_factorial_contrasts(
    *,
    losses: pd.DataFrame,
    block_length: int,
    bootstrap_reps: int,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compare F00/F10/F01/F11 on the same held-out anchors."""

    ids = {"F00": "S1_X_t", "F10": "S3_X_t_HX", "F01": "F01_X_t_WX", "F11": "F11_X_t_HX_WX"}
    keys = ["fold_id", "target_view_id", "partition", "sample_id"]
    test = losses.loc[losses["partition"].astype("string").eq("test")].copy()
    frames: list[pd.DataFrame] = []
    for fold_id in sorted(test["fold_id"].astype("string").unique()):
        for target_view_id in sorted(test["target_view_id"].astype("string").unique()):
            pieces: dict[str, pd.DataFrame] = {}
            for label, representation_id in ids.items():
                piece = test.loc[
                    test["fold_id"].astype("string").eq(fold_id)
                    & test["target_view_id"].astype("string").eq(target_view_id)
                    & test["representation_id"].astype("string").eq(representation_id),
                    keys + ["log_loss", "brier_loss", "record.node_id", "record.segment_id", "record.ts_sample"],
                ].copy()
                pieces[label] = piece.rename(columns={"log_loss": f"log_{label}", "brier_loss": f"brier_{label}"})
            joined = pieces["F00"]
            for label in ("F10", "F01", "F11"):
                joined = joined.merge(pieces[label], on=keys + ["record.node_id", "record.segment_id", "record.ts_sample"], how="inner", validate="one_to_one")
            if joined.empty:
                continue
            joined["delta_H_log_loss"] = joined["log_F00"] - joined["log_F10"]
            joined["delta_W_log_loss"] = joined["log_F00"] - joined["log_F01"]
            joined["delta_HW_log_loss"] = joined["log_F00"] - joined["log_F11"]
            joined["gamma_log_loss"] = joined["log_F11"] - joined["log_F10"] - joined["log_F01"] + joined["log_F00"]
            joined["delta_H_brier"] = joined["brier_F00"] - joined["brier_F10"]
            joined["delta_W_brier"] = joined["brier_F00"] - joined["brier_F01"]
            joined["delta_HW_brier"] = joined["brier_F00"] - joined["brier_F11"]
            joined["gamma_brier"] = joined["brier_F11"] - joined["brier_F10"] - joined["brier_F01"] + joined["brier_F00"]
            for metric in ("delta_H_log_loss", "delta_W_log_loss", "delta_HW_log_loss", "gamma_log_loss", "delta_H_brier", "delta_W_brier", "delta_HW_brier", "gamma_brier"):
                boot = _block_bootstrap(joined, value_column=metric, block_length=block_length, repetitions=bootstrap_reps, seed=_stable_seed(seed, fold_id, target_view_id, metric))
                joined[f"{metric}_ci_low"] = float(np.percentile(boot, 2.5))
                joined[f"{metric}_ci_high"] = float(np.percentile(boot, 97.5))
            frames.append(joined)
    if not frames:
        return pd.DataFrame(), pd.DataFrame()
    by_fold = pd.concat(frames, ignore_index=True).convert_dtypes()
    summary_rows: list[dict[str, object]] = []
    for target_view_id, group in by_fold.groupby("target_view_id", sort=True):
        row: dict[str, object] = {"target_view_id": str(target_view_id), "fold_count": int(group["fold_id"].nunique()), "anchor_count": int(len(group))}
        for metric in ("delta_H_log_loss", "delta_W_log_loss", "delta_HW_log_loss", "gamma_log_loss", "delta_H_brier", "delta_W_brier", "delta_HW_brier", "gamma_brier"):
            fold_values = group.groupby("fold_id")[metric].mean()
            row[f"{metric}_mean_across_folds"] = _finite_or_nan(fold_values.mean())
            row[f"{metric}_sd_across_folds"] = _sample_sd(fold_values)
            boot = _block_bootstrap(group, value_column=metric, block_length=block_length, repetitions=bootstrap_reps, seed=_stable_seed(seed, target_view_id, "pooled", metric))
            row[f"pooled_{metric}"] = _finite_or_nan(group[metric].mean())
            row[f"pooled_{metric}_ci_low"] = float(np.percentile(boot, 2.5))
            row[f"pooled_{metric}_ci_high"] = float(np.percentile(boot, 97.5))
        summary_rows.append(row)
    return by_fold, pd.DataFrame(summary_rows).convert_dtypes()


def build_module_a_group_metrics(*, predictions: pd.DataFrame, target_frame: pd.DataFrame, row_index: pd.DataFrame, moisture_frame: pd.DataFrame, k: int = 3) -> pd.DataFrame:
    s0 = predictions.loc[
        predictions["representation_id"].astype("string").eq("S0_M_t")
        & predictions["partition"].astype("string").eq("test")
    ].copy()
    if s0.empty:
        return pd.DataFrame()
    target_cols = ["sample_id", "q_threshold"]
    if "support_depth_at_anchor" not in s0.columns:
        target_cols.append("support_depth_at_anchor")
    joined = s0.merge(target_frame.loc[:, [column for column in target_cols if column in target_frame.columns]], on="sample_id", how="left", validate="many_to_one")
    joined = joined.merge(moisture_frame.loc[:, ["sample_id", "moisture_current"]], on="sample_id", how="left", validate="many_to_one")
    moisture = pd.to_numeric(joined["moisture_current"], errors="coerce")
    threshold = pd.to_numeric(joined["q_threshold"], errors="coerce")
    depth = pd.to_numeric(joined["support_depth_at_anchor"], errors="coerce")
    valid = moisture.notna() & threshold.notna() & depth.notna()
    joined["group"] = np.select(
        [valid & moisture.gt(threshold), valid & moisture.le(threshold) & depth.lt(k), valid & moisture.le(threshold) & depth.ge(k)],
        ["G0_M_gt_Q", "G1_M_le_Q_d_lt_K", "G2_M_le_Q_d_ge_K"],
        default="G_unknown_missing_boundary",
    )
    rows: list[dict[str, object]] = []
    joined = joined.loc[joined["group"].astype("string").ne("G_unknown_missing_boundary")].copy()
    for (fold_id, target_view_id, group_name), subset in joined.groupby(["fold_id", "target_view_id", "group"], sort=True):
        true = subset["label_true"].astype("string")
        pred = subset["label_pred"].astype("string")
        rows.append({"fold_id": str(fold_id), "target_view_id": str(target_view_id), "group": str(group_name), "sample_count": int(len(subset)), "error_rate": float((true != pred).mean()), "accuracy": float((true == pred).mean()), "macro_f1_fixed_3class": float(f1_score(true, pred, labels=list(REPORT_LABELS), average="macro", zero_division=0)), "mean_moisture": _safe_mean(subset["moisture_current"]), "mean_support_depth": _safe_mean(subset["support_depth_at_anchor"])})
    return pd.DataFrame(rows).convert_dtypes()


def build_snapshot_alias_pairs(*, anchors: pd.DataFrame, epsilon: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    working = anchors.dropna(subset=["moisture_current"]).copy()
    working = working.sort_values(["record.node_id", "record.segment_id", "moisture_current", "record.ts_sample"], kind="stable")
    pairs: list[dict[str, object]] = []
    for (_, _), group in working.groupby(["record.node_id", "record.segment_id"], sort=False, dropna=False):
        rows = group.to_dict(orient="records")
        for index, left in enumerate(rows):
            for right in rows[index + 1 :]:
                difference = abs(float(left["moisture_current"]) - float(right["moisture_current"]))
                if difference > epsilon:
                    if float(right["moisture_current"]) - float(left["moisture_current"]) > epsilon:
                        break
                    continue
                pairs.append({"sample_id_i": left["sample_id"], "sample_id_j": right["sample_id"], "moisture_abs_diff": difference, "depth_i": left["support_depth_at_anchor"], "depth_j": right["support_depth_at_anchor"], "online_label_i": left["label_online"], "online_label_j": right["label_online"], "event_label_i": left["label_event"], "event_label_j": right["label_event"], "depth_diff": bool(left["support_depth_at_anchor"] != right["support_depth_at_anchor"]), "online_label_diff": bool(left["label_online"] != right["label_online"]), "event_label_diff": bool(left["label_event"] != right["label_event"])})
    pair_frame = pd.DataFrame(pairs).convert_dtypes()
    if pair_frame.empty:
        return pair_frame, pd.DataFrame([{"epsilon": epsilon, "pair_count": 0, "depth_difference_rate": np.nan, "online_label_difference_rate": np.nan, "event_label_difference_rate": np.nan}]).convert_dtypes()
    summary = pd.DataFrame([{"epsilon": epsilon, "pair_count": int(len(pair_frame)), "depth_difference_rate": float(pair_frame["depth_diff"].mean()), "online_label_difference_rate": float(pair_frame["online_label_diff"].mean()), "event_label_difference_rate": float(pair_frame["event_label_diff"].mean()), "median_moisture_abs_diff": float(pair_frame["moisture_abs_diff"].median())}]).convert_dtypes()
    return pair_frame, summary


def _stable_seed(seed: int, *parts: object) -> int:
    value = "|".join([str(seed), *[str(part) for part in parts]])
    return int((seed + zlib.crc32(value.encode("utf-8"))) % (2**32 - 1))


def _safe_mean(values: pd.Series) -> float:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    return float(numeric.mean()) if not numeric.empty else float("nan")
