from __future__ import annotations

from math import pi

import numpy as np
import pandas as pd


def build_local_time_features(local_datetimes: pd.Series) -> pd.DataFrame:
    hour_fraction = (
        local_datetimes.dt.hour
        + (local_datetimes.dt.minute / 60.0)
        + (local_datetimes.dt.second / 3600.0)
    )
    day_of_week = local_datetimes.dt.dayofweek.astype(float)

    return pd.DataFrame(
        {
            "hour_sin": np.sin((2.0 * pi * hour_fraction) / 24.0),
            "hour_cos": np.cos((2.0 * pi * hour_fraction) / 24.0),
            "dayofweek_sin": np.sin((2.0 * pi * day_of_week) / 7.0),
            "dayofweek_cos": np.cos((2.0 * pi * day_of_week) / 7.0),
        },
        index=local_datetimes.index,
    )


def build_gap_minutes_since_prev(timestamp_utc: pd.Series) -> pd.Series:
    return timestamp_utc.diff().dt.total_seconds().div(60.0).fillna(0.0).clip(lower=0.0)
