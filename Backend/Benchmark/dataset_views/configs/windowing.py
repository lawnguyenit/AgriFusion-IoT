from __future__ import annotations

from dataclasses import dataclass


V2_CONTINUITY_POLICY_VERSION = "segment_cadence_x2_5_span_coverage_75.v2"
V2_CONTINUITY_THRESHOLD_MULTIPLIER = 2.5
V2_MIN_SPAN_COVERAGE_RATIO = 0.75

V2_MINIMAL_MEASUREMENT_CHANNELS: tuple[str, ...] = (
    "sht.temp_c",
    "sht.humidity_pct",
    "npk.soil_temp_c",
    "npk.soil_moisture_pct",
    "npk.ec",
)

V2_MEASUREMENT_CHANNELS: tuple[str, ...] = (
    "sht.temp_c",
    "sht.humidity_pct",
    "npk.soil_temp_c",
    "npk.soil_moisture_pct",
    "npk.ec",
    "npk.ph",
    "npk.n_proxy",
    "npk.p_proxy",
    "npk.k_proxy",
)

V2_BOUNDARY_RESET_COLUMNS: tuple[str, ...] = (
    "record.segment_boundary_before",
    "split.boundary_before",
)

V2_SENSOR_VALIDITY_COLUMNS: dict[str, str] = {
    "sht.": "sht.valid",
    "npk.": "npk.valid",
}


@dataclass(frozen=True)
class WindowHorizon:
    name: str
    hours: int
    min_valid_observations: int
    min_slope_observations: int
    min_span_coverage_ratio: float = V2_MIN_SPAN_COVERAGE_RATIO

    @property
    def seconds(self) -> int:
        return int(self.hours) * 3600

    @property
    def min_span_seconds(self) -> int:
        return int(round(self.seconds * float(self.min_span_coverage_ratio)))


V2_WINDOW_HORIZONS: tuple[WindowHorizon, ...] = (
    WindowHorizon(
        name="3h",
        hours=3,
        min_valid_observations=6,
        min_slope_observations=3,
    ),
    WindowHorizon(
        name="8h",
        hours=8,
        min_valid_observations=15,
        min_slope_observations=3,
    ),
)
