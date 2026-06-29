from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BenchmarkVersionSpec:
    name: str
    model_family: str
    expected_feature_stage: str
    compatibility_source_kind: str
    schema_policy: str
    notes: str


def build_version_catalog() -> dict[str, BenchmarkVersionSpec]:
    return {
        "v0": BenchmarkVersionSpec(
            name="v0",
            model_family="embedding_supervised",
            expected_feature_stage="layer0",
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
            expected_feature_stage="layer1",
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
            expected_feature_stage="single_window_features",
            compatibility_source_kind="single_window_exp2",
            schema_policy="single_window_ablation_schema",
            notes=(
                "Single-window feature suite. Pretrain should point to one of the single-window "
                "exports single_window_exp1..single_window_exp5, with single_window_exp2 as the default short-window run."
            ),
        ),
        "v3": BenchmarkVersionSpec(
            name="v3",
            model_family="embedding_supervised",
            expected_feature_stage="multi_window_features",
            compatibility_source_kind="multi_window_combo2",
            schema_policy="multi_window_combo_schema",
            notes=(
                "Multi-window combo benchmark built on top of the single-window feature family. "
                "The default source_kind is multi_window_combo2."
            ),
        ),
        "v4": BenchmarkVersionSpec(
            name="v4",
            model_family="embedding_supervised",
            expected_feature_stage="single_window_features",
            compatibility_source_kind="single_window_exp6",
            schema_policy="single_window_full_set_schema",
            notes=(
                "Full single-window feature benchmark. Pretrain and downstream v4 consume the full single-window "
                "feature export single_window_exp6."
            ),
        ),
    }
