from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from Backend.Benchmark.protocol_registry import load_protocol_registry
from Backend.Benchmark.weak_labels.contracts.native import NativeContract, NativeContractError
from Backend.Benchmark.weak_labels.infrastructure.shared.helpers import resolve_local_timestamp_series


CANONICAL_REQUIRED_COLUMNS = (
    "record.id",
    "record.segment_id",
    "record.sample_time_local",
    "npk.soil_moisture_pct",
    "npk.ec",
    "sht.temp_c",
    "sht.humidity_pct",
)


def load_e1_authorized_canonical(
    *,
    canonical_history_path: Path,
    canonical_evidence_schema_path: Path,
    protocol_registry_run_dir: Path,
    contract: NativeContract,
) -> tuple[pd.DataFrame, dict[str, object]]:
    registry = load_protocol_registry(protocol_registry_run_dir.resolve())
    if registry.run_manifest.get("semantic_contract_hash") not in {None, contract.semantic_contract_hash}:
        raise NativeContractError("Protocol registry semantic contract hash does not match native contract.")
    environment_rows = registry.environment_manifest.loc[
        registry.environment_manifest["environment_id"].astype("string") == "E1"
    ]
    if len(environment_rows) != 1:
        raise NativeContractError("Protocol registry must contain exactly one E1 environment.")
    e1 = environment_rows.iloc[0]
    start = pd.Timestamp(e1["start_time"], tz="UTC")
    end = pd.Timestamp(e1["end_time"], tz="UTC")
    canonical_path = canonical_history_path.resolve()
    usecols = _resolve_allowlisted_columns(canonical_evidence_schema_path, canonical_path)
    # First pass reads structural membership only.  The second pass asks the
    # CSV reader to materialize payload rows only for the authorized E1 row
    # numbers, so E2/E3 sensor payload never enters the native-engine frame.
    structural = pd.read_csv(
        canonical_path,
        usecols=["record.id", "record.segment_id", "record.sample_time_local"],
        low_memory=False,
    )
    structural_sample = resolve_local_timestamp_series(structural).dt.tz_convert("UTC")
    authorized_positions = structural.index[(structural_sample >= start) & (structural_sample < end)].tolist()
    if not authorized_positions:
        raise NativeContractError("No E1 canonical records are available for native execution.")
    authorized_file_rows = {int(position) + 1 for position in authorized_positions}
    payload = pd.read_csv(
        canonical_path,
        usecols=usecols,
        low_memory=False,
        skiprows=lambda row_number: row_number != 0 and row_number not in authorized_file_rows,
    ).convert_dtypes()
    sample = resolve_local_timestamp_series(payload).dt.tz_convert("UTC")
    payload["sample_time_utc"] = sample
    payload["environment_id"] = "E1"
    frame = payload
    missing = [column for column in CANONICAL_REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise NativeContractError(f"Canonical evidence input is missing required fields: {missing}")
    if frame["record.id"].astype("string").duplicated().any():
        raise NativeContractError("E1 record.id values must be globally unique.")
    if frame["sample_time_utc"].isna().any():
        raise NativeContractError("E1 sample timestamps must parse successfully.")
    frame = frame.sort_values(["record.segment_id", "sample_time_utc", "record.id"], kind="stable").reset_index(drop=True)
    metadata = {
        "environment_id": "E1",
        "environment_start_utc": start.isoformat(),
        "environment_end_utc": end.isoformat(),
        "authorized_record_count": int(len(frame)),
        "sensitive_environment_ids_loaded": ["E1"],
        "sensitive_environment_ids_denied": ["E2", "E3_TARGET_PREEXPOSED", "E3"],
    }
    return frame, metadata


def _resolve_allowlisted_columns(schema_path: Path, canonical_path: Path) -> list[str]:
    header = pd.read_csv(canonical_path.resolve(), nrows=0).columns.tolist()
    if not schema_path.exists():
        required = [column for column in CANONICAL_REQUIRED_COLUMNS if column in header]
        if len(required) != len(CANONICAL_REQUIRED_COLUMNS):
            raise NativeContractError(f"Missing canonical evidence schema: {schema_path}")
        return required + [column for column in ("record.upload_time_local", "record.source_path", "record.segment_boundary_before") if column in header]
    schema = pd.read_csv(schema_path.resolve()).convert_dtypes()
    field_column = "canonical_field" if "canonical_field" in schema.columns else "field_name" if "field_name" in schema.columns else None
    if field_column is None:
        raise NativeContractError("Canonical evidence schema requires canonical_field or field_name.")
    requested = [str(value) for value in schema[field_column].dropna().tolist()]
    required = list(dict.fromkeys(CANONICAL_REQUIRED_COLUMNS + tuple(requested)))
    missing = [column for column in required if column not in header]
    if missing:
        raise NativeContractError(f"Canonical evidence schema references missing columns: {missing}")
    return required
