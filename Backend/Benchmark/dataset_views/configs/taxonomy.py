from __future__ import annotations

from Backend.Benchmark.dataset_views.contracts import TaxonomyEntry


TAXONOMY_VERSION = "2026-07-29.v0-v1-v2-active"

_REGISTRY: tuple[TaxonomyEntry, ...] = (
    TaxonomyEntry(
        semantic_view_id="v0_minimal_sensor",
        numeric_alias="v0",
        status="ACTIVE_VALIDATED",
        batch="Batch 1",
        grain="row",
        selection_kind="explicit_measurements",
        public_selectable=True,
        notes="Approved minimal sensor measurement view.",
    ),
    TaxonomyEntry(
        semantic_view_id="v1_sensor_row",
        numeric_alias="v1",
        status="ACTIVE_VALIDATED",
        batch="Batch 1",
        grain="row",
        selection_kind="explicit_measurements",
        public_selectable=True,
        notes="Approved nine-feature sensor-row measurement view.",
    ),
    TaxonomyEntry(
        semantic_view_id="v2_minimal_sensor_window_3h",
        numeric_alias="v2m3",
        status="ACTIVE_VALIDATED",
        batch="Batch 1",
        grain="window",
        selection_kind="engineered_window",
        public_selectable=True,
        notes="Minimal sensor set with ISR plus only the 3h observed-only continuity-aware temporal block.",
    ),
    TaxonomyEntry(
        semantic_view_id="v2_minimal_sensor_window_8h",
        numeric_alias="v2m8",
        status="ACTIVE_VALIDATED",
        batch="Batch 1",
        grain="window",
        selection_kind="engineered_window",
        public_selectable=True,
        notes="Minimal sensor set with ISR plus only the 8h observed-only continuity-aware temporal block.",
    ),
    TaxonomyEntry(
        semantic_view_id="v2_sensor_row_window_3h",
        numeric_alias="v2r3",
        status="ACTIVE_VALIDATED",
        batch="Batch 1",
        grain="window",
        selection_kind="engineered_window",
        public_selectable=True,
        notes="Nine-feature sensor-row set with ISR plus only the 3h observed-only continuity-aware temporal block.",
    ),
    TaxonomyEntry(
        semantic_view_id="v2_sensor_row_window_8h",
        numeric_alias="v2r8",
        status="ACTIVE_VALIDATED",
        batch="Batch 1",
        grain="window",
        selection_kind="engineered_window",
        public_selectable=True,
        notes="Nine-feature sensor-row set with ISR plus only the 8h observed-only continuity-aware temporal block.",
    ),
    TaxonomyEntry(
        semantic_view_id="v2_sensor_window",
        numeric_alias="v2legacy",
        status="ACTIVE_VALIDATED",
        batch="Compatibility",
        grain="window",
        selection_kind="engineered_window",
        public_selectable=False,
        notes="Legacy bundled V2 compatibility view containing v1 ISR plus both 3h and 8h temporal blocks.",
    ),
    TaxonomyEntry(
        semantic_view_id="v4_hybrid",
        numeric_alias="v4",
        status="RESERVED_NOT_IMPLEMENTED",
        batch="Batch 3",
        grain="row",
        selection_kind="reserved",
        public_selectable=True,
        notes="Reserved for hybrid sensor plus metadata row features after V3 stabilization.",
    ),
)

LEGACY_DRIFTED_NAMES: dict[str, str] = {
    "v1_full_sensor": "Legacy drifted view id 'v1_full_sensor' is no longer supported. Use 'v1_sensor_row'.",
    "v3": "View family 'v3' has been removed from the active benchmark surface. Only v0, v1, and v2 remain supported.",
    "v3_direct": "View 'v3_direct' has been removed from the active benchmark surface. Only v0, v1, and v2 remain supported.",
    "v3_derived": "View 'v3_derived' has been removed from the active benchmark surface. Only v0, v1, and v2 remain supported.",
    "v3_independent": "View 'v3_independent' has been removed from the active benchmark surface. Only v0, v1, and v2 remain supported.",
    "v3_pre_onset": "View 'v3_pre_onset' has been removed from the active benchmark surface. Only v0, v1, and v2 remain supported.",
    "v3_metadata_only": (
        "Legacy reserved id 'v3_metadata_only' is no longer supported because the V3 family has been removed "
        "from the active benchmark surface."
    ),
    "v5": "View family 'v5' has been removed from the active benchmark surface. Only v0, v1, and v2 remain supported.",
    "v5_proxy_reduced": "View 'v5_proxy_reduced' has been removed from the active benchmark surface.",
    "v5_proxy_reduced_draft": "View 'v5_proxy_reduced_draft' has been removed from the active benchmark surface.",
    "draft": "Draft proxy-reduced views have been removed from the active benchmark surface.",
    "v6": "View family 'v6' has been removed from the active benchmark surface. Only v0, v1, and v2 remain supported.",
    "v6_proxy_reduced": (
        "Legacy drifted view id 'v6_proxy_reduced' is no longer supported because the V6 family has been removed "
        "from the active benchmark surface."
    ),
    "v6_event_level": (
        "Legacy drifted view id 'v6_event_level' is no longer supported because the V6 family has been removed "
        "from the active benchmark surface."
    ),
    "v6a_window_45m": (
        "Legacy drifted view id 'v6a_window_45m' is no longer supported because the V6 family has been removed "
        "from the active benchmark surface."
    ),
    "v6a_window_90m": (
        "Legacy drifted view id 'v6a_window_90m' is no longer supported because the V6 family has been removed "
        "from the active benchmark surface."
    ),
    "v6a_window_180m": (
        "Legacy drifted view id 'v6a_window_180m' is no longer supported because the V6 family has been removed "
        "from the active benchmark surface."
    ),
    "v6b_continuous_sequence": (
        "Legacy drifted view id 'v6b_continuous_sequence' is no longer supported because the V6 family has been removed "
        "from the active benchmark surface."
    ),
    "v6c_decoded_episode_registry": (
        "Legacy drifted view id 'v6c_decoded_episode_registry' is no longer supported because the V6 family has been removed "
        "from the active benchmark surface."
    ),
}

DEFAULT_PUBLIC_VIEW_IDS: tuple[str, ...] = (
    "v0_minimal_sensor",
    "v1_sensor_row",
)

EPISODE_REQUIRED_COLUMNS: tuple[str, ...] = (
    "episode_id",
    "episode_label",
    "start_record_id",
    "end_record_id",
    "member_record_ids",
    "deployment_segment",
    "episode_eligibility",
)


def taxonomy_entries() -> tuple[TaxonomyEntry, ...]:
    return _REGISTRY


def taxonomy_index() -> dict[str, TaxonomyEntry]:
    return {entry.semantic_view_id: entry for entry in _REGISTRY}


def public_selectable_view_ids() -> tuple[str, ...]:
    return tuple(entry.semantic_view_id for entry in _REGISTRY if entry.public_selectable)


def get_taxonomy_entry(view_id: str) -> TaxonomyEntry:
    try:
        return taxonomy_index()[view_id]
    except KeyError as exc:
        raise KeyError(f"Unsupported dataset view '{view_id}'.") from exc


def resolve_view_id(requested_view_id: str) -> str:
    normalized = requested_view_id.strip()
    if normalized in LEGACY_DRIFTED_NAMES:
        raise ValueError(LEGACY_DRIFTED_NAMES[normalized])
    index = taxonomy_index()
    if normalized in index:
        return normalized
    alias_matches = [
        entry.semantic_view_id
        for entry in _REGISTRY
        if entry.numeric_alias == normalized and entry.public_selectable
    ]
    if len(alias_matches) == 1:
        return alias_matches[0]
    if len(alias_matches) > 1:
        raise ValueError(f"Numeric alias '{requested_view_id}' maps to multiple semantic meanings.")
    raise ValueError(f"Unsupported dataset view '{requested_view_id}'.")


def resolve_view_ids(requested_view_ids: tuple[str, ...]) -> tuple[str, ...]:
    resolved: list[str] = []
    seen: set[str] = set()
    for view_id in requested_view_ids:
        if view_id.strip() == "v2":
            # Legacy compatibility alias: keep the public primary family
            # deterministic.  Eight-hour sensitivity views remain explicit
            # selections and are never pulled in implicitly by orchestration.
            for semantic_view_id in (
                "v2_minimal_sensor_window_3h",
                "v2_sensor_row_window_3h",
            ):
                if semantic_view_id not in seen:
                    seen.add(semantic_view_id)
                    resolved.append(semantic_view_id)
            continue
        semantic_view_id = resolve_view_id(view_id)
        if semantic_view_id in seen:
            continue
        seen.add(semantic_view_id)
        resolved.append(semantic_view_id)
    return tuple(resolved)
