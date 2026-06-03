from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BenchmarkVersionSpec:
    name: str
    model_family: str
    expected_fuzzy_layer: str
    compatibility_source_kind: str
    schema_policy: str
    notes: str


def build_version_catalog() -> dict[str, BenchmarkVersionSpec]:
    return {
        "v0": BenchmarkVersionSpec(
            name="v0",
            model_family="embedding_supervised",
            expected_fuzzy_layer="layer0",
            compatibility_source_kind="layer0_ph_npk",
            schema_policy="layer0_npk_ph_ablation_schema",
            notes=(
                "Layer0 nutrient/pH ablation suite. This version compares base features against "
                "raw pH-only, raw NPK-only, and combined pH+NPK representations before the Layer1 baseline."
            ),
        ),
        "v1": BenchmarkVersionSpec(
            name="v1",
            model_family="embedding_supervised",
            expected_fuzzy_layer="layer1",
            compatibility_source_kind="layer1",
            schema_policy="embedding_ready_row_wise_schema",
            notes=(
                "Layer1 baseline. Pretrain consumes the aligned Layer1 CSV and downstream v1 models "
                "consume the resulting embedding."
            ),
        ),
        "v2": BenchmarkVersionSpec(
            name="v2",
            model_family="embedding_supervised",
            expected_fuzzy_layer="layer2",
            compatibility_source_kind="layer2_exp2",
            schema_policy="layer2_single_window_ablation_schema",
            notes=(
                "Layer2 single-window ablation suite. Pretrain should point to one of the Layer2 "
                "exports layer2_exp1..layer2_exp5, with layer2_exp2 as the default short-window run."
            ),
        ),
        "v3": BenchmarkVersionSpec(
            name="v3",
            model_family="embedding_supervised",
            expected_fuzzy_layer="layer3_combo",
            compatibility_source_kind="layer3_combo2",
            schema_policy="layer3_multi_window_combo_schema",
            notes=(
                "Layer3 multi-window combo benchmark built on top of Layer2 features. "
                "The default source_kind is layer3_combo2."
            ),
        ),
        "v4": BenchmarkVersionSpec(
            name="v4",
            model_family="embedding_supervised",
            expected_fuzzy_layer="layer2",
            compatibility_source_kind="layer2_exp6",
            schema_policy="layer2_full_set_schema",
            notes=(
                "Layer2 full-set benchmark. Pretrain and downstream v4 consume the full Layer2 "
                "ablation export layer2_exp6."
            ),
        ),
    }
