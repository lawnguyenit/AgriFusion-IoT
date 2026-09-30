from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .contracts import ExternalFeatureConfig, ExternalFeatureResult
from .persistence import make_run_id, sha256_file, write_feature_artifacts
from .profiles import resolve_profile
from .windowing import build_external_feature_matrix


def run_external_feature_processing(config: ExternalFeatureConfig) -> ExternalFeatureResult:
    intake_manifest = json.loads(config.intake_manifest_path.read_text(encoding="utf-8"))
    dataset_id = str(intake_manifest["dataset_id"])
    canonical_path = config.canonical_path.resolve()
    if canonical_path.parent != config.intake_manifest_path.resolve().parent:
        raise ValueError("Canonical artifact and intake manifest must come from the same intake run directory.")
    catalog_path = canonical_path.parent / "artifact_catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    manifest_record = next((row for row in catalog if row.get("path") == config.intake_manifest_path.name), None)
    if manifest_record is None or sha256_file(config.intake_manifest_path) != manifest_record.get("sha256"):
        raise ValueError("Intake manifest checksum does not match its artifact catalog.")
    raw_manifest_path = Path(str(intake_manifest["raw_manifest_path"]))
    if not raw_manifest_path.is_file() or sha256_file(raw_manifest_path) != intake_manifest.get("raw_manifest_sha256"):
        raise ValueError("Intake raw release manifest is missing or its checksum is invalid.")
    canonical_record = next((row for row in catalog if row.get("path") == canonical_path.name), None)
    if canonical_record is None or sha256_file(canonical_path) != canonical_record.get("sha256"):
        raise ValueError("Canonical source checksum does not match its intake artifact catalog.")
    canonical = pd.read_parquet(canonical_path)
    profile = resolve_profile(dataset_id, intake_manifest)
    absent_measurements = [column for column in profile.value_columns if column not in canonical.columns]
    if absent_measurements:
        raise ValueError(f"Canonical dataset is missing allowlisted measurements: {absent_measurements}")
    leaked_criteria = [column for column in profile.value_columns if column.lower().startswith("criterion.")]
    if leaked_criteria:
        raise ValueError(f"Criterion-only fields cannot enter model features: {leaked_criteria}")
    features, groups, quality = build_external_feature_matrix(
        canonical=canonical,
        profile=profile,
        window_hours=config.window_hours,
        min_window_observations=config.min_window_observations,
    )
    run_id = make_run_id(dataset_id)
    output_dir = (config.output_root / dataset_id / run_id).resolve()
    manifest: dict[str, object] = {
        "schema_version": 1,
        "pipeline": "external_features",
        "run_id": run_id,
        "dataset_id": dataset_id,
        "dataset_metadata": intake_manifest.get("dataset_metadata", {}),
        "intake_run_id": intake_manifest["run_id"],
        "intake_manifest_path": str(config.intake_manifest_path.resolve()),
        "intake_manifest_sha256": sha256_file(config.intake_manifest_path),
        "canonical_path": str(canonical_path),
        "canonical_sha256": sha256_file(canonical_path),
        "raw_manifest_path": str(raw_manifest_path.resolve()),
        "raw_manifest_sha256": intake_manifest["raw_manifest_sha256"],
        "timestamp_column": profile.timestamp_column,
        "timestamp_time_basis": intake_manifest.get("adapter_audit", {}).get("timestamp_time_basis", "UTC"),
        "group_columns": list(profile.group_columns),
        "value_columns": list(profile.value_columns),
        "criterion_and_evidence_columns_excluded_from_features": _excluded_columns(intake_manifest),
        "window_hours": list(config.window_hours),
        "min_window_observations": config.min_window_observations,
        "causal_window_policy": "trailing closed-both; current and prior rows only; grouped by source entity",
        "feature_selection_policy": "source adapter measurement allowlist only",
        "model_fit_performed": False,
    }
    matrix_path, registry_path = write_feature_artifacts(
        output_dir=output_dir,
        feature_frame=features,
        group_columns=groups,
        quality=quality,
        manifest=manifest,
    )
    return ExternalFeatureResult(
        dataset_id=dataset_id,
        run_id=run_id,
        output_dir=output_dir,
        feature_matrix_path=matrix_path,
        registry_path=registry_path,
        row_count=len(features),
        feature_count=sum(len(columns) for columns in groups.values()),
    )


def _excluded_columns(manifest: dict[str, object]) -> list[str]:
    audit = manifest.get("adapter_audit", {})
    dataset_id = manifest.get("dataset_id")
    if dataset_id == "uci_air_quality_360":
        roles = audit.get("column_roles", {})
        return [name for name, role in roles.items() if role == "criterion_only"]
    if dataset_id == "stuard_tomato_irrigation_2023":
        role_groups = audit.get("feature_and_criterion_roles", {})
        return [
            name
            for role, columns in role_groups.items()
            if role != "measurements"
            for name in columns
        ]
    return []
