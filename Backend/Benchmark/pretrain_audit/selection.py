from __future__ import annotations

import json
from pathlib import Path

from Backend.Benchmark.dataset_views.validators import stable_hash_object


FORBIDDEN_FEATURE_PREFIXES = ("criterion.", "target.", "label.", "split.", "audit.")
IDENTIFIER_COLUMNS = {"sample_id", "source_row_position"}
FORBIDDEN_EXACT_NAMES = {
    "timestamp", "ts", "datetime", "date", "time", "row_id", "record_id",
    "device_id", "entity_id", "fold_id", "partition", "source_row_number",
}


def resolve_feature_selection(
    *,
    registry_path: Path,
    selected_groups: tuple[str, ...],
    available_columns: list[str],
) -> tuple[list[str], dict[str, object]]:
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    if not selected_groups:
        raise ValueError("Select at least one feature group.")
    if len(set(selected_groups)) != len(selected_groups):
        raise ValueError("Selected feature groups must be unique.")
    groups = registry.get("feature_groups", {})
    missing_groups = [name for name in selected_groups if name not in groups]
    if missing_groups:
        raise ValueError(f"Selected feature groups are absent from the registry: {missing_groups}")
    columns: list[str] = []
    for group in selected_groups:
        group_role = registry.get("feature_group_roles", {}).get(group)
        if group_role == "diagnostic_only":
            raise ValueError(f"Feature group {group!r} is diagnostic-only and cannot enter model audit X.")
        group_columns = groups[group]["columns"]
        if stable_hash_object(group_columns) != groups[group].get("columns_hash"):
            raise ValueError(f"Feature group {group!r} column hash does not match its registry.")
        columns.extend(group_columns)
    if len(columns) != len(set(columns)):
        raise ValueError("Selected feature groups overlap; resolve overlap explicitly before audit.")
    ordered_features = registry.get("ordered_feature_columns", [])
    selected_set = set(columns)
    allowlist = [name for name in ordered_features if name in selected_set]
    if len(allowlist) != len(selected_set):
        raise ValueError("Feature registry contains duplicate or unrecognized group columns.")
    unavailable = [name for name in allowlist if name not in available_columns]
    if unavailable:
        raise ValueError(f"Registry-selected features are absent from the matrix: {unavailable}")
    forbidden = [
        name
        for name in allowlist
        if name in IDENTIFIER_COLUMNS
        or str(name).strip().lower() in FORBIDDEN_EXACT_NAMES
        or str(name).strip().lower().startswith(FORBIDDEN_FEATURE_PREFIXES)
        or str(name).strip().lower().startswith(("target_", "label_", "criterion_", "audit_", "split_"))
    ]
    if forbidden:
        raise ValueError(f"Non-feature columns entered the selected feature set: {forbidden}")
    excluded_sources = [str(name) for name in registry.get("excluded_target_source_columns", [])]
    target_descendants = [
        name for name in allowlist
        if any(name == source or name.startswith(f"{source}__") or name.startswith(f"{source}_") for source in excluded_sources)
    ]
    if target_descendants:
        raise ValueError(f"Target source fields and their derived descendants cannot enter X: {target_descendants}")
    selection = {
        "selected_groups": list(selected_groups),
        "ordered_feature_columns": allowlist,
        "ordered_feature_columns_hash": stable_hash_object(allowlist),
    }
    return allowlist, selection
