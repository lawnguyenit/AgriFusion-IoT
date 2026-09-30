from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from .contracts import ExternalLabelConfig, ExternalLabelResult
from .engine import build_candidate_labels
from .persistence import make_run_id, sha256_file, write_label_artifacts
from .profiles import ExternalLabelProfile, TargetSpec, resolve_profile


def run_external_label_candidates(config: ExternalLabelConfig) -> ExternalLabelResult:
    canonical_path, intake_manifest_path, intake_manifest, raw_manifest_path, profile, source = _load_verified_source(config)
    labels, registry, cadence, support, calibration = build_candidate_labels(source, profile, config)
    run_id = make_run_id(profile.dataset_id)
    output_dir = (config.output_root / profile.dataset_id / run_id).resolve()
    manifest = _build_run_manifest(
        profile=profile,
        intake_manifest=intake_manifest,
        intake_manifest_path=intake_manifest_path,
        raw_manifest_path=raw_manifest_path,
        canonical_path=canonical_path,
        labels=labels,
        registry=registry,
        calibration=calibration,
        run_id=run_id,
    )
    label_path, registry_path, support_path = write_label_artifacts(
        output_dir=output_dir,
        labels=labels,
        registry=registry,
        cadence_registry=cadence,
        support_audit=support,
        manifest=manifest,
    )
    return ExternalLabelResult(
        dataset_id=profile.dataset_id,
        run_id=run_id,
        output_dir=output_dir,
        candidate_labels_path=label_path,
        registry_path=registry_path,
        support_audit_path=support_path,
        row_count=len(labels),
        candidate_count=len(registry),
    )


def _load_verified_source(
    config: ExternalLabelConfig,
) -> tuple[Path, Path, dict[str, object], Path, ExternalLabelProfile, pd.DataFrame]:
    canonical_path = config.canonical_path.resolve()
    manifest_path = config.intake_manifest_path.resolve()
    if canonical_path.parent != manifest_path.parent:
        raise ValueError("Canonical artifact and intake manifest must come from the same intake run directory.")
    intake_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    profile = resolve_profile(str(intake_manifest["dataset_id"]))
    catalog_path = canonical_path.parent / "artifact_catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    _verify_catalog_entry(catalog, manifest_path.name, manifest_path, "Intake manifest")
    _verify_catalog_entry(catalog, canonical_path.name, canonical_path, "Canonical artifact")
    raw_manifest_path = Path(str(intake_manifest["raw_manifest_path"]))
    if not raw_manifest_path.is_file() or sha256_file(raw_manifest_path) != intake_manifest.get("raw_manifest_sha256"):
        raise ValueError("Intake raw release manifest is missing or its checksum is invalid.")
    source = _read_allowlisted_columns(canonical_path, profile)
    return canonical_path, manifest_path, intake_manifest, raw_manifest_path, profile, source


def _verify_catalog_entry(
    catalog: list[dict[str, object]],
    name: str,
    path: Path,
    artifact_description: str,
) -> None:
    rows = [row for row in catalog if row.get("path") == name]
    if len(rows) != 1 or str(rows[0].get("sha256")) != sha256_file(path):
        raise ValueError(f"{artifact_description} checksum does not match its intake artifact catalog.")


def _read_allowlisted_columns(path: Path, profile: ExternalLabelProfile) -> pd.DataFrame:
    columns = ["sample_id", profile.timestamp_column, *profile.group_columns]
    columns.extend(target.measurement_column for target in profile.targets)
    return pd.read_parquet(path, columns=list(dict.fromkeys(columns)))


def _build_run_manifest(
    *,
    profile: ExternalLabelProfile,
    intake_manifest: dict[str, object],
    intake_manifest_path: Path,
    raw_manifest_path: Path,
    canonical_path: Path,
    labels: pd.DataFrame,
    registry: pd.DataFrame,
    calibration: dict[str, object],
    run_id: str,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "pipeline": "external_label_candidates",
        "policy_id": calibration["policy_id"],
        "run_id": run_id,
        "dataset_id": profile.dataset_id,
        "created_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "dataset_metadata": intake_manifest.get("dataset_metadata", {}),
        "intake_run_id": intake_manifest["run_id"],
        "intake_manifest_path": str(intake_manifest_path),
        "intake_manifest_sha256": sha256_file(intake_manifest_path),
        "canonical_path": str(canonical_path),
        "canonical_sha256": sha256_file(canonical_path),
        "raw_manifest_path": str(raw_manifest_path.resolve()),
        "raw_manifest_sha256": str(intake_manifest["raw_manifest_sha256"]),
        "target_specs": [_target_manifest(target) for target in profile.targets],
        "criterion_target_sources": [
            target.measurement_column
            for target in profile.targets
            if target.evidence_kind == "CERTIFIED_REFERENCE_CRITERION"
        ],
        "criterion_fields_used_as_model_features": False,
        "calibration": calibration,
        "primary_candidate_selected": False,
        "label_release_status": "CANDIDATE_AUDIT_REVIEW_REQUIRED",
        "row_count": int(len(labels)),
        "candidate_count": int(len(registry)),
        "ordered_sample_id_sha256": _ordered_string_hash(labels["sample_id"].astype("string").tolist()),
    }


def _target_manifest(target: TargetSpec) -> dict[str, str]:
    return {
        "target_id": str(target.target_id),
        "target_source_column": str(target.measurement_column),
        "evidence_kind": str(target.evidence_kind),
        "input_feature_candidates": "|".join(target.input_feature_candidates),
        "tail_direction": str(target.tail_direction),
        "positive_label": str(target.positive_label),
    }


def _ordered_string_hash(values: list[str]) -> str:
    digest = hashlib.sha256()
    for value in values:
        payload = value.encode("utf-8")
        digest.update(len(payload).to_bytes(8, byteorder="big"))
        digest.update(payload)
    return digest.hexdigest()
