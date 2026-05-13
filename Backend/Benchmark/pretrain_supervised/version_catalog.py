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
            compatibility_source_kind="layer2_exp5",
            schema_policy="layer2_windowed_ablation_schema",
            notes=(
                "Layer2 windowed schema. Pretrain should point to one of the Layer2 ablation exports "
                "such as layer2_exp1..layer2_exp5, with layer2_exp5 as the full default."
            ),
        ),
        "v3": BenchmarkVersionSpec(
            name="v3",
            model_family="embedding_supervised",
            expected_fuzzy_layer="layer3",
            compatibility_source_kind="layer3",
            schema_policy="layer3_relational_schema",
            notes=(
                "Reserved for Layer3 relational features built on top of Layer2 exports."
            ),
        ),
        "v4": BenchmarkVersionSpec(
            name="v4",
            model_family="embedding_supervised",
            expected_fuzzy_layer="layer4",
            compatibility_source_kind="layer4",
            schema_policy="layer4_extended_schema",
            notes=(
                "Reserved for later Layer4 schema extensions."
            ),
        ),
    }
