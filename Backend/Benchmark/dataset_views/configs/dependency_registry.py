from __future__ import annotations

import json
from pathlib import Path

from Backend.Benchmark.dataset_views.contracts import DependencyRegistryEntry


def bundled_dependency_registry_path() -> Path:
    return Path(__file__).with_name("dependency_registry.json")


def load_dependency_registry() -> dict[str, DependencyRegistryEntry]:
    payload = json.loads(bundled_dependency_registry_path().read_text(encoding="utf-8"))
    registry: dict[str, DependencyRegistryEntry] = {}
    for row in payload["entries"]:
        registry[row["canonical_name"]] = DependencyRegistryEntry(
            canonical_name=row["canonical_name"],
            dependency_type=row["dependency_type"],
            target_label_or_rule=row.get("target_label_or_rule", ""),
            direct_source_of=tuple(row.get("direct_source_of", [])),
            deterministic_derivative_of=tuple(row.get("deterministic_derivative_of", [])),
            correlated_surrogate_of=tuple(row.get("correlated_surrogate_of", [])),
            evidence=row.get("evidence", ""),
            decision=row.get("decision", ""),
            version=row.get("version", payload.get("version", "")),
        )
    return registry
