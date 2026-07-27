from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from Backend.Benchmark.common.digests import feature_contract_digest, stable_digest
from Backend.Benchmark.dataset_views.configs import (
    ABALATION_SUBSETS,
    GLOBAL_FORBIDDEN_MODEL_FIELDS,
    SHARED_METADATA_COLUMNS,
    get_view_definition,
)
from Backend.Benchmark.dataset_views.contracts import DependencyRegistryEntry, FeatureCatalogEntry
from Backend.Benchmark.dataset_views.validators import file_sha256
from Backend.Benchmark.dataset_views.writers import write_json_file, write_parquet_file, write_csv_file


OBSERVATION_METADATA_COLUMNS: tuple[str, ...] = (
    "record.sample_time_reconstructed",
    "record.sample_time_local",
    "record.upload_time_local",
    "record.timestamp_mismatch_sec",
    "record.upload_delay_sec",
    "record.gap_flag",
    "record.missing_slot_count",
    "record.segment_expected_interval_sec",
    "record.delta_prev_sec",
)

RULE_METADATA_COLUMNS: tuple[str, ...] = (
    "record.segment_boundary_before",
    "record.excluded_reason",
)


def emit_tranche0_lineage_artifacts(
    *,
    output_dir: Path,
    shared_dir: Path,
    canonical_columns: tuple[str, ...],
    row_index_df: pd.DataFrame,
    catalog_index: dict[str, FeatureCatalogEntry],
    dependency_registry: dict[str, DependencyRegistryEntry],
    parquet_engine: str,
) -> None:
    role_registry = build_feature_role_registry(canonical_columns, catalog_index, dependency_registry)
    closure = build_feature_dependency_closure(canonical_columns, dependency_registry)
    ablation_registry = pd.DataFrame(ABALATION_SUBSETS).convert_dtypes()

    write_csv_file(role_registry, shared_dir / "feature_role_registry.csv")
    write_parquet_file(closure, shared_dir / "feature_dependency_closure.parquet", engine=parquet_engine)
    write_csv_file(ablation_registry, shared_dir / "ablation_view_registry.csv")

    subset_dir = shared_dir / "ablation_subsets"
    subset_dir.mkdir(parents=True, exist_ok=True)
    view_manifests = _load_view_manifests(output_dir / "views")
    for view_id, manifest in view_manifests.items():
        lineage_payload = build_view_feature_lineage_payload(
            view_id=view_id,
            manifest=manifest,
            closure_df=closure,
            role_registry=role_registry,
        )
        write_json_file(output_dir / "views" / view_id / "feature_lineage.json", lineage_payload)

    for subset in ABALATION_SUBSETS:
        payload = build_ablation_subset_payload(
            subset=subset,
            view_manifests=view_manifests,
            closure_df=closure,
            row_index_df=row_index_df,
        )
        write_json_file(subset_dir / f"{subset['subset_id']}.json", payload)


def build_feature_role_registry(
    canonical_columns: tuple[str, ...],
    catalog_index: dict[str, FeatureCatalogEntry],
    dependency_registry: dict[str, DependencyRegistryEntry],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    all_columns = sorted({*canonical_columns, *catalog_index.keys(), *dependency_registry.keys()})
    for feature_name in all_columns:
        catalog_entry = catalog_index.get(feature_name)
        dependency_entry = dependency_registry.get(feature_name)
        rows.append(
            {
                "feature_name": feature_name,
                "physical_meaning": feature_name,
                "measurement_source": _measurement_source(feature_name),
                "derived_from": _direct_parent_string(dependency_entry),
                "label_rule_dependency": _label_rule_relation(dependency_entry, catalog_entry),
                "available_at_prediction_time": feature_name not in GLOBAL_FORBIDDEN_MODEL_FIELDS,
                "proxy_status": dependency_entry.dependency_type if dependency_entry is not None else "UNREGISTERED",
            }
        )
    return pd.DataFrame(rows).convert_dtypes()


def build_feature_dependency_closure(
    canonical_columns: tuple[str, ...],
    dependency_registry: dict[str, DependencyRegistryEntry],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    all_columns = sorted({*canonical_columns, *dependency_registry.keys()})
    for feature_name in all_columns:
        entry = dependency_registry.get(feature_name)
        direct_parents = _direct_parents(entry)
        ancestors = _resolve_ancestors(feature_name, dependency_registry, set())
        root_sources = _resolve_root_sources(feature_name, dependency_registry, set())
        rows.append(
            {
                "feature": feature_name,
                "direct_parent": json.dumps(direct_parents, ensure_ascii=True, separators=(",", ":")),
                "root_measurement_source": json.dumps(sorted(root_sources), ensure_ascii=True, separators=(",", ":")),
                "transitive_ancestors": json.dumps(sorted(ancestors), ensure_ascii=True, separators=(",", ":")),
                "label_rule_relation": _label_rule_relation(entry, None),
            }
        )
    return pd.DataFrame(rows).convert_dtypes()


def build_view_feature_lineage_payload(
    *,
    view_id: str,
    manifest: dict[str, object],
    closure_df: pd.DataFrame,
    role_registry: pd.DataFrame,
) -> dict[str, object]:
    ordered_feature_list = [str(column) for column in manifest.get("ordered_feature_list", [])]
    closure_lookup = closure_df.set_index("feature").to_dict(orient="index")
    role_lookup = role_registry.set_index("feature_name").to_dict(orient="index")
    feature_rows: list[dict[str, object]] = []
    for feature_name in ordered_feature_list:
        closure_row = closure_lookup.get(feature_name, {})
        role_row = role_lookup.get(feature_name, {})
        feature_rows.append(
            {
                "feature": feature_name,
                "direct_parent": json.loads(str(closure_row.get("direct_parent", "[]"))),
                "root_measurement_source": json.loads(str(closure_row.get("root_measurement_source", "[]"))),
                "transitive_ancestors": json.loads(str(closure_row.get("transitive_ancestors", "[]"))),
                "label_rule_relation": role_row.get("label_rule_dependency", "UNREGISTERED"),
                "proxy_status": role_row.get("proxy_status", "UNREGISTERED"),
            }
        )
    return {
        "view_id": view_id,
        "feature_count": len(feature_rows),
        "features": feature_rows,
        "payload_hash": stable_digest(feature_rows),
    }


def build_ablation_subset_payload(
    *,
    subset: dict[str, object],
    view_manifests: dict[str, dict[str, object]],
    closure_df: pd.DataFrame,
    row_index_df: pd.DataFrame,
) -> dict[str, object]:
    base_matrix_id = str(subset["base_matrix_id"])
    base_columns, availability_status = _resolve_base_columns(
        base_matrix_id=base_matrix_id,
        view_manifests=view_manifests,
    )
    resolved_columns = _resolve_subset_columns(subset=subset, base_columns=base_columns)
    _assert_forbidden_root_sources_removed(
        subset=subset,
        resolved_columns=resolved_columns,
        closure_df=closure_df,
    )
    feature_version = base_matrix_id if base_matrix_id != "shared_metadata" else "shared_metadata.v1"
    return {
        **subset,
        "availability_status": availability_status,
        "resolved_feature_columns": resolved_columns,
        "resolved_feature_count": len(resolved_columns),
        "population_digest": feature_contract_digest(
            sample_ids=row_index_df["record.id"].astype("string").tolist(),
            ordered_feature_names=["sample_id"],
            feature_view_version="population",
        ),
        "feature_contract_digest": feature_contract_digest(
            sample_ids=row_index_df["record.id"].astype("string").tolist(),
            ordered_feature_names=resolved_columns,
            feature_view_version=feature_version,
        ),
    }


def _resolve_base_columns(
    *,
    base_matrix_id: str,
    view_manifests: dict[str, dict[str, object]],
) -> tuple[list[str], str]:
    if base_matrix_id == "shared_metadata":
        return [column for column in SHARED_METADATA_COLUMNS if column not in {"record.id", "record.node_id"}], "materialized"
    manifest = view_manifests.get(base_matrix_id)
    if manifest is not None:
        return [str(column) for column in manifest.get("ordered_feature_list", [])], "materialized"
    view_definition = get_view_definition(base_matrix_id)
    if view_definition.selection_mode == "explicit":
        return list(view_definition.explicit_features), "inferred_from_contract"
    return [], "not_materialized_in_this_run"


def _load_view_manifests(views_root: Path) -> dict[str, dict[str, object]]:
    manifests: dict[str, dict[str, object]] = {}
    for manifest_path in views_root.glob("*/manifest.json"):
        with manifest_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        manifests[str(payload["view_id"])] = payload
    return manifests


def _measurement_source(feature_name: str) -> str:
    if feature_name.startswith("sht."):
        return "sht"
    if feature_name.startswith("npk."):
        return "npk"
    if feature_name.startswith("record."):
        return "record"
    if feature_name.startswith("derived."):
        return "derived"
    return "unknown"


def _direct_parent_string(entry: DependencyRegistryEntry | None) -> str:
    return "|".join(_direct_parents(entry))


def _direct_parents(entry: DependencyRegistryEntry | None) -> list[str]:
    if entry is None:
        return []
    return sorted(
        {
            *(str(value) for value in entry.direct_source_of),
            *(str(value) for value in entry.deterministic_derivative_of),
            *(str(value) for value in entry.correlated_surrogate_of),
        }
    )


def _resolve_ancestors(
    feature_name: str,
    dependency_registry: dict[str, DependencyRegistryEntry],
    seen: set[str],
) -> set[str]:
    if feature_name in seen:
        return set()
    seen = set(seen)
    seen.add(feature_name)
    entry = dependency_registry.get(feature_name)
    parents = _direct_parents(entry)
    ancestors: set[str] = set(parents)
    for parent in parents:
        ancestors.update(_resolve_ancestors(parent, dependency_registry, seen))
    return ancestors


def _resolve_root_sources(
    feature_name: str,
    dependency_registry: dict[str, DependencyRegistryEntry],
    seen: set[str],
) -> set[str]:
    entry = dependency_registry.get(feature_name)
    parents = _direct_parents(entry)
    if not parents:
        return {feature_name}
    roots: set[str] = set()
    for parent in parents:
        if parent in seen:
            continue
        roots.update(_resolve_root_sources(parent, dependency_registry, {*seen, feature_name}))
    return roots or {feature_name}


def _label_rule_relation(
    dependency_entry: DependencyRegistryEntry | None,
    catalog_entry: FeatureCatalogEntry | None,
) -> str:
    if catalog_entry is not None and catalog_entry.used_by_label_rule:
        return "DIRECT"
    if dependency_entry is None:
        return "UNREGISTERED"
    if dependency_entry.dependency_type == "DIRECT_RULE_SOURCE":
        return "DIRECT"
    if dependency_entry.dependency_type in {"DERIVED_RULE_PROXY", "CORRELATED_SURROGATE"}:
        return "INDIRECT"
    return "NONE"


def _resolve_subset_columns(*, subset: dict[str, object], base_columns: list[str]) -> list[str]:
    subset_id = str(subset["subset_id"])
    if subset_id == "v0_core":
        return [column for column in base_columns if column in {"sht.temp_c", "sht.humidity_pct", "npk.soil_temp_c", "npk.soil_moisture_pct", "npk.ec"}]
    if subset_id == "v0_plus_ph":
        return [column for column in base_columns if column in {"sht.temp_c", "sht.humidity_pct", "npk.soil_temp_c", "npk.soil_moisture_pct", "npk.ec", "npk.ph"}]
    if subset_id in {"v0_plus_npk", "v1_full"}:
        return list(base_columns)
    if subset_id == "v1_without_ph":
        return [column for column in base_columns if column != "npk.ph"]
    if subset_id == "v1_without_npk":
        return [column for column in base_columns if not column.startswith("npk.")]
    if subset_id == "v0_without_direct_row_source":
        return [column for column in base_columns if column != "npk.soil_moisture_pct"]
    if subset_id == "v0_without_direct_source_family":
        return [column for column in base_columns if not column.startswith("npk.soil_moisture")]
    if subset_id == "metadata_observation_only":
        return [column for column in SHARED_METADATA_COLUMNS if column in OBSERVATION_METADATA_COLUMNS]
    if subset_id == "metadata_rule_source_only":
        return [column for column in SHARED_METADATA_COLUMNS if column in RULE_METADATA_COLUMNS]
    if subset_id == "metadata_all":
        return [column for column in SHARED_METADATA_COLUMNS if column not in {"record.id", "record.node_id"}]
    return list(base_columns)


def _assert_forbidden_root_sources_removed(
    *,
    subset: dict[str, object],
    resolved_columns: list[str],
    closure_df: pd.DataFrame,
) -> None:
    forbidden_root_sources = {str(value) for value in subset.get("forbidden_root_sources", [])}
    if not forbidden_root_sources:
        return
    closure_lookup = closure_df.set_index("feature").to_dict(orient="index")
    leaked: list[str] = []
    for feature_name in resolved_columns:
        closure_row = closure_lookup.get(feature_name)
        if closure_row is None:
            continue
        root_sources = set(json.loads(str(closure_row["root_measurement_source"])))
        ancestors = set(json.loads(str(closure_row["transitive_ancestors"])))
        if root_sources.intersection(forbidden_root_sources) or ancestors.intersection(forbidden_root_sources):
            leaked.append(feature_name)
    if leaked:
        raise ValueError(
            f"Subset {subset['subset_id']} still contains forbidden root-source descendants: {sorted(leaked)}"
        )
