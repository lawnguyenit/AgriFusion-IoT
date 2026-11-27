from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


MaterializationMode = Literal["feature-only", "benchmark-ready"]
ViewSelectionMode = Literal[
    "explicit",
    "window_engineered",
    "reserved_not_implemented",
]


@dataclass(frozen=True)
class FeatureCatalogEntry:
    canonical_name: str
    feature_role: str
    used_by_label_rule: bool
    rule_proxy_level: str
    split_only: bool
    allowed_views: tuple[str, ...] = ()
    forbidden_views: tuple[str, ...] = ()
    eligible_for_model: bool | None = None


@dataclass(frozen=True)
class DependencyRegistryEntry:
    canonical_name: str
    dependency_type: str
    target_label_or_rule: str
    direct_source_of: tuple[str, ...] = ()
    deterministic_derivative_of: tuple[str, ...] = ()
    correlated_surrogate_of: tuple[str, ...] = ()
    evidence: str = ""
    decision: str = ""
    version: str = ""


@dataclass(frozen=True)
class CycleWindowHorizon:
    name: str
    cycles: int
    min_valid_observations: int
    min_slope_observations: int = 0


@dataclass(frozen=True)
class ViewDefinition:
    view_id: str
    description: str
    selection_mode: ViewSelectionMode
    explicit_features: tuple[str, ...] = ()
    candidate_prefixes: tuple[str, ...] = ()
    window_horizon_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class TaxonomyEntry:
    semantic_view_id: str
    numeric_alias: str
    status: str
    batch: str
    grain: str
    selection_kind: str
    public_selectable: bool
    notes: str = ""


@dataclass(frozen=True)
class LabelConfig:
    artifact_path: Path
    key_column: str = "record.id"
    required_columns: tuple[str, ...] = ()


@dataclass(frozen=True)
class MaterializationConfig:
    canonical_history_path: Path
    feature_catalog_path: Path
    output_root: Path
    mode: MaterializationMode
    selected_views: tuple[str, ...]
    manifest_path: Path | None = None
    label_config: LabelConfig | None = None


@dataclass(frozen=True)
class ViewSelectionResult:
    view_definition: ViewDefinition
    ordered_features: tuple[str, ...]
    missing_from_canonical: tuple[str, ...] = ()
    missing_from_catalog: tuple[str, ...] = ()
    excluded_by_blacklist: tuple[str, ...] = ()
    excluded_by_governance: tuple[str, ...] = ()
    excluded_by_registry: tuple[str, ...] = ()
    unresolved_risks: tuple[str, ...] = ()
    dependency_type_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class MaterializationResult:
    run_id: str
    output_dir: Path
    label_status: str
    selected_views: tuple[str, ...]
    row_count: int
    materialized_nonpublic_drafts: tuple[str, ...] = ()
