from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd


ROLE_GROUPS = {
    "measurements": "measurement",
    "acquisition_metadata": "acquisition_metadata",
    "group_or_transport": "group_or_transport",
    "posthoc_operational_evidence": "operational_evidence",
}


def flatten_column_roles(
    manifest: Mapping[str, Any],
    feature_catalog: pd.DataFrame | None = None,
) -> dict[str, str]:
    """Normalize external-intake role declarations without guessing from names."""
    raw_roles = manifest.get("column_roles", {})
    roles: dict[str, str] = {}
    if isinstance(raw_roles, Mapping):
        for name, role in raw_roles.items():
            if isinstance(role, list):
                normalized = ROLE_GROUPS.get(str(name), str(name))
                roles.update({str(column): normalized for column in role})
            else:
                roles[str(name)] = str(role)
    elif isinstance(raw_roles, list):
        roles.update({str(name): "measurement" for name in raw_roles})

    audit = manifest.get("adapter_audit", {})
    nested = audit.get("feature_and_criterion_roles", {}) if isinstance(audit, Mapping) else {}
    if isinstance(nested, Mapping):
        for group, names in nested.items():
            normalized = ROLE_GROUPS.get(str(group), str(group))
            if isinstance(names, list):
                for name in names:
                    roles.setdefault(str(name), normalized)
    if feature_catalog is not None:
        required = {"canonical_name", "feature_role"}
        if not required.issubset(feature_catalog.columns):
            raise ValueError(f"Feature catalog is missing required columns: {sorted(required - set(feature_catalog.columns))}.")
        for row in feature_catalog.loc[:, ["canonical_name", "feature_role"]].itertuples(index=False):
            field, feature_role = str(row.canonical_name), str(row.feature_role)
            if feature_role == "measurement":
                roles[field] = "measurement"
            else:
                roles.setdefault(field, feature_role)
    return roles


def build_evidence_inventory(
    frame: pd.DataFrame,
    manifest: Mapping[str, Any],
    *,
    min_observations: int = 100,
    dataset_id: str | None = None,
    feature_catalog: pd.DataFrame | None = None,
    timestamp_column: str | None = None,
    entity_column: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Summarize available evidence and propose only relative observed states.

    Semantic outcomes such as disease, safe air, gas concentration, or plant
    stress are never inferred from a column name by this inventory step.
    """
    if frame.empty:
        raise ValueError("Claim discovery requires at least one canonical row.")
    if min_observations < 1:
        raise ValueError("min_observations must be positive.")

    dataset_id = dataset_id or str(manifest.get("dataset_id", "unknown_dataset"))
    roles = flatten_column_roles(manifest, feature_catalog)
    if timestamp_column is None:
        timestamp_column = "timestamp" if "timestamp" in frame else None
    if timestamp_column is not None and timestamp_column not in frame:
        raise ValueError(f"Timestamp column {timestamp_column!r} is not present in canonical data.")
    if entity_column is not None and entity_column not in frame:
        raise ValueError(f"Entity column {entity_column!r} is not present in canonical data.")
    timestamps = pd.to_datetime(frame[timestamp_column], errors="coerce") if timestamp_column else None
    cadence_groups = frame[entity_column] if entity_column else (frame["entity_id"] if "entity_id" in frame else None)
    cadence = _cadence_summary(timestamps, cadence_groups) if timestamps is not None else {}
    rows: list[dict[str, Any]] = []

    for column in frame.columns:
        name = str(column)
        if name in {"sample_id", timestamp_column}:
            continue
        role = roles.get(name, _structural_role(name))
        is_datetime = pd.api.types.is_datetime64_any_dtype(frame[column].dtype)
        numeric = pd.to_numeric(frame[column], errors="coerce") if not is_datetime else pd.Series(pd.NA, index=frame.index, dtype="Float64")
        if pd.api.types.is_bool_dtype(numeric.dtype):
            numeric = numeric.astype("Float64")
        observed = numeric.dropna()
        is_numeric = len(observed) > 0 and not is_datetime
        direct_measurement = role in {"measurement", "observed_measurement"}
        enough_support = len(observed) >= min_observations
        candidate_status = (
            "RELATIVE_STATE_CANDIDATE"
            if direct_measurement and is_numeric and enough_support
            else "NO_AUTOMATIC_LABEL_CANDIDATE"
        )
        reason = (
            "Numeric observed measurement supports relative low/high state hypotheses only; "
            "this is not a semantic outcome or ground truth."
            if candidate_status == "RELATIVE_STATE_CANDIDATE"
            else _no_candidate_reason(role, len(observed), min_observations, is_numeric)
        )
        rows.append({
            "dataset_id": dataset_id,
            "field": name,
            "role": role,
            "dtype": str(frame[column].dtype),
            "row_count": int(len(frame)),
            "observed_count": int(frame[column].notna().sum()),
            "numeric_observed_count": int(len(observed)),
            "missing_count": int(frame[column].isna().sum()),
            "missing_fraction": float(frame[column].isna().mean()),
            "numeric": bool(is_numeric),
            "unique_observed": int(frame[column].nunique(dropna=True)),
            "minimum": _optional_float(observed.min()) if is_numeric else None,
            "q05": _optional_float(observed.quantile(0.05)) if is_numeric else None,
            "median": _optional_float(observed.median()) if is_numeric else None,
            "q95": _optional_float(observed.quantile(0.95)) if is_numeric else None,
            "maximum": _optional_float(observed.max()) if is_numeric else None,
            "candidate_claims": ["relative_low_state", "relative_high_state"]
            if candidate_status == "RELATIVE_STATE_CANDIDATE" else [],
            "candidate_status": candidate_status,
            "assessment_reason": reason,
        })

    inventory = pd.DataFrame(rows)
    metadata = {
        "dataset_id": dataset_id,
        "row_count": int(len(frame)),
        "timestamp_column": timestamp_column,
        "entity_column": entity_column or ("entity_id" if "entity_id" in frame else None),
        "time_coverage_start": timestamps.min().isoformat() if timestamps is not None and timestamps.notna().any() else None,
        "time_coverage_end": timestamps.max().isoformat() if timestamps is not None and timestamps.notna().any() else None,
        "cadence": cadence,
        "entity_count": int(frame[cadence_groups.name].nunique(dropna=True)) if cadence_groups is not None else 1,
        "column_count": int(len(frame.columns)),
        "candidate_state_count": int(inventory["candidate_status"].eq("RELATIVE_STATE_CANDIDATE").sum()),
        "semantic_claims_auto_inferred": False,
        "criterion_role_columns": sorted(name for name, role in roles.items() if role == "criterion_only"),
        "claim_generation_gate": "REVIEW_REQUIRED",
    }
    return inventory, metadata


def _cadence_summary(
    timestamps: pd.Series,
    groups: pd.Series | None = None,
) -> dict[str, Any]:
    if groups is not None:
        per_entity: dict[str, dict[str, float | int | None]] = {}
        intervals: list[pd.Series] = []
        for entity, indexes in groups.groupby(groups, dropna=False).groups.items():
            if pd.isna(entity):
                continue
            gaps = _intervals(timestamps.loc[indexes])
            per_entity[str(entity)] = _summarize_gaps(gaps)
            intervals.append(gaps)
        medians = [row["median_minutes"] for row in per_entity.values() if row["median_minutes"] is not None]
        aggregate = _summarize_gaps(pd.concat(intervals, ignore_index=True) if intervals else pd.Series(dtype="float64"))
        aggregate["median_entity_median_minutes"] = float(pd.Series(medians).median()) if medians else None
        aggregate["per_entity"] = per_entity
        return aggregate
    return _summarize_gaps(_intervals(timestamps))


def _intervals(timestamps: pd.Series) -> pd.Series:
    ordered = timestamps.dropna().sort_values().drop_duplicates()
    return ordered.diff().dt.total_seconds().div(60).dropna()


def _summarize_gaps(gaps: pd.Series) -> dict[str, float | int | None]:
    if gaps.empty:
        return {"interval_count": 0, "median_minutes": None, "p10_minutes": None, "p90_minutes": None}
    return {
        "interval_count": int(len(gaps)),
        "median_minutes": float(gaps.median()),
        "p10_minutes": float(gaps.quantile(0.10)),
        "p90_minutes": float(gaps.quantile(0.90)),
    }


def _structural_role(column: str) -> str:
    if column == "source_row_number":
        return "provenance_metadata"
    if column.endswith("_timestamp"):
        return "temporal_alignment_metadata"
    if column.endswith("_device_id") or column.endswith("_device_identifier"):
        return "device_metadata"
    if column.endswith("_alignment_age_sec"):
        return "temporal_alignment_metadata"
    if column.startswith("criterion.") or column.endswith("(GT)"):
        return "criterion_only"
    if column in {"entity_id", "line", "device_identifier"}:
        return "group_or_transport"
    return "unclassified"


def _no_candidate_reason(role: str, count: int, minimum: int, is_numeric: bool) -> str:
    if role == "criterion_only":
        return "Independent criterion is not an automatic label here; it may define Y under a reviewed target contract, but must never enter X."
    if role == "operational_evidence":
        return "Operational evidence is inventoried separately; define an explicit action/task claim before labeling."
    if not is_numeric:
        return "Non-numeric or wholly missing field; no automatic relative-state proposal."
    if not role in {"measurement", "observed_measurement"}:
        return f"Role {role!r} is not registered as a direct measurement; no automatic label proposal."
    return f"Only {count} observed values; configured minimum is {minimum}."


def _optional_float(value: Any) -> float | None:
    return None if pd.isna(value) else float(value)
