from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BenchmarkSourceProfile:
    name: str
    description: str
    default_csv: Path | None
    required_columns: list[str]
    default_feature_columns: list[str]


COMMON_TIME_FEATURES = [
    "hour_sin",
    "hour_cos",
    "dayofweek_sin",
    "dayofweek_cos",
    "gap_minutes_since_prev",
]

L1_REQUIRED_COLUMNS = [
    "timestamp",
    "soil_temp",
    "soil_humidity",
    "air_temp",
    "air_humidity",
    "EC",
]

L1_FEATURE_COLUMNS = [
    "soil_temp",
    "soil_humidity",
    "air_temp",
    "air_humidity",
    "EC",
    *COMMON_TIME_FEATURES,
]

L0_BASE_COLUMNS = [
    "soil_temp",
    "soil_humidity",
    "air_temp",
    "air_humidity",
    "EC",
]

L0_PH_COLUMNS = ["pH"]

L0_NPK_COLUMNS = ["N", "P", "K"]

L2_BASE_COLUMNS = [
    "soil_temp",
    "soil_humidity",
    "air_temp",
    "air_humidity",
    "EC",
]

L2_DELTA_COLUMNS = [
    "air_temp_delta_1step",
    "soil_temp_delta_1step",
    "soil_humidity_delta_1step",
    "EC_delta_1step",
]

L2_WINDOW_SHORT_COLUMNS = [
    "air_temp_slope_3h",
    "air_temp_range_3h",
    "air_temp_mean_3h",
    "soil_temp_slope_3h",
    "soil_humidity_slope_3h",
    "soil_humidity_range_3h",
    "EC_slope_3h",
    "EC_range_3h",
]

L2_WINDOW_MEDIUM_COLUMNS = [
    "air_temp_slope_8h",
    "air_temp_range_8h",
    "soil_temp_slope_8h",
    "soil_temp_mean_8h",
    "soil_humidity_slope_8h",
    "soil_humidity_range_8h",
    "EC_slope_8h",
    "EC_range_8h",
]

L2_WINDOW_LONG_COLUMNS = [
    "soil_temp_range_24h",
    "soil_humidity_mean_24h",
    "soil_humidity_min_24h",
    "EC_mean_24h",
    "EC_range_24h",
    "EC_exposure_24h",
]

L2_SATURATION_COLUMNS = [
    "air_humidity_saturation_flag",
    "air_humidity_saturation_duration_3h",
    "air_humidity_saturation_duration_8h",
    "air_humidity_saturation_ratio_3h",
    "air_humidity_saturation_ratio_8h",
]


def _l2_profile(
    *,
    name: str,
    description: str,
    default_csv: Path | None,
    extra_columns: list[str],
) -> BenchmarkSourceProfile:
    required_columns = ["timestamp", *L2_BASE_COLUMNS, *extra_columns]
    default_feature_columns = [*L2_BASE_COLUMNS, *extra_columns, *COMMON_TIME_FEATURES]
    return BenchmarkSourceProfile(
        name=name,
        description=description,
        default_csv=default_csv,
        required_columns=required_columns,
        default_feature_columns=default_feature_columns,
    )


def _l0_profile(
    *,
    name: str,
    description: str,
    default_csv: Path | None,
    extra_columns: list[str],
) -> BenchmarkSourceProfile:
    required_columns = ["timestamp", *L0_BASE_COLUMNS, *extra_columns]
    default_feature_columns = [*L0_BASE_COLUMNS, *extra_columns, *COMMON_TIME_FEATURES]
    return BenchmarkSourceProfile(
        name=name,
        description=description,
        default_csv=default_csv,
        required_columns=required_columns,
        default_feature_columns=default_feature_columns,
    )


def _l3_combo_profile(
    *,
    name: str,
    description: str,
    default_csv: Path | None,
    extra_columns: list[str],
) -> BenchmarkSourceProfile:
    return _l2_profile(
        name=name,
        description=description,
        default_csv=default_csv,
        extra_columns=extra_columns,
    )


def build_source_registry(root_dir: Path) -> dict[str, BenchmarkSourceProfile]:
    fuzzy_root = root_dir / "Backend" / "Benchmark" / "fuzzy_logic_basic"
    return {
        "layer0_ph": _l0_profile(
            name="layer0_ph",
            description="Layer0 baseline with raw pH added on top of the Layer1 sensor base.",
            default_csv=fuzzy_root / "dataset" / "flb_input_aligned.csv",
            extra_columns=[*L0_PH_COLUMNS],
        ),
        "layer0_npk": _l0_profile(
            name="layer0_npk",
            description="Layer0 baseline with raw NPK added on top of the Layer1 sensor base.",
            default_csv=fuzzy_root / "dataset" / "flb_input_aligned.csv",
            extra_columns=[*L0_NPK_COLUMNS],
        ),
        "layer0_ph_npk": _l0_profile(
            name="layer0_ph_npk",
            description="Layer0 baseline with raw pH and raw NPK added on top of the Layer1 sensor base.",
            default_csv=fuzzy_root / "dataset" / "flb_input_aligned.csv",
            extra_columns=[*L0_PH_COLUMNS, *L0_NPK_COLUMNS],
        ),
        "layer1": BenchmarkSourceProfile(
            name="layer1",
            description="Current aligned CSV built from fuzzy Layer1 output.",
            default_csv=fuzzy_root / "dataset" / "flb_input_aligned.csv",
            required_columns=list(L1_REQUIRED_COLUMNS),
            default_feature_columns=list(L1_FEATURE_COLUMNS),
        ),
        "layer2_exp1": _l2_profile(
            name="layer2_exp1",
            description="Fuzzy Layer2 experiment 1: base columns plus delta features.",
            default_csv=fuzzy_root / "dataset" / "flb_l2_exp1.csv",
            extra_columns=[*L2_DELTA_COLUMNS],
        ),
        "layer2_exp2": _l2_profile(
            name="layer2_exp2",
            description="Fuzzy Layer2 experiment 2: Exp1 plus 3h short-window features.",
            default_csv=fuzzy_root / "dataset" / "flb_l2_exp2.csv",
            extra_columns=[*L2_DELTA_COLUMNS, *L2_WINDOW_SHORT_COLUMNS],
        ),
        "layer2_exp3": _l2_profile(
            name="layer2_exp3",
            description="Fuzzy Layer2 experiment 3: Exp1 plus 8h medium-window features.",
            default_csv=fuzzy_root / "dataset" / "flb_l2_exp3.csv",
            extra_columns=[*L2_DELTA_COLUMNS, *L2_WINDOW_MEDIUM_COLUMNS],
        ),
        "layer2_exp4": _l2_profile(
            name="layer2_exp4",
            description="Fuzzy Layer2 experiment 4: Exp1 plus 24h long-window summaries.",
            default_csv=fuzzy_root / "dataset" / "flb_l2_exp4.csv",
            extra_columns=[*L2_DELTA_COLUMNS, *L2_WINDOW_LONG_COLUMNS],
        ),
        "layer2_exp5": _l2_profile(
            name="layer2_exp5",
            description="Fuzzy Layer2 experiment 5: Exp1 plus air-humidity saturation persistence features.",
            default_csv=fuzzy_root / "dataset" / "flb_l2_exp5.csv",
            extra_columns=[*L2_DELTA_COLUMNS, *L2_SATURATION_COLUMNS],
        ),
        "layer2_exp6": _l2_profile(
            name="layer2_exp6",
            description="Fuzzy Layer2 experiment 6: full Layer2 ablation set.",
            default_csv=fuzzy_root / "dataset" / "flb_l2_exp6.csv",
            extra_columns=[
                *L2_DELTA_COLUMNS,
                *L2_WINDOW_SHORT_COLUMNS,
                *L2_WINDOW_MEDIUM_COLUMNS,
                *L2_WINDOW_LONG_COLUMNS,
                *L2_SATURATION_COLUMNS,
            ],
        ),
        "layer3_combo1": _l3_combo_profile(
            name="layer3_combo1",
            description="Fuzzy Layer3 combo 1: base columns plus 3h and 8h windows.",
            default_csv=fuzzy_root / "dataset" / "flb_l3_combo1.csv",
            extra_columns=[*L2_WINDOW_SHORT_COLUMNS, *L2_WINDOW_MEDIUM_COLUMNS],
        ),
        "layer3_combo2": _l3_combo_profile(
            name="layer3_combo2",
            description="Fuzzy Layer3 combo 2: combo1 plus delta features.",
            default_csv=fuzzy_root / "dataset" / "flb_l3_combo2.csv",
            extra_columns=[*L2_DELTA_COLUMNS, *L2_WINDOW_SHORT_COLUMNS, *L2_WINDOW_MEDIUM_COLUMNS],
        ),
        "layer3_combo3": _l3_combo_profile(
            name="layer3_combo3",
            description="Fuzzy Layer3 combo 3: base columns plus 3h, 8h, and 24h windows.",
            default_csv=fuzzy_root / "dataset" / "flb_l3_combo3.csv",
            extra_columns=[*L2_WINDOW_SHORT_COLUMNS, *L2_WINDOW_MEDIUM_COLUMNS, *L2_WINDOW_LONG_COLUMNS],
        ),
        "layer3_combo4": _l3_combo_profile(
            name="layer3_combo4",
            description="Fuzzy Layer3 combo 4: combo3 plus delta features.",
            default_csv=fuzzy_root / "dataset" / "flb_l3_combo4.csv",
            extra_columns=[*L2_DELTA_COLUMNS, *L2_WINDOW_SHORT_COLUMNS, *L2_WINDOW_MEDIUM_COLUMNS, *L2_WINDOW_LONG_COLUMNS],
        ),
        "layer3": BenchmarkSourceProfile(
            name="layer3",
            description="Reserved for future fuzzy Layer3 benchmark exports.",
            default_csv=None,
            required_columns=[],
            default_feature_columns=[],
        ),
        "layer4": BenchmarkSourceProfile(
            name="layer4",
            description="Reserved for future fuzzy Layer4 benchmark exports.",
            default_csv=None,
            required_columns=[],
            default_feature_columns=[],
        ),
        "layer5": BenchmarkSourceProfile(
            name="layer5",
            description="Reserved for future fuzzy Layer5 benchmark exports.",
            default_csv=None,
            required_columns=[],
            default_feature_columns=[],
        ),
        "custom": BenchmarkSourceProfile(
            name="custom",
            description="Explicit CSV path passed from the CLI.",
            default_csv=None,
            required_columns=list(L1_REQUIRED_COLUMNS),
            default_feature_columns=list(L1_FEATURE_COLUMNS),
        ),
    }


def resolve_source_profile(
    *,
    source_kind: str,
    input_csv: Path | None,
    root_dir: Path,
) -> tuple[BenchmarkSourceProfile, Path]:
    registry = build_source_registry(root_dir)
    if source_kind not in registry:
        available = ", ".join(sorted(registry))
        raise ValueError(f"Unknown source kind '{source_kind}'. Available: {available}")

    profile = registry[source_kind]
    if input_csv is not None:
        return profile, input_csv.resolve()

    if profile.default_csv is None:
        raise FileNotFoundError(
            f"Source kind '{source_kind}' is reserved for future fuzzy outputs. "
            "Pass --input-csv with the generated CSV when it exists."
        )

    return profile, profile.default_csv.resolve()
