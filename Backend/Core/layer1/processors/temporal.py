from __future__ import annotations

import math
from datetime import datetime

import pandas as pd

try:
    from Config.runtime import BACKEND_SETTINGS
except ModuleNotFoundError:
    from ....Config.runtime import BACKEND_SETTINGS

from ..contracts import TemporalSettings
from .common import as_int_from_pd


def apply_temporal_features(
    canonical_df: pd.DataFrame,
    temporal_settings: TemporalSettings,
) -> tuple[pd.DataFrame, int]:
    if canonical_df.empty:
        return canonical_df, 0

    dataframe = canonical_df.copy()
    order_sample = pd.to_numeric(dataframe["record.ts_sample"], errors="coerce")
    order_server = pd.to_numeric(dataframe["record.ts_server"], errors="coerce")
    dataframe["_order_ts"] = order_sample.fillna(order_server)
    dataframe = dataframe.sort_values(
        ["record.node_id", "_order_ts", "record.event_key"],
        kind="stable",
        na_position="last",
    ).reset_index(drop=True)

    prev_sample_by_node: dict[str, int | None] = {}
    for index, row in dataframe.iterrows():
        node_id = str(row["record.node_id"])
        ts_sample = as_int_from_pd(row["record.ts_sample"])
        ts_server = as_int_from_pd(row["record.ts_server"])

        if ts_sample is not None and ts_server is not None:
            dataframe.at[index, "record.upload_delay_sec"] = ts_server - ts_sample

        previous_ts = prev_sample_by_node.get(node_id)
        if ts_sample is not None and previous_ts is not None and ts_sample > previous_ts:
            delta_prev = ts_sample - previous_ts
            dataframe.at[index, "record.delta_prev_sec"] = delta_prev
            dataframe.at[index, "record.gap_flag"] = (
                delta_prev > temporal_settings.gap_threshold_sec
            )
            missing_slot_count = max(
                round(delta_prev / temporal_settings.expected_interval_sec) - 1,
                0,
            )
            dataframe.at[index, "record.missing_slot_count"] = missing_slot_count

        if ts_sample is not None:
            local_dt = datetime.fromtimestamp(ts_sample, tz=BACKEND_SETTINGS.timezone)
            hour_fraction = (
                local_dt.hour
                + (local_dt.minute / 60.0)
                + (local_dt.second / 3600.0)
            )
            dataframe.at[index, "record.hour_sin"] = math.sin(
                (2.0 * math.pi * hour_fraction) / 24.0
            )
            dataframe.at[index, "record.hour_cos"] = math.cos(
                (2.0 * math.pi * hour_fraction) / 24.0
            )
            prev_sample_by_node[node_id] = ts_sample

    dataframe = dataframe.drop(columns=["_order_ts"])
    duplicate_count = int(dataframe["record.id"].duplicated().sum())
    return dataframe, duplicate_count
