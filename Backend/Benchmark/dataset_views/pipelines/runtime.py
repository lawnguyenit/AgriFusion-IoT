from __future__ import annotations

from pathlib import Path

from Backend.Benchmark.dataset_views.configs import (
    DEFAULT_PUBLIC_VIEW_IDS,
    get_taxonomy_entry,
    get_view_definition,
    resolve_view_ids,
)
from Backend.Benchmark.dataset_views.contracts import MaterializationConfig
from Backend.Benchmark.dataset_views.reports import (
    build_taxonomy_drift_audit_payload,
)


V3_VIEW_IDS: tuple[str, ...] = ("v3_direct", "v3_derived", "v3_independent", "v3_pre_onset")
V6_VIEW_IDS: tuple[str, ...] = ("v6_sequence_8h",)


def resolve_selected_public_view_ids(config: MaterializationConfig) -> tuple[str, ...]:
    return resolve_view_ids(tuple(config.selected_views or DEFAULT_PUBLIC_VIEW_IDS))


def validate_requested_views(selected_public_view_ids: tuple[str, ...], config: MaterializationConfig) -> None:
    for view_id in selected_public_view_ids:
        taxonomy_entry = get_taxonomy_entry(view_id)
        if taxonomy_entry.status in {"ACTIVE_VALIDATED", "ACTIVE_OPERATIONAL_LINEAGE", "ACTIVE_ENVIRONMENTAL_SEQUENCE"}:
            continue
        if taxonomy_entry.semantic_view_id == "v4_hybrid":
            raise ValueError(f"{view_id} is reserved for a later batch and is not implemented in this task.")
        if taxonomy_entry.semantic_view_id == "v5_proxy_reduced":
            raise ValueError(
                "v5_proxy_reduced is blocked until a complete validated label-rule dependency registry is available."
            )
        raise ValueError(f"Unsupported public materialization state for '{view_id}'.")


def load_requested_legacy_taxonomy_audit(config: MaterializationConfig) -> tuple[Path | None, dict[str, object] | None]:
    if config.legacy_taxonomy_audit_run_path is None:
        return None, None
    audited_run_dir = config.legacy_taxonomy_audit_run_path.resolve()
    if not audited_run_dir.exists():
        raise FileNotFoundError(f"Legacy taxonomy audit run not found: {audited_run_dir}")
    return audited_run_dir, build_taxonomy_drift_audit_payload(audited_run_dir)


def requires_segment_manifest(selected_view_ids: tuple[str, ...]) -> bool:
    return any(
        get_view_definition(view_id).selection_mode in {
            "window_engineered",
            "operational_lineage_direct",
            "operational_lineage_derived",
            "operational_lineage_independent",
            "operational_lineage_pre_onset",
            "environmental_sequence_8h",
        }
        for view_id in selected_view_ids
    )


def has_v3_views(selected_view_ids: tuple[str, ...]) -> bool:
    return any(view_id in V3_VIEW_IDS for view_id in selected_view_ids)


def has_v6_views(selected_view_ids: tuple[str, ...]) -> bool:
    return any(view_id in V6_VIEW_IDS for view_id in selected_view_ids)


def resolve_nonpublic_drafts(
    *,
    config: MaterializationConfig,
    selected_public_view_ids: tuple[str, ...],
) -> tuple[str, ...]:
    del config
    del selected_public_view_ids
    return ()
