from __future__ import annotations

from Backend.Benchmark.dataset_views.configs import GLOBAL_FORBIDDEN_MODEL_FIELDS
from Backend.Benchmark.dataset_views.contracts import DependencyRegistryEntry, FeatureCatalogEntry, ViewDefinition, ViewSelectionResult
from Backend.Benchmark.dataset_views.selectors.resolver import resolve_explicit_features


def select_view_features(
    view_definition: ViewDefinition,
    canonical_columns: tuple[str, ...],
    catalog_index: dict[str, FeatureCatalogEntry],
    dependency_registry: dict[str, DependencyRegistryEntry],
) -> ViewSelectionResult:
    _ = dependency_registry
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

    raise ValueError(f"Unsupported selection mode '{view_definition.selection_mode}'.")
