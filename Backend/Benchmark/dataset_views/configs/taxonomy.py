from __future__ import annotations

from Backend.Benchmark.dataset_views.contracts import TaxonomyEntry


TAXONOMY_VERSION = "2026-07-27.current-public-scope-v0-v1-v2-3h"

_REGISTRY: tuple[TaxonomyEntry, ...] = (
    TaxonomyEntry(
        semantic_view_id="v0_minimal_sensor",
        numeric_alias="v0",
        status="ACTIVE_VALIDATED",
        batch="Batch 1",
        grain="row",
        selection_kind="explicit_measurements",
        public_selectable=True,
        notes="Approved full snapshot measurement view with nine sensor features. The legacy semantic id is retained for continuity.",
    ),
    TaxonomyEntry(
        semantic_view_id="v1_sensor_row",
        numeric_alias="v1",
        status="ACTIVE_VALIDATED",
        batch="Batch 1",
        grain="row",
        selection_kind="explicit_measurements",
        public_selectable=True,
        notes="Approved reduced snapshot measurement view with air/soil temperature, soil moisture, and EC only. The legacy semantic id is retained for continuity.",
    ),
    TaxonomyEntry(
        semantic_view_id="v2_minimal_sensor_window_3h",
        numeric_alias="v2m3",
        status="ACTIVE_VALIDATED",
        batch="Batch 1",
        grain="window",
        selection_kind="engineered_window",
        public_selectable=True,
        notes="Reduced five-feature snapshot with only the 3h observed-only continuity-aware temporal block.",
    ),
    TaxonomyEntry(
        semantic_view_id="v2_minimal_sensor_window_8h",
        numeric_alias="v2m8",
        status="ACTIVE_VALIDATED",
        batch="Batch 1",
        grain="window",
        selection_kind="engineered_window",
        public_selectable=True,
        notes="Reduced five-feature snapshot with only the 8h observed-only continuity-aware temporal block.",
    ),
    TaxonomyEntry(
        semantic_view_id="v2_sensor_row_window_3h",
        numeric_alias="v2r3",
        status="ACTIVE_VALIDATED",
        batch="Batch 1",
        grain="window",
        selection_kind="engineered_window",
        public_selectable=True,
        notes="Full nine-feature snapshot with only the 3h observed-only continuity-aware temporal block.",
    ),
    TaxonomyEntry(
        semantic_view_id="v2_sensor_row_window_8h",
        numeric_alias="v2r8",
        status="ACTIVE_VALIDATED",
        batch="Batch 1",
        grain="window",
        selection_kind="engineered_window",
        public_selectable=True,
        notes="Full nine-feature snapshot with only the 8h observed-only continuity-aware temporal block.",
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
        semantic_view_id="v3_direct",
        numeric_alias="v3d",
        status="ACTIVE_OPERATIONAL_LINEAGE",
        batch="Batch 2",
        grain="row",
        selection_kind="operational_lineage_direct",
        public_selectable=True,
        notes="Operational-lineage direct-rule evidence view.",
    ),
    TaxonomyEntry(
        semantic_view_id="v3_derived",
        numeric_alias="v3a",
        status="ACTIVE_OPERATIONAL_LINEAGE",
        batch="Batch 2",
        grain="row",
        selection_kind="operational_lineage_derived",
        public_selectable=True,
        notes="Operational-lineage derived-rule descendants view.",
    ),
    TaxonomyEntry(
        semantic_view_id="v3_independent",
        numeric_alias="v3i",
        status="ACTIVE_OPERATIONAL_LINEAGE",
        batch="Batch 2",
        grain="row",
        selection_kind="operational_lineage_independent",
        public_selectable=True,
        notes="Operational-lineage independent-process evidence view.",
    ),
    TaxonomyEntry(
        semantic_view_id="v3_pre_onset",
        numeric_alias="v3p",
        status="ACTIVE_OPERATIONAL_LINEAGE",
        batch="Batch 2",
        grain="row",
        selection_kind="operational_lineage_pre_onset",
        public_selectable=True,
        notes="Operational-lineage pre-onset target view.",
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
    TaxonomyEntry(
        semantic_view_id="v5_proxy_reduced",
        numeric_alias="v5",
        status="RESERVED_BLOCKED_PREREQUISITE",
        batch="Batch 4",
        grain="row",
        selection_kind="blocked_proxy_reduction",
        public_selectable=True,
        notes="Reserved for validated proxy-reduced row features after dependency registry completion.",
    ),
    TaxonomyEntry(
        semantic_view_id="v6_sequence_8h",
        numeric_alias="v6",
        status="ACTIVE_ENVIRONMENTAL_SEQUENCE",
        batch="Batch 4",
        grain="sequence",
        selection_kind="environmental_sequence_8h",
        public_selectable=True,
        notes="Environmental V6 sequence-labeling dataset using fixed independent 8-hour day chunks.",
    ),
    TaxonomyEntry(
        semantic_view_id="v5_proxy_reduced_draft",
        numeric_alias="draft",
        status="INVALID_INDEPENDENT_VIEW",
        batch="Draft",
        grain="row",
        selection_kind="proxy_reduced_draft",
        public_selectable=False,
        notes="Internal draft only; currently duplicates v0 and must not be treated as an independent benchmark view.",
    ),
)

LEGACY_DRIFTED_NAMES: dict[str, str] = {
    "v1_full_sensor": "Legacy drifted view id 'v1_full_sensor' is no longer supported. Use 'v1_sensor_row'.",
    "v3_metadata_only": (
        "Legacy reserved id 'v3_metadata_only' is superseded by the V3 operational-lineage family. "
        "Use 'v3_direct', 'v3_derived', 'v3_independent', or 'v3_pre_onset'."
    ),
    "v6_proxy_reduced": (
        "Legacy drifted view id 'v6_proxy_reduced' is no longer supported. "
        "No current public replacement exists in the active benchmark-primary scope."
    ),
    "v6_event_level": (
        "Legacy drifted view id 'v6_event_level' is no longer supported. "
        "Use 'v6_sequence_8h' or the numeric alias 'v6'."
    ),
    "v6a_window_45m": (
        "Legacy drifted view id 'v6a_window_45m' is no longer supported. "
        "V6 is now a single 8-hour sequence dataset. Use 'v6_sequence_8h' or 'v6'."
    ),
    "v6a_window_90m": (
        "Legacy drifted view id 'v6a_window_90m' is no longer supported. "
        "V6 is now a single 8-hour sequence dataset. Use 'v6_sequence_8h' or 'v6'."
    ),
    "v6a_window_180m": (
        "Legacy drifted view id 'v6a_window_180m' is no longer supported. "
        "V6 is now a single 8-hour sequence dataset. Use 'v6_sequence_8h' or 'v6'."
    ),
    "v6b_continuous_sequence": (
        "Legacy drifted view id 'v6b_continuous_sequence' is no longer supported. "
        "V6 is now a single 8-hour sequence dataset. Use 'v6_sequence_8h' or 'v6'."
    ),
    "v6c_decoded_episode_registry": (
        "Legacy drifted view id 'v6c_decoded_episode_registry' is no longer supported. "
        "V6 is now a single 8-hour sequence dataset. Use 'v6_sequence_8h' or 'v6'."
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
            for semantic_view_id in (
                "v2_minimal_sensor_window_3h",
                "v2_sensor_row_window_3h",
            ):
                if semantic_view_id not in seen:
                    seen.add(semantic_view_id)
                    resolved.append(semantic_view_id)
            continue
        if view_id.strip() == "v3":
            for semantic_view_id in ("v3_direct", "v3_derived", "v3_independent", "v3_pre_onset"):
                if semantic_view_id not in seen:
                    seen.add(semantic_view_id)
                    resolved.append(semantic_view_id)
            continue
        if view_id.strip() == "v6":
            semantic_view_id = "v6_sequence_8h"
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
