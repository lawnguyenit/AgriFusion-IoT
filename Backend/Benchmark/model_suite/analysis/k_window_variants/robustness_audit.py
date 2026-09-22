from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score, f1_score, precision_score, recall_score

from .runner import LOW_LABEL, REF_LABEL, REPORT_LABELS, UNRES_LABEL


def build_unres_audit(predictions: pd.DataFrame) -> pd.DataFrame:
    """Report conditional test metrics for UNRES provenance strata.

    Provenance is read only from held-out target lineage. It is never used to
    fit the classifier. `U_K` is the union of `U_K_succ` and `U_K_fail`.
    """

    if predictions.empty:
        return pd.DataFrame()
    working = predictions.loc[predictions["partition"].astype("string").eq("test")].copy()
    if working.empty:
        return pd.DataFrame()
    rows: list[dict[str, object]] = []
    for keys, group in working.groupby(["variant_id", "target_view_id"], sort=True):
        variant_id, target_view_id = keys
        conditions = {
            "all_test": pd.Series(True, index=group.index),
            "exclude_U_A": ~group["provenance_stratum"].astype("string").eq("U_A"),
            "UNRES_K": group["provenance_stratum"].astype("string").isin(["U_K_succ", "U_K_fail"]),
            "U_K_succ": group["provenance_stratum"].astype("string").eq("U_K_succ"),
            "U_K_fail": group["provenance_stratum"].astype("string").eq("U_K_fail"),
            "U_A": group["provenance_stratum"].astype("string").eq("U_A"),
        }
        for condition, mask in conditions.items():
            subset = group.loc[mask].copy()
            if subset.empty:
                continue
            true = subset["label_true"].astype("string")
            pred = subset["label_pred"].astype("string")
            rows.append(
                {
                    "variant_id": variant_id,
                    "target_view_id": target_view_id,
                    "partition": "test",
                    "condition": condition,
                    "sample_count": len(subset),
                    "true_label_counts_json": json.dumps(true.value_counts().to_dict(), ensure_ascii=True, sort_keys=True),
                    "pred_label_counts_json": json.dumps(pred.value_counts().to_dict(), ensure_ascii=True, sort_keys=True),
                    "accuracy": float((true == pred).mean()),
                    "macro_f1_fixed_3class": float(
                        f1_score(true, pred, labels=list(REPORT_LABELS), average="macro", zero_division=0)
                    ),
                    "balanced_accuracy_supported": float(_safe_balanced_accuracy(true, pred)),
                    "low_recall": float(recall_score(true, pred, labels=[LOW_LABEL], average="macro", zero_division=0)),
                    "unres_recall": float(recall_score(true, pred, labels=[UNRES_LABEL], average="macro", zero_division=0)),
                    "ref_recall": float(recall_score(true, pred, labels=[REF_LABEL], average="macro", zero_division=0)),
                    "predicted_unres_rate": float(pred.eq(UNRES_LABEL).mean()),
                }
            )
    return pd.DataFrame(rows).convert_dtypes()


def build_threshold_history_oracle(
    *,
    snapshot_frame: pd.DataFrame,
    row_index: pd.DataFrame,
    target_frame: pd.DataFrame,
    partition: str = "test",
) -> pd.DataFrame:
    """Reconstruct a deterministic LOW gate from M_t, M_t-1, and M_t-2.

    The oracle uses only raw soil-moisture values and the frozen Q threshold.
    It is intentionally evaluated against the existing target labels as a
    positive control; it is not a new label authority.
    """

    target = target_frame.loc[
        target_frame["final_trainability"].fillna(False).astype(bool)
        & target_frame["partition"].astype("string").eq(partition)
    ].copy()
    if target.empty:
        return pd.DataFrame()
    required_index = ["record.id", "record.node_id", "record.segment_id", "record.ts_sample", "source_row_position"]
    ordered = row_index.loc[:, required_index].copy().rename(columns={"record.id": "sample_id"})
    ordered["sample_id"] = ordered["sample_id"].astype("string")
    ordered = ordered.sort_values(
        ["record.node_id", "record.segment_id", "record.ts_sample", "source_row_position"],
        kind="stable",
    ).reset_index(drop=True)
    moisture = snapshot_frame.set_index("sample_id")["npk.soil_moisture_pct"].apply(pd.to_numeric, errors="coerce")
    output: list[dict[str, object]] = []
    target_lookup = target.set_index("sample_id", drop=False)
    for _, group in ordered.groupby(["record.node_id", "record.segment_id"], sort=False, dropna=False):
        positions = group.index.to_numpy(dtype=int)
        for local_position, output_position in enumerate(positions):
            sample_id = str(ordered.loc[output_position, "sample_id"])
            if sample_id not in target_lookup.index:
                continue
            current_ts = int(ordered.loc[output_position, "record.ts_sample"])
            row: dict[str, object] = {
                "sample_id": sample_id,
                "m_t": _finite_value(moisture.get(sample_id)),
                "m_t_minus_1": np.nan,
                "m_t_minus_2": np.nan,
                "age_1_hours": np.nan,
                "age_2_hours": np.nan,
            }
            for lag in (1, 2):
                if local_position < lag:
                    continue
                prior_position = int(positions[local_position - lag])
                prior_id = str(ordered.loc[prior_position, "sample_id"])
                row[f"m_t_minus_{lag}"] = _finite_value(moisture.get(prior_id))
                row[f"age_{lag}_hours"] = (current_ts - int(ordered.loc[prior_position, "record.ts_sample"])) / 3600.0
            threshold = _finite_value(target_lookup.loc[sample_id, "q_threshold"])
            row["q_threshold"] = threshold
            row["all_three_finite"] = bool(all(np.isfinite(row[name]) for name in ("m_t", "m_t_minus_1", "m_t_minus_2", "q_threshold")))
            row["three_step_causal_within_3h"] = bool(
                row["all_three_finite"]
                and float(row["age_1_hours"]) <= 3.0
                and float(row["age_2_hours"]) <= 3.0
            )
            row["oracle_point_low"] = bool(row["all_three_finite"] and float(row["m_t"]) <= float(threshold))
            row["oracle_k3_low"] = bool(
                row["three_step_causal_within_3h"]
                and all(float(row[name]) <= float(threshold) for name in ("m_t", "m_t_minus_1", "m_t_minus_2"))
            )
            for label_column in ("label_online", "label_event"):
                row[label_column] = str(target_lookup.loc[sample_id, label_column])
            row["point_label"] = str(target_lookup.loc[sample_id, "point_label"])
            row["target_support_depth_at_anchor"] = target_lookup.loc[sample_id, "target_support_depth_at_anchor"]
            output.append(row)
    return pd.DataFrame(output).convert_dtypes()


def summarize_threshold_oracle(oracle_rows: pd.DataFrame) -> pd.DataFrame:
    if oracle_rows.empty:
        return pd.DataFrame()
    rows: list[dict[str, object]] = []
    for oracle_name in ("oracle_point_low", "oracle_k3_low"):
        for label_column in ("label_online", "label_event"):
            true = oracle_rows[label_column].astype("string").eq(LOW_LABEL).astype(int)
            pred = oracle_rows[oracle_name].astype(bool).astype(int)
            rows.append(
                {
                    "oracle": oracle_name,
                    "target": label_column,
                    "sample_count": len(oracle_rows),
                    "oracle_positive_count": int(pred.sum()),
                    "target_low_count": int(true.sum()),
                    "coverage_all_three_finite": float(oracle_rows["all_three_finite"].mean()),
                    "coverage_three_step_causal_within_3h": float(oracle_rows["three_step_causal_within_3h"].mean()),
                    "precision_low": float(precision_score(true, pred, zero_division=0)),
                    "recall_low": float(recall_score(true, pred, zero_division=0)),
                    "f1_low": float(f1_score(true, pred, zero_division=0)),
                    "balanced_accuracy": float(balanced_accuracy_score(true, pred)),
                    "agreement_with_target": float((true == pred).mean()),
                }
            )
    return pd.DataFrame(rows).convert_dtypes()


def _finite_value(value: object) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return numeric if np.isfinite(numeric) else float("nan")


def _safe_balanced_accuracy(true: pd.Series, pred: pd.Series) -> float:
    try:
        return float(balanced_accuracy_score(true, pred))
    except ValueError:
        return float("nan")
