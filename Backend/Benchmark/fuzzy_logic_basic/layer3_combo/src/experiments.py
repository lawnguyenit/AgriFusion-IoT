from __future__ import annotations

from dataclasses import dataclass

from Backend.Benchmark.fuzzy_logic_basic.layer2.src.experiments import (
    BASE_COLUMNS,
    DELTA_COLUMNS,
    WINDOW_LONG_COLUMNS,
    WINDOW_MEDIUM_COLUMNS,
    WINDOW_SHORT_COLUMNS,
)


COMBO_1_COLUMNS = [
    *BASE_COLUMNS,
    *WINDOW_SHORT_COLUMNS,
    *WINDOW_MEDIUM_COLUMNS,
]

COMBO_2_COLUMNS = [
    *BASE_COLUMNS,
    *DELTA_COLUMNS,
    *WINDOW_SHORT_COLUMNS,
    *WINDOW_MEDIUM_COLUMNS,
]

COMBO_3_COLUMNS = [
    *BASE_COLUMNS,
    *WINDOW_SHORT_COLUMNS,
    *WINDOW_MEDIUM_COLUMNS,
    *WINDOW_LONG_COLUMNS,
]

COMBO_4_COLUMNS = [
    *BASE_COLUMNS,
    *DELTA_COLUMNS,
    *WINDOW_SHORT_COLUMNS,
    *WINDOW_MEDIUM_COLUMNS,
    *WINDOW_LONG_COLUMNS,
]


@dataclass(frozen=True)
class Layer3ComboExperimentSpec:
    name: str
    description: str
    output_filename: str
    feature_columns: list[str]


def build_experiment_specs() -> dict[str, Layer3ComboExperimentSpec]:
    return {
        "combo1": Layer3ComboExperimentSpec(
            name="combo1",
            description="Base columns plus 3h and 8h windows.",
            output_filename="flb_l3_combo1.csv",
            feature_columns=list(COMBO_1_COLUMNS),
        ),
        "combo2": Layer3ComboExperimentSpec(
            name="combo2",
            description="Combo1 plus delta features.",
            output_filename="flb_l3_combo2.csv",
            feature_columns=list(COMBO_2_COLUMNS),
        ),
        "combo3": Layer3ComboExperimentSpec(
            name="combo3",
            description="Base columns plus 3h, 8h, and 24h windows.",
            output_filename="flb_l3_combo3.csv",
            feature_columns=list(COMBO_3_COLUMNS),
        ),
        "combo4": Layer3ComboExperimentSpec(
            name="combo4",
            description="Combo3 plus delta features.",
            output_filename="flb_l3_combo4.csv",
            feature_columns=list(COMBO_4_COLUMNS),
        ),
    }

