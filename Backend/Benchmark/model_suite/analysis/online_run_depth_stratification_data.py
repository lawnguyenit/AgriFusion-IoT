"""Data selection and summary functions for the online run-depth analysis."""

from __future__ import annotations

import json
from typing import Iterable

import pandas as pd

from Backend.Benchmark.weak_labels.analysis.temporal_target_views import Y_ONLINE

LOW_LABEL = "persistent_low_relative_moisture_at_anchor"
DEFAULT_FEATURE_VIEW_IDS = ("v2_temporal_mini_3h", "v2_temporal_full_3h")
DEFAULT_PARTITIONS = ("validation", "test")
DEPTH_BINS = ("d=1", "d=2", "d>=3")
RUN_OUTCOMES = ("successful", "failed", "censored_or_unknown")


def build_q_positive_population(targets: pd.DataFrame, *, target_view_id: str = Y_ONLINE) -> pd.DataFrame:
    """Return one row per Q-positive anchor with derived depth/outcome bins."""

    required = {
        "sample_id",
        "target_view_id",
        "point_label",
        "support_depth_at_anchor",
        "eventual_run_length",
        "run_complete",
        "required_k",
        "run_id",
        "m_relation_to_q",
    }
    _require_columns(targets, required, "target-view assignments")
    view = targets.loc[targets["target_view_id"].astype("string").eq(target_view_id)].copy()
    if view.empty:
        raise ValueError(f"Target view has no rows: {target_view_id}")
    if view["sample_id"].astype("string").duplicated().any():
        raise ValueError("Target view is not unique by sample_id.")
    q = view.loc[view["point_label"].astype("string").eq("low_relative_moisture_point")].copy()
    if q.empty:
        raise ValueError("Target view contains no Q-positive observations.")
    q["sample_id"] = q["sample_id"].astype("string")
    q["depth_bin"] = q["support_depth_at_anchor"].map(_depth_bin)
    q["run_outcome"] = q.apply(_run_outcome, axis=1)
    if not q["m_relation_to_q"].astype("string").eq("M_t<=Q").all():
        raise ValueError("Q-positive population contains a row outside M_t<=Q.")
    keep = [
        "sample_id",
        "deployment_segment_id",
        "sample_time_utc",
        "run_id",
        "point_label",
        "m_relation_to_q",
        "moisture_value",
        "q_threshold",
        "q_comparator",
        "support_depth_at_anchor",
        "eventual_run_length",
        "run_complete",
        "required_k",
        "depth_bin",
        "run_outcome",
        "online_label_name",
        "online_label_status",
    ]
    return q.loc[:, [column for column in keep if column in q.columns]].sort_values(
        ["sample_time_utc", "sample_id"], kind="stable"
    ).reset_index(drop=True).convert_dtypes()


def join_online_predictions(predictions: pd.DataFrame, q_population: pd.DataFrame) -> pd.DataFrame:
    """Join selected model predictions to Q-positive lineage and parse LOW probability."""

    required_predictions = {
        "feature_view_id",
        "partition",
        "sample_id",
        "target_view_id",
        "label_name_pred",
        "class_names_json",
        "prediction_probability_json",
    }
    _require_columns(predictions, required_predictions, "online predictions")
    _require_columns(q_population, {"sample_id", "depth_bin", "run_outcome"}, "Q-positive population")
    pred = predictions.copy()
    pred["sample_id"] = pred["sample_id"].astype("string")
    key = ["feature_view_id", "partition", "sample_id"]
    if pred.duplicated(key, keep=False).any():
        raise ValueError("Selected online predictions are not unique by view/partition/sample.")
    q = q_population.copy()
    q["sample_id"] = q["sample_id"].astype("string")
    joined = pred.merge(q, on="sample_id", how="inner", validate="many_to_one")
    if joined.empty:
        raise ValueError("Selected online predictions have no matching Q-positive anchors.")
    joined["predicted_low"] = joined["label_name_pred"].astype("string").eq(LOW_LABEL)
    joined["predicted_low_probability"] = joined.apply(_low_probability, axis=1)
    return joined.sort_values(
        ["feature_view_id", "partition", "sample_time_utc", "sample_id"], kind="stable"
    ).reset_index(drop=True).convert_dtypes()


def build_population_summary(q_population: pd.DataFrame) -> pd.DataFrame:
    """Count the full Q-positive population by eventual outcome and depth."""

    _require_columns(q_population, {"depth_bin", "run_outcome", "run_id"}, "Q-positive population")
    grouped = (
        q_population.groupby(["run_outcome", "depth_bin"], dropna=False)
        .agg(q_positive_rows=("sample_id", "size"), run_count=("run_id", "nunique"))
        .reset_index()
    )
    return _complete_summary(
        grouped,
        dimensions=["run_outcome", "depth_bin"],
        levels=[RUN_OUTCOMES, DEPTH_BINS],
        value_columns=["q_positive_rows", "run_count"],
    )


def build_prediction_summary(joined: pd.DataFrame) -> pd.DataFrame:
    """Compute hard LOW rates and mean LOW probabilities for every stratum."""

    required = {
        "feature_view_id",
        "partition",
        "run_outcome",
        "depth_bin",
        "predicted_low",
        "predicted_low_probability",
        "sample_id",
    }
    _require_columns(joined, required, "joined online predictions")
    grouped = (
        joined.groupby(["feature_view_id", "partition", "run_outcome", "depth_bin"], dropna=False)
        .agg(
            prediction_rows=("sample_id", "size"),
            unique_samples=("sample_id", "nunique"),
            pred_low_count=("predicted_low", "sum"),
            pred_low_rate=("predicted_low", "mean"),
            mean_predicted_low_probability=("predicted_low_probability", "mean"),
        )
        .reset_index()
    )
    return _complete_summary(
        grouped,
        dimensions=["feature_view_id", "partition", "run_outcome", "depth_bin"],
        levels=[
            sorted(joined["feature_view_id"].astype("string").unique().tolist()),
            sorted(joined["partition"].astype("string").unique().tolist()),
            RUN_OUTCOMES,
            DEPTH_BINS,
        ],
        value_columns=[
            "prediction_rows",
            "unique_samples",
            "pred_low_count",
            "pred_low_rate",
            "mean_predicted_low_probability",
        ],
    )


def select_predictions(
    predictions: pd.DataFrame,
    *,
    target_view_id: str,
    feature_view_ids: Iterable[str],
    partitions: Iterable[str],
) -> pd.DataFrame:
    """Select the requested existing online prediction scope."""

    _require_columns(
        predictions,
        {"target_view_id", "feature_view_id", "partition", "sample_id"},
        "model predictions",
    )
    selected = predictions.loc[
        predictions["target_view_id"].astype("string").eq(target_view_id)
        & predictions["feature_view_id"].astype("string").isin(tuple(feature_view_ids))
        & predictions["partition"].astype("string").isin(tuple(partitions))
    ].copy()
    if selected.empty:
        raise ValueError("No online predictions match the requested target/view/partition scope.")
    return selected.convert_dtypes()


def _complete_summary(
    frame: pd.DataFrame,
    *,
    dimensions: list[str],
    levels: list[Iterable[object]],
    value_columns: list[str],
) -> pd.DataFrame:
    index = pd.MultiIndex.from_product(levels, names=dimensions)
    completed = frame.set_index(dimensions).reindex(index).reset_index()
    for column in value_columns:
        if column in {"q_positive_rows", "run_count", "prediction_rows", "unique_samples", "pred_low_count"}:
            completed[column] = completed[column].fillna(0).astype("int64")
        else:
            completed[column] = pd.to_numeric(completed[column], errors="coerce")
    return completed.sort_values(dimensions, kind="stable").reset_index(drop=True).convert_dtypes()


def _depth_bin(value: object) -> str:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return "unknown"
    integer = int(number)
    if integer == 1:
        return "d=1"
    if integer == 2:
        return "d=2"
    if integer >= 3:
        return "d>=3"
    return "unknown"


def _run_outcome(row: pd.Series) -> str:
    complete = row.get("run_complete")
    eventual = pd.to_numeric(row.get("eventual_run_length"), errors="coerce")
    required = pd.to_numeric(row.get("required_k"), errors="coerce")
    if pd.isna(eventual) or pd.isna(required) or pd.isna(complete) or not bool(complete):
        return "censored_or_unknown"
    return "successful" if int(eventual) >= int(required) else "failed"


def _low_probability(row: pd.Series) -> float:
    try:
        class_names = json.loads(str(row["class_names_json"]))
        probabilities = json.loads(str(row["prediction_probability_json"]))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Prediction probability JSON is malformed.") from exc
    if isinstance(probabilities, dict):
        value = probabilities.get(LOW_LABEL)
    else:
        try:
            value = probabilities[class_names.index(LOW_LABEL)]
        except (AttributeError, KeyError, TypeError, ValueError, IndexError) as exc:
            raise ValueError("Prediction probabilities do not contain the LOW class.") from exc
    if value is None:
        raise ValueError("Prediction probabilities do not contain the LOW class.")
    return float(value)


def _require_columns(frame: pd.DataFrame, required: set[str], name: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{name} is missing required columns: {missing}")
