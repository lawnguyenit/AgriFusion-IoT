from __future__ import annotations

from typing import Any

from Backend.Benchmark.dataset_views.configs import (
    TAXONOMY_VERSION,
    get_taxonomy_entry,
    get_view_definition,
)


PRIMARY_PUBLIC_SCOPE_VIEW_IDS: tuple[str, ...] = (
    "v0_minimal_sensor",
    "v1_sensor_row",
    "v2_minimal_sensor_window_3h",
    "v2_sensor_row_window_3h",
)

OPTIONAL_EXPLICIT_VIEW_IDS: tuple[str, ...] = (
    "v2_minimal_sensor_window_8h",
    "v2_sensor_row_window_8h",
)


def build_current_scope_taxonomy_report_payload(selected_view_ids: tuple[str, ...]) -> dict[str, Any]:
    return {
        "taxonomy_version": TAXONOMY_VERSION,
        "scope_kind": "current_public_scope",
        "primary_public_scope_view_ids": list(PRIMARY_PUBLIC_SCOPE_VIEW_IDS),
        "default_alias_resolution": {
            "v0": ["v0_minimal_sensor"],
            "v1": ["v1_sensor_row"],
            "v2": ["v2_minimal_sensor_window_3h", "v2_sensor_row_window_3h"],
        },
        "optional_explicit_views": list(OPTIONAL_EXPLICIT_VIEW_IDS),
        "selected_views": [_selected_view_summary(view_id) for view_id in selected_view_ids],
    }


def _selected_view_summary(view_id: str) -> dict[str, object]:
    taxonomy_entry = get_taxonomy_entry(view_id)
    view_definition = get_view_definition(view_id)
    return {
        "view_id": view_id,
        "numeric_alias": taxonomy_entry.numeric_alias,
        "grain": taxonomy_entry.grain,
        "selection_kind": taxonomy_entry.selection_kind,
        "description": view_definition.description,
        "scope_role": "PRIMARY_PUBLIC_SCOPE" if view_id in PRIMARY_PUBLIC_SCOPE_VIEW_IDS else "OPTIONAL_EXPLICIT",
    }
