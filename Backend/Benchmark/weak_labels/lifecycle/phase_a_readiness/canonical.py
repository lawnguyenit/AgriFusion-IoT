from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from Backend.Benchmark.common.digests import file_sha256, stable_digest
from Backend.Benchmark.protocol_registry.contracts import ProtocolRegistry


STRUCTURAL_COLUMNS = (
    "record.node_id",
    "record.date_key",
    "record.event_key",
    "record.id",
    "record.source_path",
    "record.source_kind",
    "record.ts_sample",
    "record.ts_server",
    "record.ts_device",
    "record.sample_time_local",
    "record.upload_time_local",
    "record.timestamp_mismatch_sec",
    "record.segment_id",
    "record.segment_index",
    "record.segment_boundary_before",
    "record.segment_expected_interval_sec",
    "record.delta_prev_sec",
    "record.gap_flag",
    "record.missing_slot_count",
    "record.is_demo",
    "record.excluded_reason",
)

SENSITIVE_E1_COLUMNS = (
    "sht.temp_c",
    "sht.humidity_pct",
    "sht.packet_present",
    "sht.valid",
    "npk.soil_moisture_pct",
    "npk.ec",
    "npk.packet_present",
    "npk.valid",
)


def load_canonical_audit_inputs(
    canonical_path: Path,
    canonical_manifest_path: Path,
    registry: ProtocolRegistry,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    dict[str, object],
]:
    canonical_path = canonical_path.resolve()
    canonical_manifest_path = canonical_manifest_path.resolve()
    header = pd.read_csv(canonical_path, nrows=0).columns.tolist()
    missing = [column for column in STRUCTURAL_COLUMNS if column not in header]
    if missing:
        raise KeyError(f"Canonical history is missing structural fields: {missing}")
    structural = pd.read_csv(canonical_path, usecols=list(STRUCTURAL_COLUMNS), low_memory=False)
    structural.insert(0, "source_row_locator", pd.Series(range(len(structural)), dtype="Int64"))
    structural["sample_time"] = _parse_local_timestamp_series(structural["record.sample_time_local"])
    structural["upload_time"] = _parse_local_timestamp_series(structural["record.upload_time_local"])
    structural = assign_environment_membership(structural, registry)

    source_file_hash = file_sha256(canonical_path)
    row_hashes = _raw_csv_row_hashes(canonical_path)
    if len(row_hashes) != len(structural):
        raise ValueError("Raw canonical row-hash count does not match parsed row count.")
    structural["source_file_id"] = source_file_hash
    structural["source_row_locator"] = structural["source_row_locator"].astype("Int64")
    structural["canonical_schema_version"] = _canonical_schema_version(canonical_manifest_path)
    structural["canonical_record_hash"] = pd.Series(row_hashes, dtype="string")
    structural["provenance_locator_fingerprint"] = structural.apply(
        lambda row: stable_digest(
            {
                "source_file_id": source_file_hash,
                "source_path": row["record.source_path"],
                "source_row_locator": int(row["source_row_locator"]),
            }
        ),
        axis=1,
    ).astype("string")
    logical_fingerprints = _logical_measurement_fingerprints(canonical_path)
    structural["logical_measurement_fingerprint"] = pd.Series(logical_fingerprints, dtype="string")

    e1_locators = set(
        structural.loc[structural["environment_id"].astype("string") == "E1", "source_row_locator"]
        .dropna()
        .astype(int)
        .tolist()
    )
    e1_sensitive = _read_selected_rows(
        canonical_path,
        row_locators=e1_locators,
        columns=list(dict.fromkeys([*STRUCTURAL_COLUMNS, *SENSITIVE_E1_COLUMNS])),
    )
    e1_sensitive["source_row_locator"] = pd.Series(sorted(e1_locators), dtype="Int64")
    e1_sensitive["sample_time"] = _parse_local_timestamp_series(e1_sensitive["record.sample_time_local"])
    e1_sensitive = e1_sensitive.merge(
        structural.loc[
            structural["environment_id"].astype("string") == "E1",
            [
                "source_row_locator",
                "environment_id",
                "deployment_id",
                "position_id",
                "phase_id",
                "acquisition_regime_id",
                "canonical_record_hash",
                "logical_measurement_fingerprint",
            ],
        ],
        on="source_row_locator",
        how="left",
        validate="one_to_one",
    )

    integrity = _build_integrity_audit(structural)
    membership = _build_membership_audit(structural, registry)
    duplicate_audit = _build_duplicate_audit(structural)
    input_manifest = {
        "canonical_history_path": str(canonical_path),
        "canonical_history_hash": source_file_hash,
        "canonical_manifest_path": str(canonical_manifest_path),
        "canonical_manifest_hash": file_sha256(canonical_manifest_path),
        "canonical_schema_hash": stable_digest(header),
        "canonical_schema_version": _canonical_schema_version(canonical_manifest_path),
        "input_row_count": len(structural),
        "structural_column_allowlist": list(STRUCTURAL_COLUMNS),
        "e1_sensitive_columns": list(SENSITIVE_E1_COLUMNS),
        "sealed_environment_ids": ["E2", "E3_TARGET_PREEXPOSED"],
        "sealed_payload_policy": "STRUCTURAL_COMMITMENTS_ONLY",
    }
    return structural.convert_dtypes(), e1_sensitive.convert_dtypes(), integrity, membership, duplicate_audit, input_manifest


def assign_environment_membership(
    structural: pd.DataFrame,
    registry: ProtocolRegistry,
) -> pd.DataFrame:
    working = structural.copy()
    working["environment_id"] = pd.Series(["UNASSIGNED"] * len(working), dtype="string")
    working["deployment_id"] = pd.Series(["UNASSIGNED"] * len(working), dtype="string")
    working["position_id"] = pd.Series(["UNASSIGNED"] * len(working), dtype="string")
    working["phase_id"] = pd.Series(["UNASSIGNED"] * len(working), dtype="string")
    working["acquisition_regime_id"] = pd.Series(["UNASSIGNED"] * len(working), dtype="string")
    assignment_count = pd.Series([0] * len(working), index=working.index, dtype="Int64")
    for environment in registry.environment_manifest.to_dict(orient="records"):
        start = pd.Timestamp(environment["start_time"])
        end = pd.Timestamp(environment["end_time"])
        mask = working["sample_time"].ge(start) & working["sample_time"].lt(end)
        assignment_count.loc[mask] = assignment_count.loc[mask] + 1
        for column in ("environment_id", "deployment_id", "position_id", "phase_id", "acquisition_regime_id"):
            working.loc[mask, column] = str(environment[column])
    working["environment_assignment_count"] = assignment_count
    return working


def _build_integrity_audit(structural: pd.DataFrame) -> pd.DataFrame:
    duplicate_ids = structural["record.id"].astype("string").duplicated(keep=False)
    rows = [
        _assertion("record_id_globally_unique", not duplicate_ids.any(), int(duplicate_ids.sum())),
        _assertion("timestamps_parseable", structural["sample_time"].notna().all(), int(structural["sample_time"].isna().sum())),
        _assertion(
            "environment_membership_at_most_one",
            structural["environment_assignment_count"].le(1).all(),
            int(structural["environment_assignment_count"].gt(1).sum()),
        ),
        _assertion(
            "environment_membership_complete_for_observed_rows",
            structural["environment_id"].astype("string").ne("UNASSIGNED").all(),
            int(structural["environment_id"].astype("string").eq("UNASSIGNED").sum()),
        ),
        _assertion(
            "canonical_record_hash_present",
            structural["canonical_record_hash"].astype("string").str.len().eq(64).all(),
            int(structural["canonical_record_hash"].astype("string").str.len().ne(64).sum()),
        ),
    ]
    return pd.DataFrame(rows).convert_dtypes()


def _build_membership_audit(structural: pd.DataFrame, registry: ProtocolRegistry) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    visibility = registry.visibility_policy_registry
    for environment in registry.environment_manifest.to_dict(orient="records"):
        environment_id = str(environment["environment_id"])
        observed = structural.loc[structural["environment_id"].astype("string") == environment_id]
        policy = visibility.loc[
            (visibility["protocol_stage_id"].astype("string") == "PHASE_A_AUDIT")
            & (visibility["environment_id"].astype("string") == environment_id)
        ].iloc[0]
        rows.append(
            {
                "environment_id": environment_id,
                "legacy_environment_alias": environment["legacy_environment_alias"],
                "record_count": len(observed),
                "observed_first_time": observed["sample_time"].min().isoformat() if not observed.empty else pd.NA,
                "observed_last_time": observed["sample_time"].max().isoformat() if not observed.empty else pd.NA,
                "membership_exclusive": bool(observed["environment_assignment_count"].eq(1).all()),
                "visibility_status": policy["visibility_status"],
                "sensitive_artifacts_materialized": environment_id == "E1",
                "historical_exposure_status": environment["historical_exposure_status"],
            }
        )
    return pd.DataFrame(rows).convert_dtypes()


def _build_duplicate_audit(structural: pd.DataFrame) -> pd.DataFrame:
    duplicate_mask = structural["logical_measurement_fingerprint"].duplicated(keep=False)
    duplicated = structural.loc[
        duplicate_mask,
        [
            "record.id",
            "environment_id",
            "source_row_locator",
            "provenance_locator_fingerprint",
            "logical_measurement_fingerprint",
        ],
    ].copy()
    if duplicated.empty:
        return pd.DataFrame(
            columns=[
                "record_id",
                "environment_id",
                "source_row_locator",
                "provenance_locator_fingerprint",
                "logical_measurement_fingerprint",
                "cross_environment_duplicate",
            ]
        ).convert_dtypes()
    environment_counts = duplicated.groupby("logical_measurement_fingerprint")["environment_id"].transform("nunique")
    duplicated["cross_environment_duplicate"] = environment_counts.gt(1)
    return duplicated.rename(columns={"record.id": "record_id"}).convert_dtypes()


def _logical_measurement_fingerprints(canonical_path: Path) -> list[str]:
    header = pd.read_csv(canonical_path, nrows=0).columns.tolist()
    payload_columns = [
        column
        for column in header
        if column in {"record.node_id", "record.ts_sample"} or column.startswith(("sht.", "npk."))
    ]
    payload = pd.read_csv(canonical_path, usecols=payload_columns, dtype="string", keep_default_na=False)
    return [
        stable_digest({column: row[column] for column in payload_columns})
        for row in payload.to_dict(orient="records")
    ]


def _read_selected_rows(canonical_path: Path, *, row_locators: set[int], columns: list[str]) -> pd.DataFrame:
    if not row_locators:
        return pd.DataFrame(columns=columns)
    selected = pd.read_csv(
        canonical_path,
        usecols=columns,
        skiprows=lambda line_number: line_number > 0 and (line_number - 1) not in row_locators,
        low_memory=False,
    )
    if len(selected) != len(row_locators):
        raise ValueError("E1 selective read did not return the registered E1 row count.")
    return selected


def _raw_csv_row_hashes(path: Path) -> list[str]:
    hashes: list[str] = []
    with path.open("rb") as handle:
        handle.readline()
        for line in handle:
            hashes.append(hashlib.sha256(line.rstrip(b"\r\n")).hexdigest())
    return hashes


def _canonical_schema_version(manifest_path: Path) -> str:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return str(payload.get("schema_version", "UNKNOWN"))


def _parse_local_timestamp_series(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    if getattr(parsed.dt, "tz", None) is None:
        return parsed.dt.tz_localize("Asia/Ho_Chi_Minh", ambiguous="NaT", nonexistent="NaT")
    return parsed.dt.tz_convert("Asia/Ho_Chi_Minh")


def _assertion(assertion_id: str, passed: bool, violation_count: int) -> dict[str, object]:
    return {
        "assertion_id": assertion_id,
        "status": "PASS" if passed else "FAIL",
        "violation_count": violation_count,
    }
