from __future__ import annotations

from pathlib import Path

from Backend.Benchmark.dataset_views.configs import (
    DEFAULT_PUBLIC_VIEW_IDS,
    get_taxonomy_entry,
    get_view_definition,
    resolve_view_ids,
)
from Backend.Benchmark.dataset_views.contracts import MaterializationConfig

def resolve_selected_public_view_ids(config: MaterializationConfig) -> tuple[str, ...]:
    return resolve_view_ids(tuple(config.selected_views or DEFAULT_PUBLIC_VIEW_IDS))


def validate_requested_views(selected_public_view_ids: tuple[str, ...], config: MaterializationConfig) -> None:
    for view_id in selected_public_view_ids:
        taxonomy_entry = get_taxonomy_entry(view_id)
        if taxonomy_entry.status == "ACTIVE_VALIDATED":
            continue
        if taxonomy_entry.semantic_view_id == "v4_hybrid":
            raise ValueError(f"{view_id} is reserved for a later batch and is not implemented in this task.")
        raise ValueError(f"Unsupported public materialization state for '{view_id}'.")


def load_taxonomy_audit_if_available(output_root: Path) -> tuple[Path | None, dict[str, object] | None]:
    return None, None


def requires_segment_manifest(selected_view_ids: tuple[str, ...]) -> bool:
    return any(
        get_view_definition(view_id).selection_mode == "window_engineered"
        for view_id in selected_view_ids
    )
