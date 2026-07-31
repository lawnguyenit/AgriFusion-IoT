from __future__ import annotations

import json

import pandas as pd

from Backend.Benchmark.weak_labels.contracts.native import NativeContract


def build_rule_registry(rule_firings: pd.DataFrame) -> pd.DataFrame:
    columns = ["rule_id", "threshold_id", "comparison_operator", "evidence_field"]
    return rule_firings.loc[:, [column for column in columns if column in rule_firings.columns]].drop_duplicates().reset_index(drop=True).convert_dtypes()


def build_threshold_registry(rule_firings: pd.DataFrame) -> pd.DataFrame:
    columns = ["threshold_id", "threshold_value", "comparison_operator"]
    return rule_firings.loc[:, [column for column in columns if column in rule_firings.columns]].drop_duplicates().reset_index(drop=True).convert_dtypes()


def validate_referential_integrity(
    *,
    canonical: pd.DataFrame,
    rule_firings: pd.DataFrame,
    resolutions: pd.DataFrame,
    assignments: pd.DataFrame,
    same_y_transfers: list[pd.DataFrame] | None = None,
) -> dict[str, int]:
    canonical_ids = set(canonical["record.id"].astype("string"))
    firing_ids = set(rule_firings["rule_firing_id"].astype("string"))
    resolution_ids = set(resolutions["resolution_instance_id"].astype("string"))
    if not set(rule_firings["sample_id"].astype("string")).issubset(canonical_ids):
        raise ValueError("RuleFiring references an unknown canonical sample.")
    if not set(assignments["resolution_instance_id"].astype("string")).issubset(resolution_ids):
        raise ValueError("Assignment references an unknown Resolution.")
    if rule_firings["rule_firing_id"].duplicated().any():
        raise ValueError("rule_firing_id must be unique.")
    if resolutions["resolution_instance_id"].duplicated().any():
        raise ValueError("resolution_instance_id must be unique.")
    if assignments["assignment_id"].duplicated().any():
        raise ValueError("assignment_id must be unique.")
    for transfer in same_y_transfers or []:
        if not set(transfer["source_assignment_id"].astype("string")).issubset(set(assignments["assignment_id"].astype("string"))):
            raise ValueError("Same-Y transfer references an unknown source assignment.")
        if (transfer["source_label"].astype("string") != transfer["transferred_label"].astype("string")).any():
            raise ValueError("Same-Y transfer changed the source semantic label.")
    return {
        "canonical_record_count": len(canonical_ids),
        "rule_firing_count": len(firing_ids),
        "resolution_count": len(resolution_ids),
        "assignment_count": int(len(assignments)),
    }


def build_label_source_dependency(contract: NativeContract) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "task_id": "POINT",
                "source_kind": "CANONICAL_EVIDENCE",
                "semantic_contract_hash": contract.semantic_contract_hash,
                "dependency_policy": "FROZEN_CONTRACT",
            },
            {
                "task_id": "TEMPORAL_ANCHOR",
                "source_kind": "POINT_ASSIGNMENT_AND_WINDOW_EVIDENCE",
                "semantic_contract_hash": contract.semantic_contract_hash,
                "dependency_policy": "ANCHOR_CONDITIONED",
            },
        ]
    ).convert_dtypes()

