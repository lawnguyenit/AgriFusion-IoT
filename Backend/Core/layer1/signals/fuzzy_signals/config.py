from __future__ import annotations

from dataclasses import asdict
from typing import Any

try:
    from .engine import SignalRule
except ImportError:
    from engine import SignalRule

RULESET_VERSION = "layer1_rules_v1"
DEFAULT_WINDOW_HOURS = (3, 6, 24, 72)

NPK_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "n_ppm": ("n_ppm", "N", "n", "nitrogen"),
    "p_ppm": ("p_ppm", "P", "p", "phosphorus"),
    "k_ppm": ("k_ppm", "K", "k", "potassium"),
    "soil_temp_c": ("soil_temp_c", "temp", "soil_temp", "soil_temperature"),
    "soil_humidity_pct": ("soil_humidity_pct", "hum", "humidity", "soil_moisture"),
    "soil_ph": ("soil_ph", "ph", "pH"),
    "soil_ec_us_cm": ("soil_ec_us_cm", "ec", "soil_ec"),
}

SHT30_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "temp_air_c": ("temp_air_c", "sht_temp_c", "temperature", "temp"),
    "humidity_air_pct": ("humidity_air_pct", "sht_hum_pct", "humidity", "rh"),
}

METEO_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "temp_air_c": ("temp_air_c", "temperature_2m", "temperature", "temp"),
    "humidity_air_pct": (
        "humidity_air_pct",
        "relative_humidity_2m",
        "humidity",
        "rh",
    ),
    "rain_mm": ("rain_mm", "rain", "precipitation", "precipitation_mm"),
    "dew_point_c": ("dew_point_c", "dew_point_2m", "dew_point"),
    "cloud_cover_pct": ("cloud_cover_pct", "cloud_cover"),
    "et0_mm": ("et0_mm", "et0_fao_evapotranspiration", "et0"),
}

NPK_SIGNAL_RULES: tuple[SignalRule, ...] = (
    SignalRule(
        name="nitrogen_low_leaning",
        field="n_ppm",
        normal_low=80,
        normal_high=140,
        threshold_low=50,
        direction="low",
        alpha=0.25,
        unit="ppm",
    ),
    SignalRule(
        name="phosphorus_low_leaning",
        field="p_ppm",
        normal_low=60,
        normal_high=120,
        threshold_low=35,
        direction="low",
        alpha=0.25,
        unit="ppm",
    ),
    SignalRule(
        name="potassium_low_leaning",
        field="k_ppm",
        normal_low=80,
        normal_high=160,
        threshold_low=45,
        direction="low",
        alpha=0.25,
        unit="ppm",
    ),
    SignalRule(
        name="soil_moisture_dry_leaning",
        field="soil_humidity_pct",
        normal_low=60,
        normal_high=80,
        threshold_low=40,
        direction="low",
        alpha=0.25,
        unit="pct",
    ),
    SignalRule(
        name="soil_moisture_wet_leaning",
        field="soil_humidity_pct",
        normal_low=60,
        normal_high=80,
        threshold_high=90,
        direction="high",
        alpha=0.25,
        unit="pct",
    ),
    SignalRule(
        name="soil_ph_acid_leaning",
        field="soil_ph",
        normal_low=5.5,
        normal_high=6.5,
        threshold_low=4.5,
        direction="low",
        alpha=0.2,
        unit="pH",
    ),
    SignalRule(
        name="soil_ph_alkaline_leaning",
        field="soil_ph",
        normal_low=5.5,
        normal_high=6.5,
        threshold_high=7.5,
        direction="high",
        alpha=0.2,
        unit="pH",
    ),
    SignalRule(
        name="soil_salinity_high_leaning",
        field="soil_ec_us_cm",
        normal_low=0,
        normal_high=850,
        threshold_high=1000,
        direction="high",
        alpha=0.2,
        unit="us/cm",
    ),
)

SHT30_SIGNAL_RULES: tuple[SignalRule, ...] = (
    SignalRule(
        name="air_temperature_cold_leaning",
        field="temp_air_c",
        normal_low=24,
        normal_high=30,
        threshold_low=13,
        direction="low",
        alpha=0.25,
        unit="C",
    ),
    SignalRule(
        name="air_temperature_heat_leaning",
        field="temp_air_c",
        normal_low=24,
        normal_high=30,
        threshold_high=35,
        direction="high",
        alpha=0.25,
        unit="C",
    ),
    SignalRule(
        name="air_humidity_dry_leaning",
        field="humidity_air_pct",
        normal_low=60,
        normal_high=85,
        threshold_low=45,
        direction="low",
        alpha=0.25,
        unit="pct",
    ),
    SignalRule(
        name="air_humidity_wet_leaning",
        field="humidity_air_pct",
        normal_low=60,
        normal_high=85,
        threshold_high=95,
        direction="high",
        alpha=0.25,
        unit="pct",
    ),
    SignalRule(
        name="condensation_humidity_pressure",
        field="humidity_air_pct",
        normal_low=55,
        normal_high=85,
        threshold_high=92,
        direction="high",
        alpha=0.3,
        unit="pct",
    ),
)

METEO_SIGNAL_RULES: tuple[SignalRule, ...] = (
    SignalRule(
        name="meteo_temperature_cold_leaning",
        field="temp_air_c",
        normal_low=24,
        normal_high=30,
        threshold_low=13,
        direction="low",
        alpha=0.25,
        unit="C",
    ),
    SignalRule(
        name="meteo_temperature_heat_leaning",
        field="temp_air_c",
        normal_low=24,
        normal_high=30,
        threshold_high=35,
        direction="high",
        alpha=0.25,
        unit="C",
    ),
    SignalRule(
        name="meteo_humidity_dry_leaning",
        field="humidity_air_pct",
        normal_low=60,
        normal_high=85,
        threshold_low=45,
        direction="low",
        alpha=0.25,
        unit="pct",
    ),
    SignalRule(
        name="meteo_humidity_wet_leaning",
        field="humidity_air_pct",
        normal_low=60,
        normal_high=85,
        threshold_high=95,
        direction="high",
        alpha=0.25,
        unit="pct",
    ),
    SignalRule(
        name="rain_event_accumulation",
        field="rain_mm",
        normal_low=0,
        normal_high=0.2,
        threshold_high=5.0,
        direction="high",
        alpha=0.4,
        unit="mm",
    ),
    SignalRule(
        name="dew_point_high_pressure",
        field="dew_point_c",
        normal_low=18,
        normal_high=24,
        threshold_high=27,
        direction="high",
        alpha=0.25,
        unit="C",
    ),
    SignalRule(
        name="cloud_cover_high_pressure",
        field="cloud_cover_pct",
        normal_low=0,
        normal_high=70,
        threshold_high=90,
        direction="high",
        alpha=0.25,
        unit="pct",
    ),
    SignalRule(
        name="evapotranspiration_dry_pressure",
        field="et0_mm",
        normal_low=0,
        normal_high=5,
        threshold_high=8,
        direction="high",
        alpha=0.3,
        unit="mm",
    ),
)

SOURCE_CONFIGS: dict[str, dict[str, Any]] = {
    "npk": {
        "rules": NPK_SIGNAL_RULES,
        "aliases": NPK_FIELD_ALIASES,
        "window_hours": DEFAULT_WINDOW_HOURS,
    },
    "sht30": {
        "rules": SHT30_SIGNAL_RULES,
        "aliases": SHT30_FIELD_ALIASES,
        "window_hours": DEFAULT_WINDOW_HOURS,
    },
    "meteo": {
        "rules": METEO_SIGNAL_RULES,
        "aliases": METEO_FIELD_ALIASES,
        "window_hours": DEFAULT_WINDOW_HOURS,
    },
}


def export_config_snapshot() -> dict[str, Any]:
    return {
        "ruleset_version": RULESET_VERSION,
        "default_window_hours": list(DEFAULT_WINDOW_HOURS),
        "sources": {
            source: {
                "window_hours": list(config["window_hours"]),
                "aliases": {
                    field: list(alias_keys)
                    for field, alias_keys in config["aliases"].items()
                },
                "rules": [asdict(rule) for rule in config["rules"]],
            }
            for source, config in SOURCE_CONFIGS.items()
        },
    }
