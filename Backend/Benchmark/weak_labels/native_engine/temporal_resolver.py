from __future__ import annotations

import json

import pandas as pd

from Backend.Benchmark.weak_labels.native_engine.contracts import NativeContract, dataframe_set_hash, deterministic_id


def resolve_temporal_assignments(
    frame: pd.DataFrame,
    point_assignments: pd.DataFrame,
    windows: pd.DataFrame,
    runs: pd.DataFrame,
    contract: NativeContract,
    operationalization: pd.Series,
    horizon_id: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    k = _selected_k(contract, operationalization)
    joined = (
        frame[["record.id", "environment_id"]]
        .merge(point_assignments[["sample_id", "label", "assignment_id"]], left_on="record.id", right_on="sample_id", how="left", validate="one_to_one")
        .merge(windows, left_on="record.id", right_on="sample_id", how="left", validate="one_to_one")
        .merge(runs, left_on="record.id", right_on="record.id", how="left", validate="one_to_one")
    )
    assignment_rows: list[dict[str, object]] = []
    resolution_rows: list[dict[str, object]] = []
    for row in joined.to_dict(orient="records"):
        sample_id = str(row["record.id"])
        point_label = str(row.get("label", "point_not_evaluable"))
        eligible = str(row.get("representation_history_status", "INELIGIBLE")) == "ELIGIBLE"
        support = int(row.get("support_depth_at_anchor") or 0)
        if not eligible:
            code, label, inclusion = "TEMPORAL_WINDOW_INELIGIBLE", "window_ineligible", "EXCLUDED"
        elif point_label == "low_relative_moisture_point" and support >= k:
            code, label, inclusion = "TEMPORAL_PERSISTENT_LOW", "persistent_low_relative_moisture_at_anchor", "INCLUDED"
        elif point_label == "low_relative_moisture_point":
            code, label, inclusion = "TEMPORAL_UNRESOLVED_INSUFFICIENT_PERSISTENCE", "unresolved_environmental_evidence_at_anchor", "INCLUDED"
        elif point_label == "unresolved_environmental_evidence_point":
            code, label, inclusion = "TEMPORAL_POINT_UNRESOLVED_TRANSFER", "unresolved_environmental_evidence_at_anchor", "INCLUDED"
        elif point_label == "point_context_incomplete":
            code, label, inclusion = "TEMPORAL_POINT_CONTEXT_INCOMPLETE_TRANSFER", "point_context_incomplete_transfer", "EXCLUDED"
        elif point_label == "reference_context_point":
            code, label, inclusion = "TEMPORAL_REFERENCE_CONTEXT", "reference_context_at_anchor", "INCLUDED"
        else:
            raise ValueError(f"Unhandled temporal point state: {point_label}")
        firing_hash = dataframe_set_hash(pd.DataFrame([{"sample_id": sample_id, "horizon_id": horizon_id}]), ["sample_id", "horizon_id"])
        resolution_id = deterministic_id(
            {
                "object_type": "RESOLUTION",
                "schema_version": "native.temporal-resolution.v1",
                "semantic_contract_hash": contract.semantic_contract_hash,
                "operationalization_id": str(operationalization["operationalization_id"]),
                "task_id": "TEMPORAL_ANCHOR",
                "horizon_id": horizon_id,
                "sample_id": sample_id,
                "compatibility_row_id": code,
                "rule_firing_set_hash": firing_hash,
            }
        )
        resolution_rows.append(
            {
                "resolution_instance_id": resolution_id,
                "resolution_code": code,
                "sample_id": sample_id,
                "task_id": "TEMPORAL_ANCHOR",
                "operationalization_id": str(operationalization["operationalization_id"]),
                "horizon_id": horizon_id,
                "resolved_label": label,
                "support_depth_at_anchor": support,
                "required_k": k,
                "rule_firing_set_hash": firing_hash,
                "semantic_contract_hash": contract.semantic_contract_hash,
            }
        )
        assignment_id = deterministic_id(
            {
                "object_type": "ASSIGNMENT",
                "schema_version": "native.temporal-assignment.v1",
                "semantic_contract_hash": contract.semantic_contract_hash,
                "operationalization_id": str(operationalization["operationalization_id"]),
                "task_id": "TEMPORAL_ANCHOR",
                "horizon_id": horizon_id,
                "sample_id": sample_id,
                "resolution_instance_id": resolution_id,
                "assignment_mode": "TEMPORAL_RULE_EVALUATION",
            }
        )
        assignment_rows.append(
            {
                "assignment_id": assignment_id,
                "sample_id": sample_id,
                "environment_id": row.get("environment_id", "E1"),
                "task_id": "TEMPORAL_ANCHOR",
                "operationalization_id": str(operationalization["operationalization_id"]),
                "horizon_id": horizon_id,
                "semantic_contract_id": contract.semantic_contract_id,
                "semantic_contract_hash": contract.semantic_contract_hash,
                "label": label,
                "resolution_instance_id": resolution_id,
                "resolution_code": code,
                "assignment_mode": "TEMPORAL_RULE_EVALUATION",
                "assignment_status": "ASSIGNED",
                "train_inclusion_status": inclusion,
                "source_task": "POINT",
                "source_assignment_id": row.get("assignment_id_x", row.get("assignment_id")),
                "source_label": point_label,
                "semantic_assignment_admissible": eligible,
            }
        )
    return pd.DataFrame(resolution_rows).convert_dtypes(), pd.DataFrame(assignment_rows).convert_dtypes()


def _selected_k(contract: NativeContract, operationalization: pd.Series) -> int:
    contract_id = str(operationalization["persistence_contract_id"])
    rows = contract.persistence_registry.loc[contract.persistence_registry["contract_id"].astype("string") == contract_id]
    if len(rows) != 1:
        raise ValueError(f"Persistence contract is not unique: {contract_id}")
    return int(rows.iloc[0]["selected_k"])

