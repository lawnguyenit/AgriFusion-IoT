from __future__ import annotations

from typing import Iterable

import pandas as pd

from ..contracts import ACTIVE_FIELDS, Layer1BuildStats, known_catalog_field_names


def build_unknown_catalog_entries(canonical_columns: Iterable[str]) -> list[dict[str, object]]:
    known_names = known_catalog_field_names()
    return [
        {
            "canonical_name": column_name,
            "source_path": "",
            "group": column_name.split(".", 1)[0].upper(),
            "data_type": "unknown",
            "field_status": "UNKNOWN",
            "description": "Canonical field is missing a catalog entry.",
            "used_for_audit": True,
            "eligible_for_model": False,
            "exclusion_reason": "Missing catalog entry; update Layer1 contracts.",
        }
        for column_name in sorted(set(canonical_columns) - known_names)
    ]


def validate_unknown_catalog_fields(
    *,
    canonical_columns: Iterable[str],
    stats: Layer1BuildStats,
    policy: str = "warn",
) -> list[dict[str, object]]:
    if policy not in {"warn", "fail"}:
        raise ValueError(f"Unsupported unknown catalog field policy: {policy}")

    unknown_entries = build_unknown_catalog_entries(canonical_columns)
    if not unknown_entries:
        return []

    column_names = ", ".join(entry["canonical_name"] for entry in unknown_entries)
    message = f"Canonical fields missing catalog entries: {column_names}"
    if policy == "fail":
        raise ValueError(message)

    stats.warnings.append(message)
    return unknown_entries


def validate_canonical_invariants(
    *,
    canonical_df: pd.DataFrame,
    stats: Layer1BuildStats,
) -> None:
    expected_count = stats.input_record_count - stats.excluded_record_count
    if stats.canonical_record_count != expected_count:
        raise ValueError(
            "Canonical record count mismatch: "
            f"{stats.canonical_record_count} != {expected_count}"
        )

    if canonical_df["record.id"].duplicated().any():
        duplicates = canonical_df.loc[
            canonical_df["record.id"].duplicated(),
            "record.id",
        ].tolist()
        raise ValueError(
            f"Duplicate canonical record.id values detected: {duplicates[:5]}"
        )

    active_columns = [
        entry["canonical_name"]
        for entry in ACTIVE_FIELDS
        if entry["field_status"] != "RAW_ONLY"
    ]
    if any("quality" in column for column in active_columns):
        raise ValueError("Active canonical schema must not contain quality fields.")
