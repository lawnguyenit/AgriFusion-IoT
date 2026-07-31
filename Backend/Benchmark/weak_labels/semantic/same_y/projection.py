from __future__ import annotations

import pandas as pd

from Backend.Benchmark.weak_labels.contracts.native import NativeContract, deterministic_id


def build_same_y_transfer_projection(
    point_assignments: pd.DataFrame,
    window_projection: pd.DataFrame,
    contract: NativeContract,
    operationalization: pd.Series,
    horizon_id: str,
) -> pd.DataFrame:
    joined = point_assignments.merge(window_projection, on="sample_id", how="left", validate="one_to_one")
    rows: list[dict[str, object]] = []
    for row in joined.to_dict(orient="records"):
        sample_id = str(row["sample_id"])
        source_assignment_id = str(row["assignment_id"])
        transfer_id = deterministic_id(
            {
                "object_type": "SAME_Y_TRANSFER",
                "schema_version": "native.same-y-transfer.v1",
                "semantic_contract_hash": contract.semantic_contract_hash,
                "operationalization_id": str(operationalization["operationalization_id"]),
                "task_id": "SAME_Y",
                "horizon_id": horizon_id,
                "sample_id": sample_id,
                "source_assignment_id": source_assignment_id,
            }
        )
        eligible = str(row.get("representation_history_status", "INELIGIBLE")) == "ELIGIBLE"
        rows.append(
            {
                "same_y_transfer_id": transfer_id,
                "sample_id": sample_id,
                "task_id": "SAME_Y",
                "horizon_id": horizon_id,
                "source_assignment_id": source_assignment_id,
                "source_label": row["label"],
                "transferred_label": row["label"],
                "representation_history_status": "ELIGIBLE" if eligible else "INELIGIBLE",
                "intrinsic_transfer_status": "ELIGIBLE" if eligible and row.get("train_inclusion_status") == "INCLUDED" else "EXCLUDED_FROM_COHORT",
                "label_dependency_admissible": True,
                "semantic_contract_hash": contract.semantic_contract_hash,
            }
        )
    return pd.DataFrame(rows).convert_dtypes()

