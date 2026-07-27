from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import pandas as pd

from Backend.Benchmark.weak_labels.shared.helpers import file_sha256


FORBIDDEN_LABEL_COLUMNS = {
    "base_partition",
    "effective_partition",
    "fold_id",
    "deployment_domain",
}

REGISTRY_SPECS: tuple[dict[str, object], ...] = (
    {
        "experiment_id": "v0_point",
        "feature_view_id": "v0_point",
        "feature_source_view_id": "v0_minimal_sensor",
        "label_task_id": "v0_point_train",
        "protocol_view_id": "v0_point_train",
        "sample_unit": "record",
        "feature_join_key": "record.id",
        "label_join_key": "sample_id",
        "label_relative_path": "point/point_labels_train.parquet",
        "scientific_blocker": "",
    },
    {
        "experiment_id": "v1_point",
        "feature_view_id": "v1_point",
        "feature_source_view_id": "v1_sensor_row",
        "label_task_id": "v1_point_train",
        "protocol_view_id": "v1_point_train",
        "sample_unit": "record",
        "feature_join_key": "record.id",
        "label_join_key": "sample_id",
        "label_relative_path": "point/point_labels_train.parquet",
        "scientific_blocker": "",
    },
    {
        "experiment_id": "v2_same_y_mini_3h",
        "feature_view_id": "v2_same_y_mini_3h",
        "feature_source_view_id": "v2_minimal_sensor_window_3h",
        "label_task_id": "v2_same_y_3h",
        "protocol_view_id": "v2_same_y_3h",
        "sample_unit": "record",
        "feature_join_key": "record.id",
        "label_join_key": "sample_id",
        "label_relative_path": "v2/v2_same_y_labels.parquet",
        "scientific_blocker": "",
    },
    {
        "experiment_id": "v2_same_y_full_3h",
        "feature_view_id": "v2_same_y_full_3h",
        "feature_source_view_id": "v2_sensor_row_window_3h",
        "label_task_id": "v2_same_y_3h",
        "protocol_view_id": "v2_same_y_3h",
        "sample_unit": "record",
        "feature_join_key": "record.id",
        "label_join_key": "sample_id",
        "label_relative_path": "v2/v2_same_y_labels.parquet",
        "scientific_blocker": "",
    },
    {
        "experiment_id": "v2_temporal_mini_3h",
        "feature_view_id": "v2_temporal_mini_3h",
        "feature_source_view_id": "v2_minimal_sensor_window_3h",
        "label_task_id": "v2_temporal_3h",
        "protocol_view_id": "v2_temporal_3h",
        "sample_unit": "record",
        "feature_join_key": "record.id",
        "label_join_key": "sample_id",
        "label_relative_path": "v2/v2_temporal_labels_3h.parquet",
        "scientific_blocker": "",
    },
    {
        "experiment_id": "v2_temporal_full_3h",
        "feature_view_id": "v2_temporal_full_3h",
        "feature_source_view_id": "v2_sensor_row_window_3h",
        "label_task_id": "v2_temporal_3h",
        "protocol_view_id": "v2_temporal_3h",
        "sample_unit": "record",
        "feature_join_key": "record.id",
        "label_join_key": "sample_id",
        "label_relative_path": "v2/v2_temporal_labels_3h.parquet",
        "scientific_blocker": "",
    },
    {
        "experiment_id": "v2_same_y_mini_8h",
        "feature_view_id": "v2_same_y_mini_8h",
        "feature_source_view_id": "v2_minimal_sensor_window_8h",
        "label_task_id": "v2_same_y_8h",
        "protocol_view_id": "v2_same_y_8h",
        "sample_unit": "record",
        "feature_join_key": "record.id",
        "label_join_key": "sample_id",
        "label_relative_path": "v2/v2_same_y_labels.parquet",
        "scientific_blocker": "",
    },
    {
        "experiment_id": "v2_same_y_full_8h",
        "feature_view_id": "v2_same_y_full_8h",
        "feature_source_view_id": "v2_sensor_row_window_8h",
        "label_task_id": "v2_same_y_8h",
        "protocol_view_id": "v2_same_y_8h",
        "sample_unit": "record",
        "feature_join_key": "record.id",
        "label_join_key": "sample_id",
        "label_relative_path": "v2/v2_same_y_labels.parquet",
        "scientific_blocker": "",
    },
    {
        "experiment_id": "v2_temporal_mini_8h",
        "feature_view_id": "v2_temporal_mini_8h",
        "feature_source_view_id": "v2_minimal_sensor_window_8h",
        "label_task_id": "v2_temporal_8h",
        "protocol_view_id": "v2_temporal_8h",
        "sample_unit": "record",
        "feature_join_key": "record.id",
        "label_join_key": "sample_id",
        "label_relative_path": "v2/v2_temporal_labels_8h.parquet",
        "scientific_blocker": "",
    },
    {
        "experiment_id": "v2_temporal_full_8h",
        "feature_view_id": "v2_temporal_full_8h",
        "feature_source_view_id": "v2_sensor_row_window_8h",
        "label_task_id": "v2_temporal_8h",
        "protocol_view_id": "v2_temporal_8h",
        "sample_unit": "record",
        "feature_join_key": "record.id",
        "label_join_key": "sample_id",
        "label_relative_path": "v2/v2_temporal_labels_8h.parquet",
        "scientific_blocker": "",
    },
    {
        "experiment_id": "v6_event_unresolved",
        "feature_view_id": "v6_event_unresolved",
        "feature_source_view_id": "UNRESOLVED_V6_EVENT_FEATURE_VIEW",
        "label_task_id": "v6_event",
        "protocol_view_id": "v6_event",
        "sample_unit": "event",
        "feature_join_key": "sample_id",
        "label_join_key": "sample_id",
        "label_relative_path": "v6/v6_event_labels.parquet",
        "scientific_blocker": "normal_selection_audit",
        "feature_artifact_status": "unresolved",
    },
    {
        "experiment_id": "v6_block_unresolved",
        "feature_view_id": "v6_block_unresolved",
        "feature_source_view_id": "UNRESOLVED_V6_BLOCK_FEATURE_VIEW",
        "label_task_id": "v6_b8_block",
        "protocol_view_id": "v6_b8_block",
        "sample_unit": "block",
        "feature_join_key": "sample_id",
        "label_join_key": "sample_id",
        "label_relative_path": "v6/v6_b8_block_labels.parquet",
        "scientific_blocker": "normal_selection_audit",
        "feature_artifact_status": "unresolved",
    },
)

COMPARISON_TO_FEATURE_VIEWS: dict[str, tuple[str, str]] = {
    "v0_vs_v2_mini_3h": ("v0_point", "v2_same_y_mini_3h"),
    "v1_vs_v2_full_3h": ("v1_point", "v2_same_y_full_3h"),
    "v0_vs_v2_mini_8h": ("v0_point", "v2_same_y_mini_8h"),
    "v1_vs_v2_full_8h": ("v1_point", "v2_same_y_full_8h"),
}


@dataclass(frozen=True)
class WeakLabelSources:
    point_labels_train: pd.DataFrame
    point_labels_detailed: pd.DataFrame
    point_evidence_flags: pd.DataFrame
    v2_same_y_labels: pd.DataFrame
    v2_temporal_evidence_3h: pd.DataFrame
    v2_temporal_evidence_8h: pd.DataFrame
    v2_temporal_labels_3h: pd.DataFrame
    v2_temporal_labels_8h: pd.DataFrame
    v6_event_labels: pd.DataFrame
    v6_b8_block_composition: pd.DataFrame
    v6_b8_block_labels: pd.DataFrame
    paths: dict[str, Path]
    hashes: dict[str, str]


@dataclass(frozen=True)
class ResolvedFeatureArtifact:
    feature_source_view_id: str
    feature_artifact_path: Path
    feature_artifact_hash: str
    feature_schema_path: Path
    feature_schema_hash: str
    feature_columns_path: Path
    feature_columns_hash: str
    feature_generator_config_hash: str
    feature_generator_code_commit: str
    source_canonical_hash: str
    materialization_config_hash: str
    row_index_path: Path
    row_index_hash: str
    sample_id_hash: str
    row_count: int
    allowed_feature_columns: tuple[str, ...]
    identifier_columns: tuple[str, ...]
    audit_only_columns: tuple[str, ...]
    forbidden_columns: tuple[str, ...]
    sample_ids: frozenset[str]


def load_weak_label_sources(run_dir: Path) -> WeakLabelSources:
    paths = {
        "point_labels_train": _resolve_artifact(run_dir, "point/point_labels_train.parquet", "point_labels_train.parquet"),
        "point_labels_detailed": _resolve_artifact(run_dir, "point/point_labels_detailed.parquet", "point_labels_detailed.parquet"),
        "point_evidence_flags": _resolve_artifact(run_dir, "point/point_evidence_flags.parquet", "point_evidence_flags.parquet"),
        "v2_same_y_labels": _resolve_artifact(run_dir, "v2/v2_same_y_labels.parquet", "v2_same_y_labels.parquet"),
        "v2_temporal_evidence_3h": _resolve_artifact(run_dir, "v2/v2_temporal_evidence_3h.parquet", "v2_temporal_evidence_3h.parquet"),
        "v2_temporal_evidence_8h": _resolve_artifact(run_dir, "v2/v2_temporal_evidence_8h.parquet", "v2_temporal_evidence_8h.parquet"),
        "v2_temporal_labels_3h": _resolve_artifact(run_dir, "v2/v2_temporal_labels_3h.parquet", "v2_temporal_labels_3h.parquet"),
        "v2_temporal_labels_8h": _resolve_artifact(run_dir, "v2/v2_temporal_labels_8h.parquet", "v2_temporal_labels_8h.parquet"),
        "v6_event_labels": _resolve_artifact(run_dir, "v6/v6_event_labels.parquet", "v6_event_labels.parquet"),
        "v6_b8_block_composition": _resolve_artifact(run_dir, "v6/v6_b8_block_composition.parquet", "v6_b8_block_composition.parquet"),
        "v6_b8_block_labels": _resolve_artifact(run_dir, "v6/v6_b8_block_labels.parquet", "v6_b8_block_labels.parquet"),
    }
    frames = {name: pd.read_parquet(path).convert_dtypes() for name, path in paths.items()}
    for name, frame in frames.items():
        assert_no_forbidden_protocol_columns(frame, artifact_name=name)
    _assert_unique_label_keys(frames)
    hashes = {name: file_sha256(path) for name, path in paths.items()}
    return WeakLabelSources(
        point_labels_train=frames["point_labels_train"],
        point_labels_detailed=frames["point_labels_detailed"],
        point_evidence_flags=frames["point_evidence_flags"],
        v2_same_y_labels=frames["v2_same_y_labels"],
        v2_temporal_evidence_3h=frames["v2_temporal_evidence_3h"],
        v2_temporal_evidence_8h=frames["v2_temporal_evidence_8h"],
        v2_temporal_labels_3h=frames["v2_temporal_labels_3h"],
        v2_temporal_labels_8h=frames["v2_temporal_labels_8h"],
        v6_event_labels=frames["v6_event_labels"],
        v6_b8_block_composition=frames["v6_b8_block_composition"],
        v6_b8_block_labels=frames["v6_b8_block_labels"],
        paths=paths,
        hashes=hashes,
    )


def assert_no_forbidden_protocol_columns(frame: pd.DataFrame, *, artifact_name: str) -> None:
    unexpected = FORBIDDEN_LABEL_COLUMNS.intersection(frame.columns)
    if unexpected:
        raise RuntimeError(f"Label artifact exposes forbidden protocol columns in {artifact_name}: {sorted(unexpected)}")


def load_dataset_view_feature_artifacts(
    dataset_views_run_dir: Path,
    *,
    required_view_ids: tuple[str, ...] | None = None,
) -> dict[str, ResolvedFeatureArtifact]:
    shared_dir = dataset_views_run_dir / "shared"
    source_manifest = _load_json_file(shared_dir / "source_manifest.json")
    row_index_contract = _load_json_file(shared_dir / "row_index_contract.json")
    row_index_path = Path(str(row_index_contract["parquet_path"]))
    row_index_df = pd.read_parquet(row_index_path, columns=["record.id"]).convert_dtypes()
    if row_index_df["record.id"].astype("string").duplicated(keep=False).any():
        duplicates = row_index_df.loc[
            row_index_df["record.id"].astype("string").duplicated(keep=False),
            ["record.id"],
        ]
        raise ValueError(f"dataset_views row_index has duplicate record.id values: {duplicates.to_dict(orient='records')}")
    sample_ids = frozenset(row_index_df["record.id"].astype("string").dropna().tolist())
    source_canonical_hash = str(source_manifest["source"]["canonical_history_hash"])
    materialization_config_hash = str(source_manifest["source"]["materialization_config_hash"])
    views_root = dataset_views_run_dir / "views"
    if required_view_ids is None:
        required_view_ids = tuple(sorted({str(spec["feature_source_view_id"]) for spec in REGISTRY_SPECS if "UNRESOLVED" not in str(spec["feature_source_view_id"])}))

    artifacts: dict[str, ResolvedFeatureArtifact] = {}
    for view_id in required_view_ids:
        view_dir = views_root / view_id
        manifest_path = view_dir / "manifest.json"
        manifest = _load_json_file(manifest_path)
        schema_path = Path(str(manifest.get("feature_schema_path") or (view_dir / "schema.json").resolve()))
        feature_columns_path = Path(str(manifest.get("feature_columns_path") or (view_dir / "feature_columns.json").resolve()))
        x_path = Path(str(manifest.get("feature_artifact_path") or (view_dir / "X.parquet").resolve()))
        feature_columns_payload = _load_json_file(feature_columns_path)
        ordered_feature_list = [str(column) for column in manifest["ordered_feature_list"]]
        allowed_feature_columns = [str(column) for column in feature_columns_payload["allowed_feature_columns"]]
        if ordered_feature_list != allowed_feature_columns:
            raise ValueError(
                f"dataset_views feature columns drift for {view_id}: "
                f"manifest ordered_feature_list does not match feature_columns allowlist."
            )
        if int(manifest["row_count"]) != int(row_index_contract["row_count"]):
            raise ValueError(
                f"dataset_views view {view_id} row_count={manifest['row_count']} "
                f"does not match shared row_index row_count={row_index_contract['row_count']}."
            )
        if str(manifest["row_index_hash"]) != str(row_index_contract["file_hash"]):
            raise ValueError(
                f"dataset_views view {view_id} row_index hash mismatch: "
                f"{manifest['row_index_hash']} != {row_index_contract['file_hash']}."
            )
        if str(manifest["sample_id_hash"]) != str(row_index_contract["record_id_hash"]):
            raise ValueError(
                f"dataset_views view {view_id} sample_id hash mismatch: "
                f"{manifest['sample_id_hash']} != {row_index_contract['record_id_hash']}."
            )
        artifacts[view_id] = ResolvedFeatureArtifact(
            feature_source_view_id=view_id,
            feature_artifact_path=x_path,
            feature_artifact_hash=file_sha256(x_path),
            feature_schema_path=schema_path,
            feature_schema_hash=file_sha256(schema_path),
            feature_columns_path=feature_columns_path,
            feature_columns_hash=file_sha256(feature_columns_path),
            feature_generator_config_hash=str(manifest["feature_generator_config_hash"]),
            feature_generator_code_commit=str(manifest["feature_generator_code_commit"]),
            source_canonical_hash=source_canonical_hash,
            materialization_config_hash=materialization_config_hash,
            row_index_path=row_index_path,
            row_index_hash=str(row_index_contract["file_hash"]),
            sample_id_hash=str(row_index_contract["record_id_hash"]),
            row_count=int(manifest["row_count"]),
            allowed_feature_columns=tuple(allowed_feature_columns),
            identifier_columns=tuple(str(column) for column in feature_columns_payload["identifier_columns"]),
            audit_only_columns=tuple(str(column) for column in feature_columns_payload["audit_only_columns"]),
            forbidden_columns=tuple(str(column) for column in feature_columns_payload["forbidden_columns"]),
            sample_ids=sample_ids,
        )
    return artifacts


def build_task_view_registry(
    *,
    weak_labels_run_dir: Path,
    dataset_views_run_dir: Path,
    split_artifact_path: Path,
    feature_artifacts: dict[str, ResolvedFeatureArtifact],
    feature_view_ids: tuple[str, ...] | None = None,
) -> pd.DataFrame:
    allowed_feature_views = set(feature_view_ids) if feature_view_ids is not None else None
    rows = [
        _registry_row(
            spec=spec,
            weak_labels_run_dir=weak_labels_run_dir,
            dataset_views_run_dir=dataset_views_run_dir,
            split_artifact_path=split_artifact_path,
            resolved_feature=feature_artifacts.get(str(spec["feature_source_view_id"])),
        )
        for spec in REGISTRY_SPECS
        if allowed_feature_views is None or str(spec["feature_view_id"]) in allowed_feature_views
    ]
    return pd.DataFrame(rows).convert_dtypes()


def build_task_training_manifest(
    *,
    registry_df: pd.DataFrame,
    view_assignments: pd.DataFrame,
    label_frames: dict[str, pd.DataFrame],
    label_paths: dict[str, Path],
    label_hashes: dict[str, str],
    protocol_artifact_path: Path,
    protocol_artifact_hash: str,
    feature_artifacts: dict[str, ResolvedFeatureArtifact],
    cohort_manifests: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    validation_rows: list[dict[str, object]] = []
    cohort_lookup = _build_matched_cohort_lookup(cohort_manifests)
    for mapping in registry_df.to_dict(orient="records"):
        label_task_id = str(mapping["label_task_id"])
        protocol_view_id = str(mapping["protocol_view_id"])
        feature_view_id = str(mapping["feature_view_id"])
        feature_source_view_id = str(mapping["feature_source_view_id"])
        feature_artifact_status = str(mapping["feature_artifact_status"])
        label_frame = label_frames[label_task_id].copy()
        protocol_rows = view_assignments.loc[view_assignments["view_id"].astype("string") == protocol_view_id].copy()
        if protocol_rows.empty:
            continue

        resolved_feature = feature_artifacts.get(feature_source_view_id)
        if feature_artifact_status == "resolved" and resolved_feature is None:
            raise ValueError(f"Resolved feature artifact metadata is missing for {feature_source_view_id}.")

        merged = protocol_rows.merge(
            label_frame,
            on="sample_id",
            how="left",
            validate="many_to_one",
            suffixes=("_protocol", "_label"),
        )
        protocol_eligible = merged["effective_partition"].astype("string") != "excluded"
        intrinsic_present = merged["intrinsic_eligibility"].notna()
        intrinsic_eligible = merged["intrinsic_eligibility"].fillna(False).astype(bool)
        label_present = merged["label_status"].notna()
        label_status = merged["label_status"].astype("string")
        train_candidate = protocol_eligible & intrinsic_eligible & (label_status == "LABELED")
        feature_sample_present = (
            merged["sample_id"].astype("string").map(lambda value: value in resolved_feature.sample_ids).astype(bool)
            if resolved_feature is not None
            else pd.Series(False, index=merged.index)
        )
        feature_join_ready = train_candidate & feature_sample_present
        final_trainability = feature_join_ready

        for row in merged.to_dict(orient="records"):
            sample_id = str(row["sample_id"])
            partition = str(row["effective_partition"])
            key = (
                sample_id,
                feature_view_id,
                label_task_id,
                str(row["fold_id"]),
                partition,
            )
            row_feature_present = bool(sample_id in resolved_feature.sample_ids) if resolved_feature is not None else False
            row_protocol_eligible = partition != "excluded"
            row_intrinsic_eligible = bool(row.get("intrinsic_eligibility", False))
            row_label_status = str(row.get("label_status", ""))
            row_train_candidate = row_protocol_eligible and row_intrinsic_eligible and row_label_status == "LABELED"
            row_feature_join_ready = row_train_candidate and row_feature_present
            rows.append(
                {
                    "sample_id": sample_id,
                    "feature_view_id": feature_view_id,
                    "feature_source_view_id": feature_source_view_id,
                    "label_task_id": label_task_id,
                    "protocol_view_id": protocol_view_id,
                    "fold_id": str(row["fold_id"]),
                    "partition": partition,
                    "deployment_domain": str(row["deployment_domain"]),
                    "effective_partition": partition,
                    "label_name": row.get("label_name", pd.NA),
                    "label_status": row.get("label_status", pd.NA),
                    "intrinsic_eligibility": row_intrinsic_eligible,
                    "protocol_eligibility": row_protocol_eligible,
                    "feature_artifact_ready": feature_artifact_status == "resolved",
                    "feature_join_ready": row_feature_join_ready,
                    "final_trainability": row_feature_join_ready,
                    "intrinsic_exclusion_reason": row.get("intrinsic_exclusion_reason", pd.NA),
                    "protocol_exclusion_reason": row.get("exclusion_reason", pd.NA),
                    "matched_cohort_id": cohort_lookup.get(key, pd.NA),
                    "label_artifact_path": str(label_paths[label_task_id]),
                    "label_artifact_hash": label_hashes[label_task_id],
                    "feature_artifact_status": feature_artifact_status,
                    "feature_artifact_path": mapping["feature_artifact_path"],
                    "feature_artifact_hash": mapping["feature_artifact_hash"],
                    "feature_schema_path": mapping["feature_schema_path"],
                    "feature_schema_hash": mapping["feature_schema_hash"],
                    "feature_columns_path": mapping["feature_columns_path"],
                    "feature_columns_hash": mapping["feature_columns_hash"],
                    "feature_generator_config_hash": mapping["feature_generator_config_hash"],
                    "feature_generator_code_commit": mapping["feature_generator_code_commit"],
                    "source_canonical_hash": mapping["source_canonical_hash"],
                    "materialization_config_hash": mapping["materialization_config_hash"],
                    "row_index_path": mapping["row_index_path"],
                    "row_index_hash": mapping["row_index_hash"],
                    "sample_id_hash": mapping["sample_id_hash"],
                    "allowed_feature_columns_json": mapping["allowed_feature_columns_json"],
                    "identifier_columns_json": mapping["identifier_columns_json"],
                    "audit_only_columns_json": mapping["audit_only_columns_json"],
                    "forbidden_columns_json": mapping["forbidden_columns_json"],
                    "scientific_blocker": mapping["scientific_blocker"],
                    "protocol_artifact_path": str(protocol_artifact_path),
                    "protocol_artifact_hash": protocol_artifact_hash,
                }
            )

        expected_protocol_eligible = int(protocol_eligible.sum())
        joined_with_label = int((protocol_eligible & label_present).sum())
        joined_with_intrinsic_state = int((protocol_eligible & intrinsic_present).sum())
        intrinsic_excluded = int((protocol_eligible & intrinsic_present & ~intrinsic_eligible).sum())
        blocked_by_label_state = int((protocol_eligible & intrinsic_eligible & (label_status != "LABELED")).sum())
        feature_blocked = int((train_candidate & ~feature_sample_present).sum())
        final_trainable_count = int(final_trainability.sum())
        missing_label_count = int((protocol_eligible & ~label_present).sum())
        missing_intrinsic_reason = int(
            (
                protocol_eligible
                & intrinsic_present
                & ~intrinsic_eligible
                & merged["intrinsic_exclusion_reason"].isna()
            ).sum()
        )
        count_assertion_passed = expected_protocol_eligible == (
            final_trainable_count + intrinsic_excluded + blocked_by_label_state + feature_blocked
        )
        validation_rows.append(
            {
                "feature_view_id": feature_view_id,
                "feature_source_view_id": feature_source_view_id,
                "label_task_id": label_task_id,
                "protocol_view_id": protocol_view_id,
                "feature_artifact_status": feature_artifact_status,
                "protocol_eligible_count": expected_protocol_eligible,
                "joined_label_count": joined_with_label,
                "joined_intrinsic_state_count": joined_with_intrinsic_state,
                "intrinsic_excluded_count": intrinsic_excluded,
                "blocked_by_label_state_count": blocked_by_label_state,
                "feature_blocked_count": feature_blocked,
                "final_trainable_count": final_trainable_count,
                "missing_label_count": missing_label_count,
                "missing_intrinsic_reason_count": missing_intrinsic_reason,
                "count_assertion_passed": count_assertion_passed,
            }
        )
        if missing_label_count > 0:
            raise ValueError(
                f"Protocol-eligible samples are missing label rows for feature_view_id={feature_view_id}, "
                f"label_task_id={label_task_id}, protocol_view_id={protocol_view_id}."
            )
        if joined_with_intrinsic_state != expected_protocol_eligible:
            raise ValueError(
                f"Protocol-eligible samples are missing intrinsic state for feature_view_id={feature_view_id}, "
                f"label_task_id={label_task_id}, protocol_view_id={protocol_view_id}."
            )
        if missing_intrinsic_reason > 0:
            raise ValueError(
                f"Intrinsic exclusions are missing reasons for feature_view_id={feature_view_id}, "
                f"label_task_id={label_task_id}, protocol_view_id={protocol_view_id}."
            )
        if feature_artifact_status == "resolved" and feature_blocked > 0:
            raise ValueError(
                f"Resolved feature artifact is missing protocol-trainable sample IDs for feature_view_id={feature_view_id}, "
                f"label_task_id={label_task_id}, protocol_view_id={protocol_view_id}."
            )
        if not count_assertion_passed:
            raise ValueError(
                f"Protocol eligibility does not reconcile with final trainability for feature_view_id={feature_view_id}, "
                f"label_task_id={label_task_id}, protocol_view_id={protocol_view_id}."
            )

    manifest_df = pd.DataFrame(rows).convert_dtypes()
    if not manifest_df.empty and manifest_df.duplicated(
        subset=["feature_view_id", "fold_id", "partition", "sample_id"],
        keep=False,
    ).any():
        duplicates = manifest_df.loc[
            manifest_df.duplicated(subset=["feature_view_id", "fold_id", "partition", "sample_id"], keep=False),
            ["feature_view_id", "fold_id", "partition", "sample_id"],
        ]
        raise ValueError(
            "Task training manifest has duplicate feature_view_id/fold_id/partition/sample_id rows: "
            f"{duplicates.to_dict(orient='records')}"
        )
    return manifest_df, pd.DataFrame(validation_rows).convert_dtypes()


def build_comparison_training_manifest(
    *,
    task_training_manifest: pd.DataFrame,
    cohort_manifests: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    validation_rows: list[dict[str, object]] = []
    for manifest_name, cohort_frame in cohort_manifests.items():
        if cohort_frame.empty:
            continue
        comparison_id = str(cohort_frame["comparison_id"].astype("string").dropna().iloc[0])
        feature_view_ids = COMPARISON_TO_FEATURE_VIEWS.get(comparison_id)
        if feature_view_ids is None:
            continue
        for feature_view_id, comparison_side in zip(feature_view_ids, ("left", "right"), strict=True):
            manifest_slice = task_training_manifest.loc[
                task_training_manifest["feature_view_id"].astype("string") == feature_view_id
            ].copy()
            joined = cohort_frame.merge(
                manifest_slice,
                left_on=["record_id", "fold_id", "partition"],
                right_on=["sample_id", "fold_id", "partition"],
                how="left",
                validate="one_to_one",
            )
            missing_count = int(joined["sample_id"].isna().sum())
            validation_rows.append(
                {
                    "comparison_id": comparison_id,
                    "feature_view_id": feature_view_id,
                    "comparison_side": comparison_side,
                    "matched_row_count": int(len(cohort_frame)),
                    "resolved_row_count": int(len(joined) - missing_count),
                    "missing_row_count": missing_count,
                    "count_assertion_passed": missing_count == 0,
                }
            )
            if missing_count > 0:
                raise ValueError(
                    f"Comparison manifest rows could not be resolved against task training manifest for "
                    f"{comparison_id} / {feature_view_id}."
                )
            for row in joined.to_dict(orient="records"):
                rows.append(
                    {
                        "comparison_id": comparison_id,
                        "comparison_side": comparison_side,
                        "matched_cohort_id": str(row.get("matched_cohort_id_x", row.get("matched_cohort_id", ""))),
                        "feature_view_id": feature_view_id,
                        "feature_source_view_id": row["feature_source_view_id"],
                        "label_task_id": row["label_task_id"],
                        "protocol_view_id": row["protocol_view_id"],
                        "fold_id": str(row["fold_id"]),
                        "partition": str(row["partition"]),
                        "sample_id": str(row["sample_id"]),
                        "record_id_order": int(row["record_id_order"]),
                        "record_set_hash": str(row["record_set_hash"]),
                        "label_name": row["label_name"],
                        "label_status": row["label_status"],
                        "intrinsic_eligibility": row["intrinsic_eligibility"],
                        "protocol_eligibility": row["protocol_eligibility"],
                        "feature_artifact_ready": row["feature_artifact_ready"],
                        "feature_join_ready": row["feature_join_ready"],
                        "final_trainability": row["final_trainability"],
                        "feature_artifact_path": row["feature_artifact_path"],
                        "feature_artifact_hash": row["feature_artifact_hash"],
                        "feature_schema_hash": row["feature_schema_hash"],
                        "feature_columns_hash": row["feature_columns_hash"],
                        "feature_generator_config_hash": row["feature_generator_config_hash"],
                        "feature_generator_code_commit": row["feature_generator_code_commit"],
                        "source_canonical_hash": row["source_canonical_hash"],
                        "sample_id_hash": row["sample_id_hash"],
                    }
                )
    comparison_df = pd.DataFrame(rows).convert_dtypes()
    if not comparison_df.empty and comparison_df.duplicated(
        subset=["comparison_id", "feature_view_id", "fold_id", "partition", "sample_id"],
        keep=False,
    ).any():
        duplicates = comparison_df.loc[
            comparison_df.duplicated(
                subset=["comparison_id", "feature_view_id", "fold_id", "partition", "sample_id"],
                keep=False,
            ),
            ["comparison_id", "feature_view_id", "fold_id", "partition", "sample_id"],
        ]
        raise ValueError(
            "Comparison training manifest has duplicate comparison_id/feature_view_id/fold_id/partition/sample_id rows: "
            f"{duplicates.to_dict(orient='records')}"
        )
    return comparison_df, pd.DataFrame(validation_rows).convert_dtypes()


def _assert_unique_label_keys(frames: dict[str, pd.DataFrame]) -> None:
    for artifact_name, frame in frames.items():
        if "sample_id" not in frame.columns or "label_task_id" not in frame.columns:
            continue
        duplicates = frame.loc[
            frame.duplicated(subset=["label_task_id", "sample_id"], keep=False),
            ["label_task_id", "sample_id"],
        ]
        if not duplicates.empty:
            raise ValueError(
                f"Label artifact is not unique on (label_task_id, sample_id) in {artifact_name}: "
                f"{duplicates.to_dict(orient='records')}"
            )


def _registry_row(
    *,
    spec: dict[str, object],
    weak_labels_run_dir: Path,
    dataset_views_run_dir: Path,
    split_artifact_path: Path,
    resolved_feature: ResolvedFeatureArtifact | None,
) -> dict[str, object]:
    feature_artifact_status = str(spec.get("feature_artifact_status", "resolved" if resolved_feature is not None else "missing"))
    scientific_blocker = str(spec.get("scientific_blocker", ""))
    row = {
        "experiment_id": str(spec["experiment_id"]),
        "feature_view_id": str(spec["feature_view_id"]),
        "feature_source_view_id": str(spec["feature_source_view_id"]),
        "label_task_id": str(spec["label_task_id"]),
        "protocol_view_id": str(spec["protocol_view_id"]),
        "sample_unit": str(spec["sample_unit"]),
        "feature_join_key": str(spec["feature_join_key"]),
        "label_join_key": str(spec["label_join_key"]),
        "label_artifact_path": str((weak_labels_run_dir / str(spec["label_relative_path"])).resolve()),
        "split_artifact_path": str(split_artifact_path.resolve()),
        "dataset_views_run_dir": str(dataset_views_run_dir.resolve()),
        "feature_artifact_status": feature_artifact_status,
        "scientific_blocker": scientific_blocker,
        "feature_artifact_ready": feature_artifact_status == "resolved",
        "feature_schema_ready": feature_artifact_status == "resolved",
        "feature_join_ready": feature_artifact_status == "resolved",
    }
    if resolved_feature is None:
        row.update(
            {
                "feature_artifact_path": pd.NA,
                "feature_artifact_hash": pd.NA,
                "feature_schema_path": pd.NA,
                "feature_schema_hash": pd.NA,
                "feature_columns_path": pd.NA,
                "feature_columns_hash": pd.NA,
                "feature_generator_config_hash": pd.NA,
                "feature_generator_code_commit": pd.NA,
                "source_canonical_hash": pd.NA,
                "materialization_config_hash": pd.NA,
                "row_index_path": pd.NA,
                "row_index_hash": pd.NA,
                "sample_id_hash": pd.NA,
                "row_count": pd.NA,
                "allowed_feature_columns_json": pd.NA,
                "identifier_columns_json": pd.NA,
                "audit_only_columns_json": pd.NA,
                "forbidden_columns_json": pd.NA,
            }
        )
        return row
    row.update(
        {
            "feature_artifact_path": str(resolved_feature.feature_artifact_path),
            "feature_artifact_hash": resolved_feature.feature_artifact_hash,
            "feature_schema_path": str(resolved_feature.feature_schema_path),
            "feature_schema_hash": resolved_feature.feature_schema_hash,
            "feature_columns_path": str(resolved_feature.feature_columns_path),
            "feature_columns_hash": resolved_feature.feature_columns_hash,
            "feature_generator_config_hash": resolved_feature.feature_generator_config_hash,
            "feature_generator_code_commit": resolved_feature.feature_generator_code_commit,
            "source_canonical_hash": resolved_feature.source_canonical_hash,
            "materialization_config_hash": resolved_feature.materialization_config_hash,
            "row_index_path": str(resolved_feature.row_index_path),
            "row_index_hash": resolved_feature.row_index_hash,
            "sample_id_hash": resolved_feature.sample_id_hash,
            "row_count": resolved_feature.row_count,
            "allowed_feature_columns_json": _json_list(resolved_feature.allowed_feature_columns),
            "identifier_columns_json": _json_list(resolved_feature.identifier_columns),
            "audit_only_columns_json": _json_list(resolved_feature.audit_only_columns),
            "forbidden_columns_json": _json_list(resolved_feature.forbidden_columns),
        }
    )
    return row


def _resolve_artifact(run_dir: Path, nested_relative: str, legacy_name: str) -> Path:
    nested = run_dir / nested_relative
    if nested.exists():
        return nested
    legacy = run_dir / legacy_name
    if legacy.exists():
        return legacy
    raise FileNotFoundError(f"Unable to resolve artifact {nested_relative} or legacy {legacy_name} under {run_dir}.")


def _build_matched_cohort_lookup(cohort_manifests: dict[str, pd.DataFrame]) -> dict[tuple[str, str, str, str, str], str]:
    lookup: dict[tuple[str, str, str, str, str], str] = {}
    for name, frame in cohort_manifests.items():
        if frame.empty:
            continue
        comparison_id = str(frame["comparison_id"].astype("string").dropna().iloc[0])
        feature_view_ids = COMPARISON_TO_FEATURE_VIEWS.get(comparison_id)
        if feature_view_ids is None:
            continue
        label_task_id = "v2_same_y_3h" if "3h" in comparison_id else "v2_same_y_8h"
        for feature_view_id in feature_view_ids:
            for row in frame.to_dict(orient="records"):
                lookup[
                    (
                        str(row["record_id"]),
                        feature_view_id,
                        label_task_id if feature_view_id.startswith("v2_same_y_") else ("v0_point_train" if feature_view_id == "v0_point" else "v1_point_train"),
                        str(row["fold_id"]),
                        str(row["partition"]),
                    )
                ] = str(row["matched_cohort_id"])
    return lookup


def _load_json_file(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _json_list(values: tuple[str, ...]) -> str:
    return json.dumps(list(values), ensure_ascii=True, separators=(",", ":"))
