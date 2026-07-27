from __future__ import annotations

from pathlib import Path

import pandas as pd

from Backend.Benchmark.validity_lifecycle.contracts import EnvironmentSpec


DEFAULT_PROTOCOL_VERSION = "2026-07-26.validity-lifecycle.v1"
EXPECTED_POINT_TARGETS: tuple[str, ...] = ("NRM", "LRM", "UNK")
PRIMARY_VIEW_IDS: tuple[str, ...] = (
    "v0_point",
    "v1_point",
    "v2_same_y_mini_3h",
    "v2_same_y_full_3h",
    "v2_same_y_mini_8h",
    "v2_same_y_full_8h",
)
POINT_TARGET_MAP: dict[str, str] = {
    "normal_point": "NRM",
    "low_relative_moisture_point": "LRM",
    "unknown_environment_point": "UNK",
}


def default_environment_specs() -> tuple[EnvironmentSpec, ...]:
    return (
        EnvironmentSpec(
            environment_id="E1",
            stage_name="Discovery",
            start_local=pd.Timestamp("2026-04-01T00:00:00", tz="Asia/Ho_Chi_Minh"),
            end_local=pd.Timestamp("2026-05-09T00:00:00", tz="Asia/Ho_Chi_Minh"),
            deployment_id="P1_SOURCE",
            boundary_status="protocol_locked",
            boundary_reason="Initial P1 source-development interval locked by the lifecycle contract.",
            train_description="Train on E1 only.",
            evaluation_description="Evaluate on future folds within E1.",
            stage_question="Under stable source conditions, what dependency appears usable before transport stress?",
        ),
        EnvironmentSpec(
            environment_id="E2",
            stage_name="Temporal falsification",
            start_local=pd.Timestamp("2026-05-09T00:00:00", tz="Asia/Ho_Chi_Minh"),
            end_local=pd.Timestamp("2026-05-20T00:00:00", tz="Asia/Ho_Chi_Minh"),
            deployment_id="P1_SOURCE",
            boundary_status="post_hoc_exploratory",
            boundary_reason="Operational boundary retained as exploratory until an independent field log is linked.",
            train_description="Train on E1 only.",
            evaluation_description="Evaluate on all of E2.",
            stage_question="Does a dependency seen in E1 survive the later P1 regime without refitting the contract?",
        ),
        EnvironmentSpec(
            environment_id="E3",
            stage_name="Deployment transport",
            start_local=pd.Timestamp("2026-06-27T00:00:00", tz="Asia/Ho_Chi_Minh"),
            end_local=pd.Timestamp("2026-07-13T00:00:00", tz="Asia/Ho_Chi_Minh"),
            deployment_id="P2_TARGET",
            boundary_status="protocol_locked",
            boundary_reason="P2 relocation holdout interval locked by the transport benchmark contract.",
            train_description="Train on E1 or E1+E2 depending on the later experiment stage.",
            evaluation_description="Evaluate on all of E3.",
            stage_question="After relocation, what remains estimable, transportable, or ambiguous?",
        ),
    )


def lifecycle_config_payload() -> dict[str, object]:
    return {
        "protocol_version": DEFAULT_PROTOCOL_VERSION,
        "environments": [
            {
                "environment_id": spec.environment_id,
                "stage_name": spec.stage_name,
                "start_local": spec.start_local.isoformat(),
                "end_local": spec.end_local.isoformat(),
                "deployment_id": spec.deployment_id,
                "boundary_status": spec.boundary_status,
                "boundary_reason": spec.boundary_reason,
                "train_description": spec.train_description,
                "evaluation_description": spec.evaluation_description,
                "stage_question": spec.stage_question,
            }
            for spec in default_environment_specs()
        ],
        "support_thresholds": {
            "min_samples": 5,
            "min_days": 2,
            "min_segments": 1,
        },
        "gating_policy": {
            "support_fail_state": "NOT_ESTIMABLE",
            "eligibility_warn_below_rate": 0.25,
            "comparison_hash_mismatch_blocks_training": True,
        },
    }


def primary_claims_payload() -> dict[str, object]:
    return {
        "views": list(PRIMARY_VIEW_IDS),
        "domains": {
            "source": "P1_SOURCE",
            "target": "P2_TARGET",
        },
        "comparisons": [
            "v0_vs_v2_mini_3h",
            "v1_vs_v2_full_3h",
            "v0_vs_v2_mini_8h",
            "v1_vs_v2_full_8h",
        ],
        "constraints": [
            "Use V0, V1, and V2 same-Y only for primary lifecycle gating.",
            "Treat P2 as target-only and never as a model-selection source.",
            "Require prebuilt manifests instead of runner-side 70/15/15 slicing.",
        ],
    }


def secondary_analyses_payload() -> dict[str, object]:
    return {
        "included": [
            "V2 temporal labels remain diagnostic-only in this phase.",
            "Threshold sensitivity remains read-only and may inform later falsification work.",
            "Metadata-only and reduced-ontology variants remain out of the primary gate contract.",
        ],
        "excluded_from_primary_gate": [
            "Any train-time refit against P2.",
            "Any experiment that changes both X and Y without explicit separation.",
        ],
    }


def config_file_payloads() -> dict[Path, dict[str, object]]:
    return {
        Path("validity_lifecycle_v1.yaml"): lifecycle_config_payload(),
        Path("primary_claims.yaml"): primary_claims_payload(),
        Path("secondary_analyses.yaml"): secondary_analyses_payload(),
    }
