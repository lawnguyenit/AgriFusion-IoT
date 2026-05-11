from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.fuzzy_logic_basic.shared.timeseries import rolling_time_slope


def main() -> None:
    timestamps = pd.to_datetime(
        [
            "2026-04-02 08:00:00+00:00",
            "2026-04-02 08:30:00+00:00",
            "2026-04-02 09:15:00+00:00",
            "2026-04-02 10:00:00+00:00",
            "2026-04-02 11:00:00+00:00",
        ]
    )

    soil_humidity = pd.Series([72.0, 70.5, 68.0, 66.2, 64.8])

    slope = rolling_time_slope(
        soil_humidity,
        timestamps,
        window_hours=3,
        min_points=3,
    )

    example = pd.DataFrame(
        {
            "timestamp": timestamps,
            "soil_humidity": soil_humidity,
            "soil_humidity_slope_3h": slope,
        }
    )

    print("Example 1: rolling_time_slope over a 3h window")
    print(example.to_string(index=False))
    print()

    window = pd.Series(
        [72.0, 70.5, 68.0],
        index=pd.DatetimeIndex(
            [
                "2026-04-02 08:00:00+00:00",
                "2026-04-02 08:30:00+00:00",
                "2026-04-02 09:15:00+00:00",
            ]
        ),
    )
    x_hours = (window.index - window.index[0]).total_seconds() / 3600.0
    print("Example 2: relative x-axis inside one rolling window")
    print("window values:", window.to_list())
    print("x_hours:", x_hours.to_list())
    print("Here x_hours starts at 0.0 and measures each point relative to the oldest point in the window.")


if __name__ == "__main__":
    main()
