from __future__ import annotations

from collections import Counter

from Backend.Benchmark.dataset_views.configs import GLOBAL_FORBIDDEN_MODEL_FIELDS, VIEW_ID_ALIASES
from Backend.Benchmark.dataset_views.contracts import DependencyRegistryEntry, FeatureCatalogEntry, ViewDefinition, ViewSelectionResult
from Backend.Benchmark.dataset_views.selectors.resolver import resolve_explicit_features, resolve_prefix_candidates


def select_view_features(
    view_definition: ViewDefinition,
    canonical_columns: tuple[str, ...],
    catalog_index: dict[str, FeatureCatalogEntry],
    dependency_registry: dict[str, DependencyRegistryEntry],
) -> ViewSelectionResult:
    if view_definition.selection_mode == "explicit":
        selected_features, missing_from_canonical = resolve_explicit_features(
            view_definition.explicit_features,
            canonical_columns,
        )
        missing_from_catalog = [feature for feature in selected_features if feature not in catalog_index]
        excluded_by_blacklist = [feature for feature in selected_features if feature in GLOBAL_FORBIDDEN_MODEL_FIELDS]
        final_features = [feature for feature in selected_features if feature not in set(excluded_by_blacklist)]
        return ViewSelectionResult(
            view_definition=view_definition,
            ordered_features=tuple(final_features),
            missing_from_canonical=tuple(missing_from_canonical),
            missing_from_catalog=tuple(missing_from_catalog),
            excluded_by_blacklist=tuple(excluded_by_blacklist),
        )

    if view_definition.selection_mode != "proxy_reduced_draft":
        raise ValueError(f"Unsupported selection mode '{view_definition.selection_mode}'.")

    candidate_features = resolve_prefix_candidates(view_definition.candidate_prefixes, canonical_columns)
    missing_from_catalog = [feature for feature in candidate_features if feature not in catalog_index]
    global_blacklist = set(GLOBAL_FORBIDDEN_MODEL_FIELDS)
    excluded_by_blacklist = [feature for feature in candidate_features if feature in global_blacklist]

    allowed_features: list[str] = []
    excluded_by_governance: list[str] = []
    excluded_by_registry: list[str] = []
    dependency_type_counts: Counter[str] = Counter()
    unresolved_risks: list[str] = []
    alias = VIEW_ID_ALIASES[view_definition.view_id]

    for feature_name in candidate_features:
        if feature_name in global_blacklist:
            continue
        if feature_name in missing_from_catalog:
            continue
        catalog_entry = catalog_index[feature_name]
        if catalog_entry.split_only or alias in catalog_entry.forbidden_views or view_definition.view_id in catalog_entry.forbidden_views:
            excluded_by_governance.append(feature_name)
            continue
        registry_entry = dependency_registry.get(feature_name)
        if registry_entry is None:
            unresolved_risks.append(f"Dependency registry is missing sensor candidate '{feature_name}'.")
            continue
        if registry_entry.decision != "retain":
            excluded_by_registry.append(feature_name)
            dependency_type_counts[registry_entry.dependency_type] += 1
            continue
        allowed_features.append(feature_name)

    return ViewSelectionResult(
        view_definition=view_definition,
        ordered_features=tuple(allowed_features),
        missing_from_catalog=tuple(missing_from_catalog),
        excluded_by_blacklist=tuple(excluded_by_blacklist),
        excluded_by_governance=tuple(excluded_by_governance),
        excluded_by_registry=tuple(excluded_by_registry),
        unresolved_risks=tuple(unresolved_risks),
        dependency_type_counts=dict(sorted(dependency_type_counts.items())),
    )
