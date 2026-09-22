from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


COMPARISON_PAIRS: tuple[tuple[str, str], ...] = (
    ("ts_sample", "record.ts_sample"),
    ("event_key", "record.event_key"),
    ("air_temp_c", "sht.temp_c"),
    ("air_rh_pct", "sht.humidity_pct"),
    ("soil_moisture_pct", "npk.soil_moisture_pct"),
    ("soil_temp_c", "npk.soil_temp_c"),
    ("soil_ec_us_cm", "npk.ec"),
    ("soil_n_proxy", "npk.n_proxy"),
    ("soil_p_proxy", "npk.p_proxy"),
    ("soil_k_proxy", "npk.k_proxy"),
    ("soil_ph", "npk.ph"),
)


def build_audit(
    source: pd.DataFrame,
    old_canonical: pd.DataFrame,
    candidate: pd.DataFrame,
) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    source = source.copy()
    old = old_canonical.copy()
    source["record.id"] = _candidate_ids(source)
    old["record.id"] = old["record.id"].astype("string")

    new_ids = set(source["record.id"].dropna())
    old_ids = set(old["record.id"].dropna())
    shared_ids = new_ids & old_ids

    summary = {
        "source_rows": int(len(source)),
        "source_columns": int(len(source.columns) - 1),
        "old_rows": int(len(old)),
        "old_columns": int(len(old.columns) - 1),
        "candidate_rows": int(len(candidate)),
        "source_date_min": _date_min(source["date_local"]),
        "source_date_max": _date_max(source["date_local"]),
        "old_date_min": _date_min(old["record.sample_time_local"]),
        "old_date_max": _date_max(old["record.sample_time_local"]),
        "source_has_ts_server": "ts_server" in source.columns,
        "source_has_upload_time": "upload_time_local" in source.columns,
        "shared_key_count": len(shared_ids),
        "new_only_key_count": len(new_ids - old_ids),
        "old_only_key_count": len(old_ids - new_ids),
        "source_duplicate_id_rows": int(source["record.id"].duplicated(keep=False).sum()),
        "old_duplicate_id_rows": int(old["record.id"].duplicated(keep=False).sum()),
        "source_duplicate_event_key_rows": int(source["event_key"].duplicated(keep=False).sum()),
        "source_duplicate_ts_sample_rows": int(source["ts_sample"].duplicated(keep=False).sum()),
        "source_duplicate_ts_sample_values": int(source["ts_sample"].duplicated(keep=False).groupby(source["ts_sample"]).any().sum()),
        "buffered_rows": int(_bool(source, "buffered").fillna(False).sum()),
        "replayed_rows": int(_bool(source, "replayed").fillna(False).sum()),
        "buffered_or_replayed_rows": int((_bool(source, "buffered") | _bool(source, "replayed")).fillna(False).sum()),
        "all_core_sensor_missing_rows": int(source[list(_source_sensor_columns())].isna().all(axis=1).sum()),
        "replayed_rows_with_any_sensor_value": int(
            ((_bool(source, "replayed").fillna(False)) & ~source[list(_source_sensor_columns())].isna().all(axis=1)).sum()
        ),
        "rows_with_any_missing_status_flag": int(source[_status_columns(source)].isna().any(axis=1).sum()),
        "time_reconstructed_rows": int(_bool(source, "time_reconstructed").fillna(False).sum()),
        "gap_gt_30m_rows": int(_bool(source, "gap_gt_30m").fillna(False).sum()),
        "gap_gt_60m_rows": int(_bool(source, "gap_gt_60m").fillna(False).sum()),
        "export_key_corruption_rows": int(_bool(source, "export_key_corruption_flag").fillna(False).sum()),
        "out_of_range_rows": _range_anomaly_count(source),
        "source_all_null_columns": [column for column in source.columns if column != "record.id" and source[column].isna().all()],
        "delta_recompute_max_abs_diff_min": _delta_recompute_max_abs_diff(source),
        "delta_recompute_mismatch_rows": _delta_recompute_mismatch_rows(source),
        "candidate_columns": int(len(candidate.columns)),
        "candidate_missing_values": int(candidate.isna().sum().sum()),
    }

    comparisons = _build_comparison_table(source, old, shared_ids)
    gap_events, gap_metrics = _build_gap_events(source)
    sensorless_runs, sensorless_metrics = _build_sensorless_runs(source)
    replay_delay, replay_metrics = _build_replay_delay(source)
    summary.update(gap_metrics)
    summary.update(sensorless_metrics)
    summary.update(replay_metrics)
    missingness = pd.DataFrame(
        {
            "column": [column for column in source.columns if column != "record.id"],
            "null_rows": [int(source[column].isna().sum()) for column in source.columns if column != "record.id"],
            "null_ratio": [float(source[column].isna().mean()) for column in source.columns if column != "record.id"],
            "dtype": [str(source[column].dtype) for column in source.columns if column != "record.id"],
        }
    ).sort_values(["null_ratio", "column"], ascending=[False, True], ignore_index=True)
    date_counts = source.groupby("date_local", dropna=False).size().rename("rows").reset_index()
    date_counts["buffered_or_replayed"] = source.groupby("date_local", dropna=False).apply(
        lambda frame: int((_bool(frame, "buffered") | _bool(frame, "replayed")).fillna(False).sum()),
        include_groups=False,
    ).to_numpy()
    date_counts["all_core_sensor_missing"] = source.groupby("date_local", dropna=False).apply(
        lambda frame: int(frame[list(_source_sensor_columns())].isna().all(axis=1).sum()),
        include_groups=False,
    ).to_numpy()

    status_counts = _build_status_counts(source)
    duplicate_timestamps = source.loc[
        source["ts_sample"].duplicated(keep=False),
        ["record.id", "event_key", "ts_sample", "sample_time_local_iso", "buffered", "replayed", "time_reconstructed"],
    ].sort_values(["ts_sample", "event_key"])
    new_only = source.loc[~source["record.id"].isin(old_ids)].sort_values(["ts_sample", "event_key"])
    anomaly_rows = _build_anomaly_rows(source)

    details = {
        "value_comparison": comparisons,
        "missingness": missingness,
        "date_counts": date_counts,
        "status_counts": status_counts,
        "duplicate_timestamps": duplicate_timestamps,
        "new_only_rows": new_only,
        "anomaly_rows": anomaly_rows,
        "gap_events": gap_events,
        "sensorless_runs": sensorless_runs,
        "replay_delay": replay_delay,
    }
    return summary, details


def _candidate_ids(source: pd.DataFrame) -> pd.Series:
    return (
        source["node_id"].astype("string")
        + ":"
        + source["raw_date_key"].astype("string")
        + ":"
        + pd.to_numeric(source["event_key"], errors="coerce").astype("Int64").astype("string")
    )


def _source_sensor_columns() -> tuple[str, ...]:
    return (
        "air_temp_c",
        "air_rh_pct",
        "soil_moisture_pct",
        "soil_temp_c",
        "soil_ec_us_cm",
        "soil_ph",
    )


def _status_columns(source: pd.DataFrame) -> list[str]:
    return [
        column
        for column in (
            "time_valid",
            "registered",
            "attached",
            "pdp_active",
            "air_read_ok",
            "air_sample_valid",
            "soil_moisture_valid",
            "soil_temp_valid",
            "soil_ec_valid",
            "soil_ph_valid",
            "soil_read_ok",
            "soil_sample_valid",
        )
        if column in source.columns
    ]


def _bool(source: pd.DataFrame, column: str) -> pd.Series:
    if column not in source:
        return pd.Series(False, index=source.index, dtype="boolean")
    return source[column].map(_coerce_bool).astype("boolean")


def _coerce_bool(value: Any) -> bool | pd._libs.missing.NAType:
    if value is None or pd.isna(value):
        return pd.NA
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _date_min(series: pd.Series) -> str | None:
    values = pd.to_datetime(series, errors="coerce")
    return None if values.dropna().empty else str(values.min().date())


def _date_max(series: pd.Series) -> str | None:
    values = pd.to_datetime(series, errors="coerce")
    return None if values.dropna().empty else str(values.max().date())


def _build_comparison_table(
    source: pd.DataFrame,
    old: pd.DataFrame,
    shared_ids: set[Any],
) -> pd.DataFrame:
    source_indexed = source.set_index("record.id")
    old_indexed = old.set_index("record.id")
    shared_index = source_indexed.index.intersection(old_indexed.index)
    rows: list[dict[str, Any]] = []
    for source_column, old_column in COMPARISON_PAIRS:
        left = pd.to_numeric(source_indexed.loc[shared_index, source_column], errors="coerce")
        right = pd.to_numeric(old_indexed.loc[shared_index, old_column], errors="coerce")
        both = left.notna() & right.notna()
        difference = (left - right).abs()
        rows.append(
            {
                "source_column": source_column,
                "old_column": old_column,
                "shared_rows": int(len(shared_index)),
                "both_numeric_rows": int(both.sum()),
                "exact_rows": int((both & (difference <= 1e-9)).sum()),
                "mismatch_rows": int((both & (difference > 1e-9)).sum()),
                "source_missing_old_present": int((~left.notna() & right.notna()).sum()),
                "old_missing_source_present": int((left.notna() & ~right.notna()).sum()),
                "max_abs_difference": float(difference[both].max()) if both.any() else None,
            }
        )
    return pd.DataFrame(rows)


def _build_status_counts(source: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for column in _status_columns(source) + ["buffered", "replayed", "gap_gt_30m", "gap_gt_60m"]:
        if column not in source:
            continue
        counts = source[column].value_counts(dropna=False)
        for value, count in counts.items():
            rows.append({"column": column, "value": _json_value(value), "rows": int(count)})
    return pd.DataFrame(rows)


def _build_anomaly_rows(source: pd.DataFrame) -> pd.DataFrame:
    sensorless = source[list(_source_sensor_columns())].isna().all(axis=1)
    status_missing = source[_status_columns(source)].isna().any(axis=1)
    range_bad = (
        source["soil_moisture_pct"].lt(0)
        | source["soil_moisture_pct"].gt(100)
        | source["air_rh_pct"].lt(0)
        | source["air_rh_pct"].gt(100)
        | source["soil_ph"].lt(0)
        | source["soil_ph"].gt(14)
    ).fillna(False)
    mask = sensorless | status_missing | range_bad | source["ts_sample"].duplicated(keep=False)
    columns = [
        "record.id",
        "event_key",
        "ts_sample",
        "date_local",
        "buffered",
        "replayed",
        "time_reconstructed",
        "soil_sample_valid",
        "air_sample_valid",
        "delta_min",
        "gap_gt_30m",
        "gap_gt_60m",
        "duplicate_timestamp_flag",
    ]
    return source.loc[mask, [column for column in columns if column in source.columns]].sort_values(
        ["ts_sample", "event_key"]
    )


def _prepare_temporal_source(source: pd.DataFrame) -> pd.DataFrame:
    ordered = source.sort_values(
        ["node_id", "ts_sample", "event_key"],
        kind="stable",
    ).reset_index(drop=True).copy()
    ordered["sample_dt"] = pd.to_datetime(
        ordered["ts_sample"], unit="s", errors="coerce", utc=True
    ).dt.tz_convert("Asia/Ho_Chi_Minh")
    ordered["previous_sample_dt"] = ordered.groupby("node_id")["sample_dt"].shift(1)
    ordered["delta_sec_recomputed"] = ordered.groupby("node_id")["ts_sample"].diff()
    ordered["delta_min_recomputed"] = ordered["delta_sec_recomputed"] / 60.0
    ordered["event_key_minus_ts_sample_sec"] = (
        pd.to_numeric(ordered["event_key"], errors="coerce")
        - pd.to_numeric(ordered["ts_sample"], errors="coerce")
    )
    ordered["sensorless"] = ordered[list(_source_sensor_columns())].isna().all(axis=1)
    ordered["buffered_bool"] = _bool(ordered, "buffered").fillna(False)
    ordered["replayed_bool"] = _bool(ordered, "replayed").fillna(False)
    return ordered


def _estimate_direct_cadence_sec(ordered: pd.DataFrame) -> float:
    clean = ordered.loc[
        (~ordered["buffered_bool"])
        & ordered["delta_sec_recomputed"].gt(0)
        & ordered["delta_sec_recomputed"].le(1800),
        "delta_sec_recomputed",
    ].dropna()
    if clean.empty:
        return 900.0
    return float(clean.median())


def _build_gap_events(source: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    ordered = _prepare_temporal_source(source)
    direct_cadence_sec = _estimate_direct_cadence_sec(ordered)
    gaps = ordered.loc[ordered["delta_min_recomputed"].gt(30)].copy()
    gaps["gap_event_id"] = range(1, len(gaps) + 1)
    gaps["expected_direct_interval_sec"] = direct_cadence_sec
    gaps["estimated_missed_slots"] = (
        (gaps["delta_sec_recomputed"] / direct_cadence_sec).round() - 1
    ).clip(lower=0).astype("Int64")
    gaps["classification"] = "gap_into_direct_sensorless"
    gaps.loc[gaps["buffered_bool"] & gaps["sensorless"], "classification"] = "gap_into_replay_sensorless"
    gaps.loc[gaps["buffered_bool"] & ~gaps["sensorless"], "classification"] = "gap_into_replay_sensorful"
    gaps.loc[~gaps["buffered_bool"] & ~gaps["sensorless"], "classification"] = "gap_into_direct_sensorful"

    ordered_positions = ordered.index.to_series()
    next_direct_sensorful: list[bool] = []
    next_sensorful: list[bool] = []
    for position in gaps.index:
        following = ordered.iloc[position + 1 : position + 11]
        next_direct_sensorful.append(bool((~following["buffered_bool"] & ~following["sensorless"]).any()))
        next_sensorful.append(bool((~following["sensorless"]).any()))
    gaps["sensorful_within_next_10_rows"] = next_sensorful
    gaps["direct_sensorful_within_next_10_rows"] = next_direct_sensorful

    output_columns = [
        "gap_event_id",
        "record.id",
        "node_id",
        "previous_sample_dt",
        "sample_dt",
        "delta_min_recomputed",
        "expected_direct_interval_sec",
        "estimated_missed_slots",
        "classification",
        "buffered_bool",
        "replayed_bool",
        "sensorless",
        "sensorful_within_next_10_rows",
        "direct_sensorful_within_next_10_rows",
        "event_key_minus_ts_sample_sec",
        "direct_upload_ok",
        "wake_reason",
    ]
    output = gaps.loc[:, [column for column in output_columns if column in gaps.columns]].rename(
        columns={
            "previous_sample_dt": "gap_start_local",
            "sample_dt": "gap_end_local",
            "delta_min_recomputed": "gap_minutes",
            "buffered_bool": "current_buffered",
            "replayed_bool": "current_replayed",
            "sensorless": "current_sensorless",
        }
    )
    metrics = {
        "direct_expected_interval_sec_for_gap_audit": direct_cadence_sec,
        "gap_event_count_gt_30m": int(len(gaps)),
        "gap_event_count_gt_60m": int(gaps["delta_min_recomputed"].gt(60).sum()),
        "gap_event_max_minutes": float(gaps["delta_min_recomputed"].max()) if not gaps.empty else 0.0,
        "gap_into_replay_sensorless_count": int((gaps["classification"] == "gap_into_replay_sensorless").sum()),
        "gap_into_replay_sensorful_count": int((gaps["classification"] == "gap_into_replay_sensorful").sum()),
        "gap_into_direct_sensorful_count": int((gaps["classification"] == "gap_into_direct_sensorful").sum()),
        "gap_into_direct_sensorless_count": int((gaps["classification"] == "gap_into_direct_sensorless").sum()),
        "largest_gap_start_local": _timestamp_text(gaps["previous_sample_dt"].loc[gaps["delta_min_recomputed"].idxmax()]) if not gaps.empty else None,
        "largest_gap_end_local": _timestamp_text(gaps["sample_dt"].loc[gaps["delta_min_recomputed"].idxmax()]) if not gaps.empty else None,
    }
    return output.sort_values(["gap_minutes", "gap_end_local"], ascending=[False, True]), metrics


def _build_sensorless_runs(source: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    ordered = _prepare_temporal_source(source)
    state = ordered["node_id"].astype("string") + "|" + ordered["sensorless"].astype("string")
    ordered["state_transition"] = state.ne(state.shift(1)).fillna(True)
    ordered["state_run_id"] = ordered["state_transition"].cumsum()
    sensorless = ordered.loc[ordered["sensorless"]].copy()
    if sensorless.empty:
        return pd.DataFrame(), {
            "sensorless_run_count": 0,
            "sensorless_run_gt_6h": 0,
            "sensorless_run_gt_24h": 0,
            "sensorless_run_max_minutes": 0.0,
            "sensorless_run_max_rows": 0,
        }

    rows: list[dict[str, Any]] = []
    for run_id, frame in sensorless.groupby("state_run_id", sort=False):
        start = frame["sample_dt"].iloc[0]
        end = frame["sample_dt"].iloc[-1]
        span_minutes = float((end - start).total_seconds() / 60.0)
        rows.append(
            {
                "sensorless_run_id": int(run_id),
                "node_id": str(frame["node_id"].iloc[0]),
                "start_local": _timestamp_text(start),
                "end_local": _timestamp_text(end),
                "row_count": int(len(frame)),
                "span_minutes": span_minutes,
                "max_internal_gap_minutes": float(frame["delta_min_recomputed"].max()) if len(frame) > 1 else 0.0,
                "buffered_rows": int(frame["buffered_bool"].sum()),
                "replayed_rows": int(frame["replayed_bool"].sum()),
                "missing_status_rows": int(frame[_status_columns(frame)].isna().any(axis=1).sum()),
            }
        )
    output = pd.DataFrame(rows).sort_values(["span_minutes", "start_local"], ascending=[False, True])
    max_span_row = output.loc[output["span_minutes"].idxmax()]
    max_row_count = output.loc[output["row_count"].idxmax()]
    metrics = {
        "sensorless_run_count": int(len(output)),
        "sensorless_run_gt_6h": int(output["span_minutes"].gt(360).sum()),
        "sensorless_run_gt_24h": int(output["span_minutes"].gt(1440).sum()),
        "sensorless_run_max_minutes": float(output["span_minutes"].max()),
        "sensorless_run_max_rows": int(output["row_count"].max()),
        "sensorless_run_max_start_local": str(max_span_row["start_local"]),
        "sensorless_run_max_end_local": str(max_span_row["end_local"]),
        "sensorless_run_max_rows_start_local": str(max_row_count["start_local"]),
        "sensorless_run_max_rows_end_local": str(max_row_count["end_local"]),
        "sensorless_run_max_rows_span_minutes": float(max_row_count["span_minutes"]),
    }
    return output, metrics


def _build_replay_delay(source: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    ordered = _prepare_temporal_source(source)
    replay = ordered.loc[ordered["buffered_bool"] | ordered["replayed_bool"]].copy()
    output_columns = [
        "record.id",
        "node_id",
        "sample_dt",
        "event_key",
        "ts_sample",
        "event_key_minus_ts_sample_sec",
        "sensorless",
        "direct_upload_ok",
        "soil_sample_valid",
    ]
    output = replay.loc[:, [column for column in output_columns if column in replay.columns]].sort_values(
        "event_key_minus_ts_sample_sec", ascending=False
    )
    delay = pd.to_numeric(output["event_key_minus_ts_sample_sec"], errors="coerce")
    metrics = {
        "replay_delay_proxy_gt_120_sec": int(delay.gt(120).sum()),
        "replay_delay_proxy_gt_1h": int(delay.gt(3600).sum()),
        "replay_delay_proxy_gt_1d": int(delay.gt(86400).sum()),
        "replay_delay_proxy_max_sec": float(delay.max()) if not delay.dropna().empty else 0.0,
        "direct_median_interval_sec": _median_interval(ordered, buffered=False),
        "replay_median_interval_sec": _median_interval(ordered, buffered=True),
    }
    return output, metrics


def _median_interval(ordered: pd.DataFrame, *, buffered: bool) -> float | None:
    values = ordered.loc[
        ordered["buffered_bool"].eq(buffered)
        & ordered["delta_sec_recomputed"].gt(0)
        & ordered["delta_sec_recomputed"].le(1800),
        "delta_sec_recomputed",
    ].dropna()
    return None if values.empty else float(values.median())


def _timestamp_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    return str(value)


def _range_anomaly_count(source: pd.DataFrame) -> int:
    mask = (
        source["soil_moisture_pct"].lt(0)
        | source["soil_moisture_pct"].gt(100)
        | source["air_rh_pct"].lt(0)
        | source["air_rh_pct"].gt(100)
        | source["soil_ph"].lt(0)
        | source["soil_ph"].gt(14)
    ).fillna(False)
    return int(mask.sum())


def _delta_recompute(source: pd.DataFrame) -> pd.DataFrame:
    ordered = source.sort_values(["node_id", "ts_sample", "event_key"], kind="stable").copy()
    ordered["recomputed_delta_min"] = ordered.groupby("node_id")["ts_sample"].diff() / 60.0
    ordered["delta_abs_diff"] = (
        pd.to_numeric(ordered["delta_min"], errors="coerce") - ordered["recomputed_delta_min"]
    ).abs()
    return ordered


def _delta_recompute_max_abs_diff(source: pd.DataFrame) -> float | None:
    values = _delta_recompute(source)["delta_abs_diff"].dropna()
    return None if values.empty else float(values.max())


def _delta_recompute_mismatch_rows(source: pd.DataFrame) -> int:
    values = _delta_recompute(source)["delta_abs_diff"].dropna()
    return int((values > 1e-6).sum())


def _json_value(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value
