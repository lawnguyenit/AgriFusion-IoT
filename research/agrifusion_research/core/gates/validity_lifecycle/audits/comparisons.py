from __future__ import annotations

import hashlib

import pandas as pd


def build_comparison_hash_audit(
    comparison_training_manifest: pd.DataFrame,
    observation_registry: pd.DataFrame,
) -> pd.DataFrame:
    registry_lookup = observation_registry.set_index("sample_id", drop=False)
    rows: list[dict[str, object]] = []
    group_columns = ["comparison_id", "matched_cohort_id", "fold_id", "partition"]
    for keys, group in comparison_training_manifest.groupby(group_columns, dropna=False, sort=False):
        comparison_id, matched_cohort_id, fold_id, partition = keys
        left = group.loc[group["comparison_side"].astype("string") == "left"].copy()
        right = group.loc[group["comparison_side"].astype("string") == "right"].copy()
        left_samples = left["sample_id"].astype("string").dropna().tolist()
        right_samples = right["sample_id"].astype("string").dropna().tolist()
        left_manifest_hash = _first_unique_value(left["record_set_hash"])
        right_manifest_hash = _first_unique_value(right["record_set_hash"])
        left_derived_hash = _sample_hash(left_samples)
        right_derived_hash = _sample_hash(right_samples)
        left_targets = _lookup_series(left_samples, registry_lookup, "point_target")
        right_targets = _lookup_series(right_samples, registry_lookup, "point_target")
        left_timestamps = _lookup_series(left_samples, registry_lookup, "timestamp")
        right_timestamps = _lookup_series(right_samples, registry_lookup, "timestamp")
        target_match = left_targets == right_targets
        timestamp_match = _range_signature(left_timestamps) == _range_signature(right_timestamps)
        sample_count_match = len(left_samples) == len(right_samples)
        manifest_hash_match = left_manifest_hash == right_manifest_hash
        derived_hash_match = left_derived_hash == right_derived_hash
        lookup_complete = len(left_targets) == len(left_samples) and len(right_targets) == len(right_samples)
        status = "PASS" if all((sample_count_match, manifest_hash_match, derived_hash_match, target_match, timestamp_match, lookup_complete)) else "FAIL"
        rows.append(
            {
                "comparison_id": comparison_id,
                "matched_cohort_id": matched_cohort_id,
                "fold_id": fold_id,
                "partition": partition,
                "left_row_count": len(left_samples),
                "right_row_count": len(right_samples),
                "sample_count_match": sample_count_match,
                "left_manifest_hash": left_manifest_hash,
                "right_manifest_hash": right_manifest_hash,
                "manifest_hash_match": manifest_hash_match,
                "left_sample_hash": left_derived_hash,
                "right_sample_hash": right_derived_hash,
                "derived_hash_match": derived_hash_match,
                "target_match": target_match,
                "timestamp_range_match": timestamp_match,
                "lookup_complete": lookup_complete,
                "status": status,
            }
        )
    return pd.DataFrame(rows).convert_dtypes()


def _first_unique_value(series: pd.Series) -> str:
    values = series.astype("string").dropna().unique().tolist()
    return str(values[0]) if values else ""


def _sample_hash(sample_ids: list[str]) -> str:
    digest = hashlib.sha256()
    for sample_id in sample_ids:
        digest.update(sample_id.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _lookup_series(sample_ids: list[str], registry_lookup: pd.DataFrame, column_name: str) -> list[str]:
    values: list[str] = []
    for sample_id in sample_ids:
        if sample_id not in registry_lookup.index:
            continue
        values.append(str(registry_lookup.loc[sample_id, column_name]))
    return values


def _range_signature(values: list[str]) -> tuple[str, str]:
    if not values:
        return ("", "")
    ordered = sorted(values)
    return ordered[0], ordered[-1]
