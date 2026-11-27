from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ..validation import (
    normalize_column_names,
    parse_millisecond_timestamps,
    reject_duplicate_keys,
    require_columns,
    stable_timestamp_sort,
)


@dataclass(frozen=True)
class AdaptedSource:
    canonical: pd.DataFrame
    excluded: pd.DataFrame
    audit: dict[str, object]


def build_stuard_candidate(source_dir: Path) -> AdaptedSource:
    env, env_excluded = _load_stream(source_dir / "stuard_environmental_data.csv", "environment")
    soil, soil_excluded = _load_stream(source_dir / "stuard_soil_data.csv", "soil")
    water, water_excluded = _load_stream(source_dir / "stuard_water_meter_data.csv", "water")

    require_columns(env, ["ts_generation", "device_identifier", "co2", "humidity", "pressure", "temperature", "battery"], source_name="Stuard environmental stream")
    require_columns(soil, ["ts_generation", "device_identifier", "line", "electrical_conductivity", "humidity", "temperature", "battery"], source_name="Stuard soil stream")
    require_columns(water, ["ts_generation", "device_identifier", "line", "current_volume"], source_name="Stuard water stream")

    for frame, name in ((soil, "soil"), (water, "water")):
        line = pd.to_numeric(frame["line"], errors="coerce")
        invalid_line = line.isna() | ~line.isin([1, 2, 3])
        if invalid_line.any():
            raise ValueError(
                f"Stuard {name} stream has {int(invalid_line.sum())} missing or unknown line identifiers; "
                "only lines 1, 2, and 3 can define an entity."
            )
        frame["line"] = line.astype("int64")

    for frame, name in ((soil, "soil"), (water, "water")):
        line = pd.to_numeric(frame["line"], errors="coerce")
        invalid_line = line.isna() | ~line.isin([1, 2, 3])
        if invalid_line.any():
            raise ValueError(
                f"Stuard {name} stream has {int(invalid_line.sum())} missing or unknown line identifiers; "
                "only lines 1, 2, and 3 can define an entity."
            )
        frame["line"] = line.astype("int64")

    env = _with_timestamps(env, "environment")
    soil = _with_timestamps(soil, "soil")
    water = _with_timestamps(water, "water")
    for frame, name, keys in (
        (env, "Stuard environmental stream", ["timestamp"]),
        (soil, "Stuard soil stream", ["line", "timestamp"]),
        (water, "Stuard water stream", ["line", "timestamp"]),
    ):
        reject_duplicate_keys(frame, keys, source_name=name)

    env = env.rename(columns={
        "device_identifier": "env_device_id",
        "timestamp": "environment_timestamp",
        "co2": "air_co2_ppm",
        "humidity": "air_humidity_pct",
        "pressure": "air_pressure_hpa",
        "temperature": "air_temperature_c",
        "battery": "env_battery_pct",
    })
    soil = soil.rename(columns={
        "device_identifier": "soil_device_id",
        "timestamp": "timestamp",
        "electrical_conductivity": "soil_ec_us_cm",
        "humidity": "soil_moisture_pct",
        "temperature": "soil_temperature_c",
        "battery": "soil_battery_pct",
    })
    water = water.rename(columns={
        "device_identifier": "water_device_id",
        "timestamp": "water_timestamp",
        "current_volume": "water_volume_m3",
    })

    left = stable_timestamp_sort(soil)
    water_right = stable_timestamp_sort(water.rename(columns={"water_timestamp": "timestamp"}))
    merged = pd.merge_asof(
        left,
        water_right[["timestamp", "line", "source_row_number", "water_device_id", "water_volume_m3"]].rename(
            columns={"timestamp": "water_timestamp", "source_row_number": "water_source_row_number"}
        ).sort_values(["water_timestamp", "water_source_row_number"], kind="stable"),
        left_on="timestamp",
        right_on="water_timestamp",
        by="line",
        direction="backward",
        tolerance=pd.Timedelta("8min"),
    )
    env_right = stable_timestamp_sort(env.rename(columns={"environment_timestamp": "timestamp"}))
    env_right = env_right.rename(columns={"timestamp": "environment_timestamp", "source_row_number": "environment_source_row_number"})
    merged = pd.merge_asof(
        stable_timestamp_sort(merged),
        env_right.sort_values(["environment_timestamp", "environment_source_row_number"], kind="stable"),
        left_on="timestamp",
        right_on="environment_timestamp",
        direction="backward",
        tolerance=pd.Timedelta("8min"),
        suffixes=("", "_environment"),
    )

    merged["sample_id"] = merged.apply(
        lambda row: f"stuard:line_{row['line']}:{int(row['timestamp'].value)}:{int(row['source_row_number'])}",
        axis=1,
    )
    merged["entity_id"] = merged["line"].map(lambda value: f"line_{int(value)}" if pd.notna(value) else pd.NA)
    merged["irrigation_regime_fraction"] = merged["line"].map({1: 1.0, 2: 0.6, 3: 0.3})
    merged["water_alignment_age_sec"] = (merged["timestamp"] - merged["water_timestamp"]).dt.total_seconds()
    merged["environment_alignment_age_sec"] = (merged["timestamp"] - merged["environment_timestamp"]).dt.total_seconds()
    merged["delta_t_min"] = merged.groupby("line", dropna=False)["timestamp"].diff().dt.total_seconds().div(60)
    median_delta = merged.groupby("line", dropna=False)["delta_t_min"].transform("median")
    merged["gap_flag"] = merged["delta_t_min"].gt(1.5 * median_delta).astype("boolean")

    audit = {
        "source_rows": {
            "environment": int(len(env) + len(env_excluded)),
            "soil": int(len(soil) + len(soil_excluded)),
            "water": int(len(water) + len(water_excluded)),
        },
        "parsed_source_rows": {"environment": int(len(env)), "soil": int(len(soil)), "water": int(len(water))},
        "repeated_header_rows_excluded": int(len(env_excluded) + len(soil_excluded) + len(water_excluded)),
        "canonical_rows": int(len(merged)),
        "water_unmatched_rows": int(merged["water_timestamp"].isna().sum()),
        "environment_unmatched_rows": int(merged["environment_timestamp"].isna().sum()),
        "water_future_matches": int((merged["water_alignment_age_sec"] < 0).fillna(False).sum()),
        "environment_future_matches": int((merged["environment_alignment_age_sec"] < 0).fillna(False).sum()),
        "feature_and_criterion_roles": {
            "measurements": ["soil_moisture_pct", "soil_temperature_c", "soil_ec_us_cm", "air_temperature_c", "air_humidity_pct", "air_co2_ppm", "air_pressure_hpa"],
            "acquisition_metadata": ["soil_battery_pct", "env_battery_pct", "delta_t_min", "gap_flag"],
            "group_or_transport": ["entity_id", "line", "irrigation_regime_fraction"],
            "posthoc_operational_evidence": ["water_volume_m3", "water_alignment_age_sec"],
        },
    }
    if audit["water_future_matches"] or audit["environment_future_matches"]:
        raise ValueError("Causal Stuard join invariant failed: a source measurement occurs after its soil anchor.")

    keep = [
        "sample_id", "timestamp", "source_row_number", "entity_id", "line", "irrigation_regime_fraction",
        "soil_moisture_pct", "soil_temperature_c", "soil_ec_us_cm", "soil_battery_pct",
        "water_volume_m3", "water_timestamp", "water_alignment_age_sec", "water_device_id",
        "air_temperature_c", "air_humidity_pct", "air_co2_ppm", "air_pressure_hpa",
        "environment_timestamp", "environment_alignment_age_sec", "env_device_id", "env_battery_pct",
        "soil_device_id", "delta_t_min", "gap_flag",
    ]
    excluded = pd.concat([env_excluded, soil_excluded, water_excluded], ignore_index=True).convert_dtypes()
    return AdaptedSource(merged.loc[:, keep].convert_dtypes(), excluded, audit)


def _load_stream(path: Path, name: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not path.is_file():
        raise FileNotFoundError(f"Stuard {name} source file is missing: {path}")
    frame = normalize_column_names(pd.read_csv(path, low_memory=False))
    frame["source_row_number"] = range(1, len(frame) + 1)
    repeated_header = pd.Series(False, index=frame.index)
    if {"ts_generation", "device_identifier"}.issubset(frame.columns):
        repeated_header = (
            frame["ts_generation"].astype("string").str.strip().str.lower().eq("ts_generation")
            & frame["device_identifier"].astype("string").str.strip().str.lower().eq("device_identifier")
        )
        if "line" in frame:
            repeated_header &= frame["line"].astype("string").str.strip().str.lower().eq("line")
    excluded = pd.DataFrame(
        {
            "source_stream": name,
            "source_row_number": frame.loc[repeated_header, "source_row_number"],
            "exclusion_reason": "REPEATED_HEADER",
        }
    )
    return frame.loc[~repeated_header].copy(), excluded


def _with_timestamps(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    frame = frame.copy()
    frame["timestamp"] = parse_millisecond_timestamps(frame["ts_generation"])
    invalid = frame["timestamp"].isna()
    if invalid.any():
        raise ValueError(f"Stuard {name} stream has {int(invalid.sum())} rows with invalid ts_generation; raw files remain untouched.")
    return frame
