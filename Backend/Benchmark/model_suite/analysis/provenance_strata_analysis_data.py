"""Data contracts and summaries for provenance-aware prediction analysis."""

from __future__ import annotations

import json
from typing import Iterable

import pandas as pd

from Backend.Benchmark.weak_labels.analysis.temporal_target_views import Y_EVENT, Y_ONLINE

LOW_LABEL = "persistent_low_relative_moisture_at_anchor"
UNRES_LABEL = "unresolved_environmental_evidence_at_anchor"
REF_LABEL = "reference_context_at_anchor"
DISPLAY_LABELS = {
    LOW_LABEL: "LOW",
    UNRES_LABEL: "UNRES",
    REF_LABEL: "REF",
}
PREDICTION_LABELS = ("LOW", "UNRES", "REF")
PROVENANCE_STRATA = ("LOW", "U_K_succ", "U_K_fail", "U_A", "REF")
K_STRATA = ("LOW", "U_K_succ", "U_K_fail")
DEPTH_BINS = ("d=1", "d=2", "d>=3")


def build_provenance_frame(targets: pd.DataFrame, *, target_view_id: str = Y_ONLINE) -> pd.DataFrame:
    """Assign exactly one of five provenance strata to every online labeled row."""

    required = {
        "sample_id",
        "target_view_id",
        "online_label_name",
        "online_label_status",
        "event_label_name",
        "event_label_status",
        "point_label",
        "unres_origin",
        "m_relation_to_q",
        "aux_positive_count",
        "support_depth_at_anchor",
        "eventual_run_length",
        "run_complete",
        "required_k",
        "run_id",
    }
    _require_columns(targets, required, "target-view assignments")
    view = targets.loc[targets["target_view_id"].astype("string").eq(target_view_id)].copy()
    view = view.loc[
        view["online_label_status"].astype("string").eq("LABELED")
        & view["event_label_status"].astype("string").eq("LABELED")
    ].copy()
    if view.empty:
        raise ValueError(f"No labeled rows exist for target view: {target_view_id}")
    view["sample_id"] = view["sample_id"].astype("string")
    if view["sample_id"].duplicated().any():
        raise ValueError("Online labeled target rows are not unique by sample_id.")

    view["depth_bin"] = view["support_depth_at_anchor"].map(_depth_bin)
    view["run_outcome"] = view.apply(_run_outcome, axis=1)
    view["provenance_stratum"] = pd.Series(pd.NA, index=view.index, dtype="string")

    view.loc[view["online_label_name"].astype("string").eq(LOW_LABEL), "provenance_stratum"] = "LOW"
    view.loc[view["unres_origin"].astype("string").eq("UNRES_A"), "provenance_stratum"] = "U_A"
    view.loc[
        view["unres_origin"].astype("string").eq("UNRES_K")
        & view["run_outcome"].astype("string").eq("successful"),
        "provenance_stratum",
    ] = "U_K_succ"
    view.loc[
        view["unres_origin"].astype("string").eq("UNRES_K")
        & view["run_outcome"].astype("string").eq("failed"),
        "provenance_stratum",
    ] = "U_K_fail"
    view.loc[view["online_label_name"].astype("string").eq(REF_LABEL), "provenance_stratum"] = "REF"

    if view["provenance_stratum"].isna().any():
        examples = view.loc[view["provenance_stratum"].isna(), ["sample_id", "online_label_name", "unres_origin"]].head(10)
        raise ValueError(f"Labeled rows are not covered by the five strata: {examples.to_dict('records')}")
    view["provenance_stratum"] = view["provenance_stratum"].astype("string")
    _validate_provenance_contract(view)

    view["online_target_display"] = view["online_label_name"].map(DISPLAY_LABELS)
    view["event_target_display"] = view["event_label_name"].map(DISPLAY_LABELS)
    keep = [
        "sample_id",
        "deployment_segment_id",
        "sample_time_utc",
        "run_id",
        "point_label",
        "m_relation_to_q",
        "aux_positive_count",
        "support_depth_at_anchor",
        "depth_bin",
        "eventual_run_length",
        "run_complete",
        "required_k",
        "run_outcome",
        "unres_origin",
        "provenance_stratum",
        "online_label_name",
        "event_label_name",
        "online_target_display",
        "event_target_display",
    ]
    return view.loc[:, [column for column in keep if column in view.columns]].sort_values(
        ["sample_time_utc", "sample_id"], kind="stable"
    ).reset_index(drop=True).convert_dtypes()


def select_predictions(
    predictions: pd.DataFrame,
    *,
    target_view_id: str,
    feature_view_ids: Iterable[str],
    partitions: Iterable[str],
) -> pd.DataFrame:
    """Select one target's existing predictions in the requested scope."""

    required = {
        "target_view_id",
        "feature_view_id",
        "partition",
        "fold_id",
        "sample_id",
        "label_name_pred",
        "class_names_json",
        "prediction_probability_json",
    }
    _require_columns(predictions, required, "model predictions")
    selected = predictions.loc[
        predictions["target_view_id"].astype("string").eq(target_view_id)
        & predictions["feature_view_id"].astype("string").isin(tuple(feature_view_ids))
        & predictions["partition"].astype("string").isin(tuple(partitions))
    ].copy()
    if selected.empty:
        raise ValueError(f"No predictions match target/view/partition scope for {target_view_id}.")
    key = ["feature_view_id", "partition", "fold_id", "sample_id"]
    if selected.duplicated(key, keep=False).any():
        raise ValueError("Selected prediction rows are not unique by feature/partition/fold/sample.")
    unknown = sorted(set(selected["label_name_pred"].dropna()) - set(DISPLAY_LABELS))
    if unknown:
        raise ValueError(f"Predictions contain unsupported labels: {unknown}")
    selected["prediction_label"] = selected["label_name_pred"].map(DISPLAY_LABELS)
    selected["p_LOW"] = selected.apply(lambda row: _probability_for(row, LOW_LABEL), axis=1)
    selected["p_UNRES"] = selected.apply(lambda row: _probability_for(row, UNRES_LABEL), axis=1)
    selected["p_REF"] = selected.apply(lambda row: _probability_for(row, REF_LABEL), axis=1)
    probabilities = selected.loc[:, ["p_LOW", "p_UNRES", "p_REF"]].sum(axis=1)
    if not probabilities.sub(1.0).abs().le(1e-5).all():
        raise ValueError("Prediction probability rows do not sum to one within tolerance.")
    return selected.convert_dtypes()


def join_predictions_with_provenance(
    predictions: pd.DataFrame,
    provenance: pd.DataFrame,
    *,
    prediction_source: str,
) -> pd.DataFrame:
    """Join one prediction target to the five-strata provenance frame."""

    _require_columns(predictions, {"sample_id", "prediction_label", "p_LOW", "p_UNRES", "p_REF"}, "selected predictions")
    _require_columns(provenance, {"sample_id", "provenance_stratum"}, "provenance rows")
    pred = predictions.copy()
    prov = provenance.copy()
    pred["sample_id"] = pred["sample_id"].astype("string")
    prov["sample_id"] = prov["sample_id"].astype("string")
    joined = pred.merge(prov, on="sample_id", how="inner", validate="many_to_one")
    if joined.empty:
        raise ValueError(f"No {prediction_source} predictions match the provenance rows.")
    joined["prediction_source"] = prediction_source
    joined["prediction_target_view_id"] = predictions["target_view_id"].iloc[0]
    return joined.sort_values(
        ["feature_view_id", "partition", "sample_id"], kind="stable"
    ).reset_index(drop=True).convert_dtypes()


def build_prediction_count_summary(joined: pd.DataFrame) -> pd.DataFrame:
    """Build the hard 5 x 3 provenance-aware confusion counts."""

    _require_columns(joined, {"feature_view_id", "partition", "provenance_stratum", "prediction_label", "sample_id"}, "joined predictions")
    grouped = (
        joined.groupby(["prediction_source", "feature_view_id", "partition", "provenance_stratum", "prediction_label"], dropna=False)
        .size()
        .rename("prediction_count")
        .reset_index()
    )
    return _complete_prediction_summary(grouped, "prediction_count")


def build_provenance_summary(provenance: pd.DataFrame) -> pd.DataFrame:
    """Count the full online labeled population by provenance stratum."""

    _require_columns(provenance, {"provenance_stratum", "sample_id", "run_id"}, "provenance rows")
    return (
        provenance.groupby("provenance_stratum", dropna=False)
        .agg(row_count=("sample_id", "size"), unique_samples=("sample_id", "nunique"), run_count=("run_id", "nunique"))
        .reindex(PROVENANCE_STRATA, fill_value=0)
        .reset_index()
        .convert_dtypes()
    )


def build_probability_summary(joined: pd.DataFrame) -> pd.DataFrame:
    """Build mean output probabilities for every provenance stratum."""

    _require_columns(joined, {"prediction_source", "feature_view_id", "partition", "provenance_stratum", "sample_id", "p_LOW", "p_UNRES", "p_REF"}, "joined predictions")
    grouped = (
        joined.groupby(["prediction_source", "feature_view_id", "partition", "provenance_stratum"], dropna=False)
        .agg(
            prediction_rows=("sample_id", "size"),
            unique_samples=("sample_id", "nunique"),
            mean_p_LOW=("p_LOW", "mean"),
            mean_p_UNRES=("p_UNRES", "mean"),
            mean_p_REF=("p_REF", "mean"),
        )
        .reset_index()
    )
    return _complete_group_summary(grouped, ["prediction_rows", "unique_samples", "mean_p_LOW", "mean_p_UNRES", "mean_p_REF"])


def build_row_normalized_rates(counts: pd.DataFrame) -> pd.DataFrame:
    """Normalize prediction counts within each true provenance row."""

    _require_columns(counts, {"prediction_source", "feature_view_id", "partition", "provenance_stratum", "prediction_label", "prediction_count"}, "prediction counts")
    keys = ["prediction_source", "feature_view_id", "partition", "provenance_stratum"]
    wide = counts.pivot_table(index=keys, columns="prediction_label", values="prediction_count", fill_value=0, aggfunc="sum").reset_index()
    for label in PREDICTION_LABELS:
        if label not in wide.columns:
            wide[label] = 0
    wide = wide.rename(columns={label: f"count_{label}" for label in PREDICTION_LABELS})
    wide["support"] = wide[[f"count_{label}" for label in PREDICTION_LABELS]].sum(axis=1)
    for label in PREDICTION_LABELS:
        wide[f"rate_{label}"] = wide[f"count_{label}"].div(wide["support"].replace(0, pd.NA))
    return wide.sort_values(keys, kind="stable").reset_index(drop=True).convert_dtypes()


def build_k_decomposition(joined: pd.DataFrame) -> pd.DataFrame:
    """Summarize p(output) for LOW and the two pre-K candidate outcomes."""

    selected = joined.loc[joined["provenance_stratum"].isin(K_STRATA)].copy()
    _require_columns(selected, {"provenance_stratum", "depth_bin", "prediction_source", "feature_view_id", "partition"}, "K decomposition rows")
    grouped = (
        selected.groupby(["prediction_source", "feature_view_id", "partition", "provenance_stratum", "depth_bin"], dropna=False)
        .agg(
            prediction_rows=("sample_id", "size"),
            unique_samples=("sample_id", "nunique"),
            pred_low_count=("prediction_label", lambda values: int(values.eq("LOW").sum())),
            pred_low_rate=("prediction_label", lambda values: float(values.eq("LOW").mean())),
            mean_p_LOW=("p_LOW", "mean"),
            mean_p_UNRES=("p_UNRES", "mean"),
            mean_p_REF=("p_REF", "mean"),
        )
        .reset_index()
    )
    grouped["online_target_expected"] = grouped["provenance_stratum"].map({"LOW": "LOW", "U_K_succ": "UNRES", "U_K_fail": "UNRES"})
    return grouped.sort_values(
        ["prediction_source", "feature_view_id", "partition", "provenance_stratum", "depth_bin"], kind="stable"
    ).reset_index(drop=True).convert_dtypes()


def build_k_contrasts(decomposition: pd.DataFrame) -> pd.DataFrame:
    """Compare p_LOW among U_K_fail, U_K_succ, and confirmed LOW."""

    required = {"prediction_source", "feature_view_id", "partition", "provenance_stratum", "mean_p_LOW", "prediction_rows"}
    _require_columns(decomposition, required, "K decomposition")
    rows: list[dict[str, object]] = []
    for keys, frame in decomposition.groupby(["prediction_source", "feature_view_id", "partition"], sort=False):
        source, view, partition = (str(value) for value in keys)
        means = frame.groupby("provenance_stratum")["mean_p_LOW"].mean().to_dict()
        counts = frame.groupby("provenance_stratum")["prediction_rows"].sum().to_dict()
        rows.append(
            {
                "prediction_source": source,
                "feature_view_id": view,
                "partition": partition,
                "n_LOW": int(counts.get("LOW", 0)),
                "n_U_K_succ": int(counts.get("U_K_succ", 0)),
                "n_U_K_fail": int(counts.get("U_K_fail", 0)),
                "p_LOW_LOW": means.get("LOW"),
                "p_LOW_U_K_succ": means.get("U_K_succ"),
                "p_LOW_U_K_fail": means.get("U_K_fail"),
                "delta_succ_minus_fail": _difference(means.get("U_K_succ"), means.get("U_K_fail")),
                "delta_low_minus_succ": _difference(means.get("LOW"), means.get("U_K_succ")),
            }
        )
    return pd.DataFrame(rows).convert_dtypes()


def build_event_online_probability_deltas(joined: pd.DataFrame) -> pd.DataFrame:
    """Compare event-model and online-model output probabilities by stratum."""

    required = {
        "feature_view_id",
        "partition",
        "provenance_stratum",
        "online_p_LOW",
        "online_p_UNRES",
        "online_p_REF",
        "event_p_LOW",
        "event_p_UNRES",
        "event_p_REF",
        "sample_id",
    }
    _require_columns(joined, required, "paired event/online predictions")
    result = (
        joined.groupby(["feature_view_id", "partition", "provenance_stratum"], dropna=False)
        .agg(
            prediction_rows=("sample_id", "size"),
            unique_samples=("sample_id", "nunique"),
            online_mean_p_LOW=("online_p_LOW", "mean"),
            event_mean_p_LOW=("event_p_LOW", "mean"),
            online_mean_p_UNRES=("online_p_UNRES", "mean"),
            event_mean_p_UNRES=("event_p_UNRES", "mean"),
            online_mean_p_REF=("online_p_REF", "mean"),
            event_mean_p_REF=("event_p_REF", "mean"),
        )
        .reset_index()
    )
    result["delta_event_minus_online_p_LOW"] = result["event_mean_p_LOW"] - result["online_mean_p_LOW"]
    result["delta_event_minus_online_p_UNRES"] = result["event_mean_p_UNRES"] - result["online_mean_p_UNRES"]
    result["delta_event_minus_online_p_REF"] = result["event_mean_p_REF"] - result["online_mean_p_REF"]
    return result.sort_values(["feature_view_id", "partition", "provenance_stratum"], kind="stable").reset_index(drop=True).convert_dtypes()


def build_prediction_transitions(joined: pd.DataFrame) -> pd.DataFrame:
    """Count online-to-event hard prediction transitions by provenance."""

    required = {"feature_view_id", "partition", "provenance_stratum", "online_prediction_label", "event_prediction_label"}
    _require_columns(joined, required, "paired event/online predictions")
    return (
        joined.groupby(["feature_view_id", "partition", "provenance_stratum", "online_prediction_label", "event_prediction_label"], dropna=False)
        .size()
        .rename("row_count")
        .reset_index()
        .sort_values(["feature_view_id", "partition", "provenance_stratum", "online_prediction_label", "event_prediction_label"], kind="stable")
        .reset_index(drop=True)
        .convert_dtypes()
    )


def pair_event_online_predictions(online: pd.DataFrame, event: pd.DataFrame, provenance: pd.DataFrame) -> pd.DataFrame:
    """Pair event and online predictions and attach one shared provenance row."""

    join_keys = ["feature_view_id", "partition", "fold_id", "sample_id"]
    _require_columns(online, set(join_keys) | {"prediction_label", "p_LOW", "p_UNRES", "p_REF"}, "online predictions")
    _require_columns(event, set(join_keys) | {"prediction_label", "p_LOW", "p_UNRES", "p_REF"}, "event predictions")
    online_side = online.loc[:, join_keys + ["prediction_label", "p_LOW", "p_UNRES", "p_REF"]].rename(
        columns={
            "prediction_label": "online_prediction_label",
            "p_LOW": "online_p_LOW",
            "p_UNRES": "online_p_UNRES",
            "p_REF": "online_p_REF",
        }
    )
    event_side = event.loc[:, join_keys + ["prediction_label", "p_LOW", "p_UNRES", "p_REF"]].rename(
        columns={
            "prediction_label": "event_prediction_label",
            "p_LOW": "event_p_LOW",
            "p_UNRES": "event_p_UNRES",
            "p_REF": "event_p_REF",
        }
    )
    paired = online_side.merge(event_side, on=join_keys, how="inner", validate="one_to_one")
    paired = paired.merge(provenance, on="sample_id", how="inner", validate="many_to_one")
    if paired.empty:
        raise ValueError("No paired event/online prediction rows remain after provenance join.")
    return paired.sort_values(["feature_view_id", "partition", "sample_id"], kind="stable").reset_index(drop=True).convert_dtypes()


def _validate_provenance_contract(frame: pd.DataFrame) -> None:
    strata = set(frame["provenance_stratum"].dropna().astype(str))
    unexpected = strata - set(PROVENANCE_STRATA)
    if unexpected:
        raise ValueError(f"Unexpected provenance strata: {sorted(unexpected)}")
    low = frame.loc[frame["provenance_stratum"].eq("LOW")]
    if not low.empty and not low["online_label_name"].eq(LOW_LABEL).all():
        raise ValueError("LOW stratum contains a non-LOW online target.")
    if not low.empty and not (pd.to_numeric(low["support_depth_at_anchor"], errors="coerce") >= pd.to_numeric(low["required_k"], errors="coerce")).all():
        raise ValueError("LOW stratum contains a row below K.")
    u_a = frame.loc[frame["provenance_stratum"].eq("U_A")]
    if not u_a.empty and not u_a["unres_origin"].eq("UNRES_A").all():
        raise ValueError("U_A stratum has an unexpected origin.")
    if not u_a.empty and not u_a["online_label_name"].eq(UNRES_LABEL).all():
        raise ValueError("U_A stratum is not labeled UNRES online.")
    if not u_a.empty and not u_a["m_relation_to_q"].astype("string").eq("M_t>Q").all():
        raise ValueError("U_A stratum is not Q-negative.")
    if not u_a.empty and not (pd.to_numeric(u_a["aux_positive_count"], errors="coerce") > 0).all():
        raise ValueError("U_A stratum does not have auxiliary positive evidence.")
    u_k = frame.loc[frame["provenance_stratum"].isin(["U_K_succ", "U_K_fail"])]
    if not u_k.empty and not u_k["unres_origin"].eq("UNRES_K").all():
        raise ValueError("U_K stratum has an unexpected origin.")
    if not u_k.empty and not u_k["online_label_name"].eq(UNRES_LABEL).all():
        raise ValueError("U_K stratum is not labeled UNRES online.")
    if not u_k.empty and not (pd.to_numeric(u_k["support_depth_at_anchor"], errors="coerce") < pd.to_numeric(u_k["required_k"], errors="coerce")).all():
        raise ValueError("U_K stratum contains a row at or above K.")
    if not u_k.empty and not u_k["m_relation_to_q"].astype("string").eq("M_t<=Q").all():
        raise ValueError("U_K stratum is not Q-positive.")
    ref = frame.loc[frame["provenance_stratum"].eq("REF")]
    if not ref.empty and not ref["online_label_name"].eq(REF_LABEL).all():
        raise ValueError("REF stratum is not labeled REF online.")
    expected_event = frame["provenance_stratum"].map({"LOW": LOW_LABEL, "U_K_succ": LOW_LABEL, "U_K_fail": UNRES_LABEL, "U_A": UNRES_LABEL, "REF": REF_LABEL})
    if not frame["event_label_name"].astype("string").eq(expected_event.astype("string")).all():
        raise ValueError("Event target semantics do not match the five-strata contract.")


def _complete_prediction_summary(grouped: pd.DataFrame, value_name: str) -> pd.DataFrame:
    key = ["prediction_source", "feature_view_id", "partition", "provenance_stratum", "prediction_label"]
    levels = [
        sorted(grouped["prediction_source"].astype("string").unique().tolist()),
        sorted(grouped["feature_view_id"].astype("string").unique().tolist()),
        sorted(grouped["partition"].astype("string").unique().tolist()),
        PROVENANCE_STRATA,
        PREDICTION_LABELS,
    ]
    index = pd.MultiIndex.from_product(levels, names=key)
    result = grouped.set_index(key).reindex(index).reset_index()
    result[value_name] = result[value_name].fillna(0).astype("int64")
    return result.sort_values(key, kind="stable").reset_index(drop=True).convert_dtypes()


def _complete_group_summary(grouped: pd.DataFrame, value_columns: list[str]) -> pd.DataFrame:
    key = ["prediction_source", "feature_view_id", "partition", "provenance_stratum"]
    levels = [
        sorted(grouped["prediction_source"].astype("string").unique().tolist()),
        sorted(grouped["feature_view_id"].astype("string").unique().tolist()),
        sorted(grouped["partition"].astype("string").unique().tolist()),
        PROVENANCE_STRATA,
    ]
    index = pd.MultiIndex.from_product(levels, names=key)
    result = grouped.set_index(key).reindex(index).reset_index()
    for column in value_columns:
        if column in {"prediction_rows", "unique_samples"}:
            result[column] = result[column].fillna(0).astype("int64")
        else:
            result[column] = pd.to_numeric(result[column], errors="coerce")
    return result.sort_values(key, kind="stable").reset_index(drop=True).convert_dtypes()


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
    eventual = pd.to_numeric(row.get("eventual_run_length"), errors="coerce")
    required = pd.to_numeric(row.get("required_k"), errors="coerce")
    complete = row.get("run_complete")
    if pd.isna(eventual) or pd.isna(required) or pd.isna(complete) or not bool(complete):
        return "censored_or_unknown"
    return "successful" if int(eventual) >= int(required) else "failed"


def _probability_for(row: pd.Series, label_name: str) -> float:
    try:
        class_names = json.loads(str(row["class_names_json"]))
        probabilities = json.loads(str(row["prediction_probability_json"]))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Prediction probability JSON is malformed.") from exc
    if isinstance(probabilities, dict):
        value = probabilities.get(label_name)
    else:
        try:
            value = probabilities[class_names.index(label_name)]
        except (AttributeError, KeyError, TypeError, ValueError, IndexError) as exc:
            raise ValueError(f"Prediction probabilities do not contain {label_name}.") from exc
    if value is None:
        raise ValueError(f"Prediction probabilities do not contain {label_name}.")
    return float(value)


def _difference(left: object, right: object) -> float | None:
    if left is None or right is None or pd.isna(left) or pd.isna(right):
        return None
    return float(left) - float(right)


def _require_columns(frame: pd.DataFrame, required: set[str], name: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{name} is missing required columns: {missing}")
