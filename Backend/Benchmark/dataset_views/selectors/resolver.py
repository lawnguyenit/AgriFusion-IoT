from __future__ import annotations

from collections.abc import Iterable


def resolve_explicit_features(configured_features: Iterable[str], canonical_columns: Iterable[str]) -> tuple[list[str], list[str]]:
    canonical_set = set(canonical_columns)
    ordered: list[str] = []
    missing: list[str] = []
    for feature_name in configured_features:
        if feature_name in canonical_set:
            ordered.append(feature_name)
        else:
            missing.append(feature_name)
    return ordered, missing


def resolve_prefix_candidates(candidate_prefixes: Iterable[str], canonical_columns: Iterable[str]) -> list[str]:
    prefixes = tuple(candidate_prefixes)
    return [column for column in canonical_columns if column.startswith(prefixes)]
