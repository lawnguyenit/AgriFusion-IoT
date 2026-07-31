from __future__ import annotations

import json

import pandas as pd

from Backend.Benchmark.weak_labels.contracts.native import NativeContract, dataframe_set_hash, deterministic_id


def resolve_point_assignments(
    frame: pd.DataFrame,
    rule_states: pd.DataFrame,
    rule_firings: pd.DataFrame,
    contract: NativeContract,
    operationalization: pd.Series,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    joined = frame.merge(rule_states, left_on="record.id", right_on="sample_id", how="left", validate="one_to_one")
    assignment_rows: list[dict[str, object]] = []
    resolution_rows: list[dict[str, object]] = []
    for row in joined.to_dict(orient="records"):
        sample_id = str(row["record.id"])
        low = str(row.get("low_state", "NOT_EVALUABLE"))
        auxiliary = [str(row.get(column, "NOT_EVALUABLE")) for column in ("thermal_state", "rise_state", "ec_state")]
        observed_positive = any(state == "POSITIVE" for state in auxiliary)
        incomplete = any(state == "NOT_EVALUABLE" for state in auxiliary)
        if not bool(row.get("time_integrity_ok", False)) or low == "NOT_EVALUABLE":
            code = "POINT_NOT_EVALUABLE"
            label = "point_not_evaluable"
            train_inclusion = "EXCLUDED"
        elif low == "POSITIVE":
            code = "POINT_LOW_RELATIVE_MOISTURE"
            label = "low_relative_moisture_point"
            train_inclusion = "INCLUDED"
        elif observed_positive:
            code = "POINT_UNRESOLVED_AUXILIARY_POSITIVE"
            label = "unresolved_environmental_evidence_point"
            train_inclusion = "INCLUDED"
        elif incomplete:
            code = "POINT_CONTEXT_INCOMPLETE"
            label = "point_context_incomplete"
            train_inclusion = "EXCLUDED"
        else:
            code = "POINT_REFERENCE_CONTEXT"
            label = "reference_context_point"
            train_inclusion = "INCLUDED"
        firing_ids = rule_firings.loc[
            (rule_firings["sample_id"].astype("string") == sample_id)
            & (rule_firings["task_id"].astype("string") == "POINT")
        ]["rule_firing_id"].astype("string").tolist()
        firing_set_hash = dataframe_set_hash(
            rule_firings.loc[rule_firings["sample_id"].astype("string") == sample_id],
            ["rule_firing_id"],
        )
        compatibility_row_id = _compatibility_row_id(contract, low, auxiliary)
        resolution_instance_id = deterministic_id(
            {
                "object_type": "RESOLUTION",
                "schema_version": "native.resolution.v1",
                "semantic_contract_hash": contract.semantic_contract_hash,
                "operationalization_id": str(operationalization["operationalization_id"]),
                "task_id": "POINT",
                "horizon_id": "NONE",
                "sample_id": sample_id,
                "compatibility_row_id": compatibility_row_id,
                "rule_firing_set_hash": firing_set_hash,
            }
        )
        resolution_rows.append(
            {
                "resolution_instance_id": resolution_instance_id,
                "resolution_code": code,
                "sample_id": sample_id,
                "task_id": "POINT",
                "operationalization_id": str(operationalization["operationalization_id"]),
                "horizon_id": "NONE",
                "compatibility_row_id": compatibility_row_id,
                "rule_firing_set_hash": firing_set_hash,
                "fired_rule_ids": json.dumps(firing_ids, separators=(",", ":")),
                "resolved_label": label,
                "exclusion_reason": "context_incomplete" if code == "POINT_CONTEXT_INCOMPLETE" else pd.NA,
                "semantic_contract_hash": contract.semantic_contract_hash,
            }
        )
        assignment_id = deterministic_id(
            {
                "object_type": "ASSIGNMENT",
                "schema_version": "native.assignment.v1",
                "semantic_contract_hash": contract.semantic_contract_hash,
                "operationalization_id": str(operationalization["operationalization_id"]),
                "task_id": "POINT",
                "horizon_id": "NONE",
                "sample_id": sample_id,
                "resolution_instance_id": resolution_instance_id,
                "assignment_mode": "RULE_EVALUATION",
            }
        )
        assignment_rows.append(
            {
                "assignment_id": assignment_id,
                "sample_id": sample_id,
                "environment_id": row.get("environment_id", "E1"),
                "task_id": "POINT",
                "operationalization_id": str(operationalization["operationalization_id"]),
                "horizon_id": "NONE",
                "semantic_contract_id": contract.semantic_contract_id,
                "semantic_contract_hash": contract.semantic_contract_hash,
                "resolver_contract_id": "POINT_RESOLUTION_V1",
                "continuity_contract_id": "STRICT_15M_PM2_V1",
                "assignment_schema_version": "native.assignment.v1",
                "input_record_hash": str(row.get("record.id")),
                "label": label,
                "resolution_instance_id": resolution_instance_id,
                "resolution_code": code,
                "source_task": pd.NA,
                "source_assignment_id": pd.NA,
                "source_label": pd.NA,
                "assignment_mode": "RULE_EVALUATION",
                "assignment_status": "ASSIGNED",
                "train_inclusion_status": train_inclusion,
                "ambiguity_code": "AUXILIARY_MULTIPLE" if sum(state == "POSITIVE" for state in auxiliary) > 1 else "NONE",
                "diagnostic_tags": json.dumps(_diagnostic_tags(low, auxiliary), separators=(",", ":")),
            }
        )
    return pd.DataFrame(resolution_rows).convert_dtypes(), pd.DataFrame(assignment_rows).convert_dtypes()


def _compatibility_row_id(contract: NativeContract, low: str, auxiliary: list[str]) -> str:
    states = [low, *auxiliary]
    matrix = contract.point_compatibility_matrix
    columns = ["low_state", "thermal_state", "rise_state", "ec_state"]
    rows = matrix.copy()
    for column, state in zip(columns, states, strict=True):
        rows = rows.loc[rows[column].astype("string") == state]
    if len(rows) != 1:
        return "UNMATCHED_COMPATIBILITY_ROW"
    return str(rows.iloc[0].get("compatibility_row_id", rows.index[0]))


def _diagnostic_tags(low: str, auxiliary: list[str]) -> list[str]:
    tags: list[str] = []
    if low == "POSITIVE" and "POSITIVE" in auxiliary[1:]:
        tags.extend(["recovery_or_transition_candidate", "boundary_sensitive"])
    return tags

