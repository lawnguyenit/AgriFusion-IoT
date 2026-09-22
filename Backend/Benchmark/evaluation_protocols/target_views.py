"""Build an additive protocol for paired temporal target views.

The builder starts from an already materialized protocol run and replaces only
the temporal target assignment.  Feature artifacts, row order, folds, and
partitions are inherited byte-for-byte by reference; the source protocol is
never modified.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from Backend.Benchmark.shared.artifacts import create_run_directory, write_json, write_text
from Backend.Benchmark.weak_labels.infrastructure.hashing import file_sha256
from Backend.Benchmark.weak_labels.analysis.temporal_target_views import (
    EVENT_UNDETERMINED,
    TARGET_VIEW_IDS,
    Y_EVENT,
    Y_ONLINE,
)


TEMPORAL_FEATURE_VIEW_IDS = ("v2_temporal_mini_3h", "v2_temporal_full_3h")


@dataclass(frozen=True)
class PairedTargetProtocolResult:
    run_id: str
    output_dir: Path
    task_row_count: int
    trainable_row_counts: dict[str, dict[str, int]]


def build_paired_target_view_protocol(
    *,
    base_protocol_run_dir: Path,
    target_views_artifact_dir: Path,
    output_root: Path,
    feature_view_ids: tuple[str, ...] = TEMPORAL_FEATURE_VIEW_IDS,
    target_view_ids: tuple[str, ...] = TARGET_VIEW_IDS,
) -> PairedTargetProtocolResult:
    base_protocol_run_dir = base_protocol_run_dir.resolve()
    target_views_artifact_dir = target_views_artifact_dir.resolve()
    base_runner = base_protocol_run_dir / "primary_protocol" / "runner"
    if not base_runner.is_dir():
        raise FileNotFoundError(f"Base protocol runner directory is missing: {base_runner}")
    for target_view_id in target_view_ids:
        target_path = target_views_artifact_dir / "targets" / target_view_id / "assignments.parquet"
        if not target_path.exists():
            raise FileNotFoundError(f"Target-view assignment is missing: {target_path}")

    base_registry = pd.read_csv(base_runner / "task_view_registry.csv").convert_dtypes()
    base_manifest = pd.read_parquet(base_runner / "task_training_manifest.parquet").convert_dtypes()
    selected_registry = base_registry.loc[
        base_registry["feature_view_id"].astype("string").isin(feature_view_ids)
    ].copy()
    selected_manifest = base_manifest.loc[
        base_manifest["feature_view_id"].astype("string").isin(feature_view_ids)
    ].copy()
    _assert_base_feature_alignment(selected_registry, selected_manifest, feature_view_ids)

    target_frames = {
        target_view_id: _load_target_frame(
            target_views_artifact_dir / "targets" / target_view_id / "assignments.parquet",
            target_view_id,
        )
        for target_view_id in target_view_ids
    }
    _assert_target_view_alignment(target_frames, target_view_ids)
    target_manifest_payload = json.loads(
        (target_views_artifact_dir / "run_metadata" / "run_manifest.json").read_text(encoding="utf-8")
    )
    native_release_dir = Path(str(target_manifest_payload["source_native_release_dir"])).resolve()
    horizon_id = str(target_manifest_payload.get("horizon_id", "3h"))
    oracle_artifact_path = native_release_dir / "tasks" / "temporal" / f"horizon_{horizon_id}" / "assignments.parquet"
    if not oracle_artifact_path.exists():
        raise FileNotFoundError(f"Native temporal oracle artifact is missing: {oracle_artifact_path}")

    run_id, output_dir = create_run_directory(
        output_root.resolve(), prefix="evaluation_protocols_target_views"
    )
    runner_dir = output_dir / "primary_protocol" / "runner"
    runner_dir.mkdir(parents=True, exist_ok=True)

    manifest_frames: list[pd.DataFrame] = []
    registry_frames: list[pd.DataFrame] = []
    trainable_counts: dict[str, dict[str, int]] = {}
    target_paths: dict[str, Path] = {}
    for target_view_id in target_view_ids:
        target_path = (target_views_artifact_dir / "targets" / target_view_id / "assignments.parquet").resolve()
        target_paths[target_view_id] = target_path
        target_hash = file_sha256(target_path)
        target_frame = target_frames[target_view_id]
        target_manifest = _replace_temporal_target(
            selected_manifest,
            target_frame,
            target_view_id=target_view_id,
            target_artifact_path=target_path,
            target_artifact_hash=target_hash,
        )
        manifest_frames.append(target_manifest)
        registry_frames.append(
            _build_target_registry(
                selected_registry,
                target_view_id=target_view_id,
                target_artifact_path=target_path,
                target_artifact_hash=target_hash,
                oracle_artifact_path=oracle_artifact_path,
            )
        )
        trainable_counts[target_view_id] = {
            partition: int(
                target_manifest.loc[
                    target_manifest["partition"].astype("string").eq(partition)
                    & target_manifest["final_trainability"].fillna(False).astype(bool)
                ].shape[0]
            )
            for partition in ("train", "validation", "test")
        }

    task_manifest = pd.concat(manifest_frames, ignore_index=True).convert_dtypes()
    task_registry = pd.concat(registry_frames, ignore_index=True).convert_dtypes()
    _assert_paired_protocol(task_manifest, task_registry, feature_view_ids, target_view_ids)

    task_manifest.to_parquet(runner_dir / "task_training_manifest.parquet", index=False)
    task_registry.to_csv(runner_dir / "task_view_registry.csv", index=False)
    _write_empty_compatibility_manifest(
        base_runner / "comparison_training_manifest.parquet",
        runner_dir / "comparison_training_manifest.parquet",
    )
    _write_empty_compatibility_manifest(
        base_runner / "frozen_target_manifest.parquet",
        runner_dir / "frozen_target_manifest.parquet",
    )

    runner_contract = _build_runner_contract(
        run_id=run_id,
        base_protocol_run_dir=base_protocol_run_dir,
        target_views_artifact_dir=target_views_artifact_dir,
        feature_view_ids=feature_view_ids,
        target_view_ids=target_view_ids,
        trainable_counts=trainable_counts,
    )
    write_json(runner_dir / "runner_contract.json", runner_contract)
    write_json(runner_dir / "runner_contract_v2.json", _build_runner_contract_v2(runner_contract))

    metadata_dir = output_dir / "run_metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "artifact_type": "PAIRED_TEMPORAL_TARGET_VIEW_PROTOCOL",
        "artifact_status": "DERIVED_ANALYSIS_ONLY",
        "authority_status": "CANDIDATE_REFERENCE_ONLY",
        "run_id": run_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_protocol_run_dir": str(base_protocol_run_dir),
        "base_protocol_runner_hashes": {
            name: file_sha256(base_runner / name)
            for name in (
                "task_view_registry.csv",
                "task_training_manifest.parquet",
                "comparison_training_manifest.parquet",
                "frozen_target_manifest.parquet",
            )
        },
        "target_views_artifact_dir": str(target_views_artifact_dir),
        "target_views_artifact_manifest_hash": file_sha256(
            target_views_artifact_dir / "run_metadata" / "run_manifest.json"
        ),
        "feature_view_ids": list(feature_view_ids),
        "target_view_ids": list(target_view_ids),
        "same_features_and_split": True,
        "future_used_for_features": False,
        "future_used_for_event_target_only": True,
        "native_protocol_mutated": False,
        "task_row_count": int(len(task_manifest)),
        "trainable_row_counts": trainable_counts,
        "target_artifacts": {
            target_view_id: {
                "path": str(path),
                "sha256": file_sha256(path),
            }
            for target_view_id, path in target_paths.items()
        },
        "output_files": {
            "task_registry": str(runner_dir / "task_view_registry.csv"),
            "task_manifest": str(runner_dir / "task_training_manifest.parquet"),
            "runner_contract": str(runner_dir / "runner_contract.json"),
        },
    }
    write_json(metadata_dir / "run_manifest.json", manifest)
    write_text(output_dir / "README.md", _build_readme(manifest))
    write_text(output_dir / "paired_target_protocol_report.md", _build_report(manifest))
    return PairedTargetProtocolResult(
        run_id=run_id,
        output_dir=output_dir,
        task_row_count=int(len(task_manifest)),
        trainable_row_counts=trainable_counts,
    )


def _load_target_frame(path: Path, target_view_id: str) -> pd.DataFrame:
    frame = pd.read_parquet(path).convert_dtypes()
    required = {
        "sample_id",
        "target_view_id",
        "label_name",
        "label_status",
        "intrinsic_eligibility",
        "target_pair_status",
        "target_semantics",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Target view {target_view_id} is missing columns: {sorted(missing)}")
    frame["sample_id"] = frame["sample_id"].astype("string")
    frame = frame.loc[frame["target_view_id"].astype("string").eq(target_view_id)].copy()
    if frame["sample_id"].duplicated(keep=False).any():
        raise ValueError(f"Target view {target_view_id} is not unique by sample_id.")
    return frame


def _assert_base_feature_alignment(
    registry: pd.DataFrame,
    manifest: pd.DataFrame,
    feature_view_ids: tuple[str, ...],
) -> None:
    if set(registry["feature_view_id"].astype("string")) != set(feature_view_ids):
        raise ValueError("Base protocol registry does not contain exactly the requested temporal feature views.")
    sample_sets = {
        feature_view_id: set(
            manifest.loc[
                manifest["feature_view_id"].astype("string").eq(feature_view_id), "sample_id"
            ].astype("string")
        )
        for feature_view_id in feature_view_ids
    }
    if any(not samples for samples in sample_sets.values()):
        raise ValueError(f"Base protocol has an empty temporal feature view: {sample_sets}")
    first = sample_sets[feature_view_ids[0]]
    if any(samples != first for samples in sample_sets.values()):
        raise ValueError("Temporal feature views do not share the same protocol sample universe.")


def _assert_target_view_alignment(target_frames: dict[str, pd.DataFrame], target_view_ids: tuple[str, ...]) -> None:
    sample_sets = {target: set(frame["sample_id"].astype("string")) for target, frame in target_frames.items()}
    first = sample_sets[target_view_ids[0]]
    if any(samples != first for samples in sample_sets.values()):
        raise ValueError("Paired target views do not share the same raw sample universe.")
    if any(
        (frame["target_pair_status"].astype("string") == "PAIRED").sum()
        != (target_frames[target_view_ids[0]]["target_pair_status"].astype("string") == "PAIRED").sum()
        for frame in target_frames.values()
    ):
        raise ValueError("Paired target views do not have the same paired-cohort count.")


def _replace_temporal_target(
    base_manifest: pd.DataFrame,
    target_frame: pd.DataFrame,
    *,
    target_view_id: str,
    target_artifact_path: Path,
    target_artifact_hash: str,
) -> pd.DataFrame:
    target_columns = [
        "sample_id",
        "label_name",
        "label_status",
        "intrinsic_eligibility",
        "target_pair_status",
        "target_semantics",
        "unres_origin",
        "support_depth_at_anchor",
        "eventual_run_length",
        "run_complete",
        "event_vs_online_changed",
        "event_label_name",
        "online_label_name",
        "origin_formula",
    ]
    target = target_frame.loc[:, [column for column in target_columns if column in target_frame.columns]].copy()
    target = target.rename(columns={column: f"target_{column}" for column in target.columns if column != "sample_id"})
    merged = base_manifest.merge(target, on="sample_id", how="left", validate="many_to_one")
    if merged["target_label_name"].isna().any():
        raise ValueError(f"Target view {target_view_id} does not cover every base protocol row.")
    result = merged.copy()
    result["target_view_id"] = target_view_id
    result["target_semantics"] = result["target_target_semantics"]
    result["label_task_id"] = target_view_id
    result["label_name"] = result["target_label_name"]
    result["label_status"] = result["target_label_status"]
    result["intrinsic_eligibility"] = result["target_intrinsic_eligibility"].fillna(False).astype(bool)
    paired = result["target_target_pair_status"].astype("string").eq("PAIRED")
    labeled = result["label_status"].astype("string").eq("LABELED")
    result["feature_join_ready"] = (
        result["feature_join_ready"].fillna(False).astype(bool) & paired & labeled & result["intrinsic_eligibility"]
    )
    result["final_trainability"] = (
        result["final_trainability"].fillna(False).astype(bool) & result["feature_join_ready"]
    )
    result["label_artifact_path"] = str(target_artifact_path)
    result["label_artifact_hash"] = target_artifact_hash
    result["source_task_id"] = "TEMPORAL_NATIVE_ONLINE"
    result["target_pair_status"] = result["target_target_pair_status"]
    for source_name, target_name in (
        ("target_unres_origin", "target_unres_origin"),
        ("target_support_depth_at_anchor", "target_support_depth_at_anchor"),
        ("target_eventual_run_length", "target_eventual_run_length"),
        ("target_run_complete", "target_run_complete"),
        ("target_event_vs_online_changed", "target_event_vs_online_changed"),
        ("target_event_label_name", "target_event_label_name"),
        ("target_online_label_name", "target_online_label_name"),
        ("target_origin_formula", "target_origin_formula"),
    ):
        if source_name in result.columns:
            result[target_name] = result[source_name]
    return result.convert_dtypes()


def _build_target_registry(
    base_registry: pd.DataFrame,
    *,
    target_view_id: str,
    target_artifact_path: Path,
    target_artifact_hash: str,
    oracle_artifact_path: Path,
) -> pd.DataFrame:
    result = base_registry.copy()
    result["experiment_id"] = result["feature_view_id"].astype("string") + "__" + target_view_id
    result["label_task_id"] = target_view_id
    result["target_view_id"] = target_view_id
    result["target_semantics"] = (
        "EVENT_RETROSPECTIVE" if target_view_id == Y_EVENT else "ONLINE_CAUSAL_CONFIRMATION"
    )
    result["label_artifact_path"] = str(target_artifact_path)
    result["label_artifact_hash"] = target_artifact_hash
    result["oracle_artifact_path"] = str(oracle_artifact_path)
    result["oracle_kind"] = (
        "RETROSPECTIVE_EVENT_RUN_LENGTH"
        if target_view_id == Y_EVENT
        else "CAUSAL_SUPPORT_DEPTH"
    )
    return result.convert_dtypes()


def _assert_paired_protocol(
    manifest: pd.DataFrame,
    registry: pd.DataFrame,
    feature_view_ids: tuple[str, ...],
    target_view_ids: tuple[str, ...],
) -> None:
    expected_registry_keys = {(feature, target) for feature in feature_view_ids for target in target_view_ids}
    actual_registry_keys = set(
        zip(
            registry["feature_view_id"].astype("string"),
            registry["target_view_id"].astype("string"),
            strict=False,
        )
    )
    if actual_registry_keys != expected_registry_keys:
        raise ValueError(f"Target registry keys mismatch: {actual_registry_keys} != {expected_registry_keys}")
    duplicate_keys = ["target_view_id", "feature_view_id", "fold_id", "partition", "sample_id"]
    if manifest.duplicated(duplicate_keys, keep=False).any():
        raise ValueError("Paired target protocol manifest has duplicate target/feature/sample rows.")
    for feature_view_id in feature_view_ids:
        sets = []
        for target_view_id in target_view_ids:
            frame = manifest.loc[
                manifest["feature_view_id"].astype("string").eq(feature_view_id)
                & manifest["target_view_id"].astype("string").eq(target_view_id)
                & manifest["final_trainability"].fillna(False).astype(bool)
            ]
            sets.append(set(frame["sample_id"].astype("string")))
        if sets[0] != sets[1]:
            raise ValueError(f"Target views have different trainable sample sets for {feature_view_id}.")
    if manifest["label_status"].astype("string").eq(EVENT_UNDETERMINED).any():
        raise ValueError("Event-undetermined rows must be represented as abstentions, not a model class.")


def _write_empty_compatibility_manifest(source_path: Path, destination_path: Path) -> None:
    source = pd.read_parquet(source_path)
    pd.DataFrame(columns=source.columns).convert_dtypes().to_parquet(destination_path, index=False)


def _build_runner_contract(
    *,
    run_id: str,
    base_protocol_run_dir: Path,
    target_views_artifact_dir: Path,
    feature_view_ids: tuple[str, ...],
    target_view_ids: tuple[str, ...],
    trainable_counts: dict[str, dict[str, int]],
) -> dict[str, object]:
    return {
        "protocol_id": "TEMPORAL_EVENT_ONLINE_PAIRED_V1",
        "protocol_version": "2026-09-02.target-views.v1",
        "derived_run_id": run_id,
        "derived_from_protocol_run_dir": str(base_protocol_run_dir),
        "target_views_artifact_dir": str(target_views_artifact_dir),
        "primary_feature_views": list(feature_view_ids),
        "target_view_ids": list(target_view_ids),
        "primary_fold_ids": ["fold_01"],
        "primary_partitions": ["train", "validation", "test"],
        "same_feature_artifacts": True,
        "same_split_assignments": True,
        "event_target_is_retrospective": True,
        "future_forbidden_in_features": True,
        "trainable_row_counts": trainable_counts,
    }


def _build_runner_contract_v2(contract: dict[str, object]) -> dict[str, object]:
    return {
        "contract_version": "runner_contract.target_views.v1",
        "target_dimension": {
            "field": "target_view_id",
            "values": contract["target_view_ids"],
            "paired_sample_key": ["feature_view_id", "fold_id", "partition", "sample_id"],
        },
        "lineage": {
            "same_feature_artifacts": True,
            "same_split_assignments": True,
            "future_forbidden_in_features": True,
        },
    }


def _build_readme(manifest: dict[str, object]) -> str:
    return f"""# Paired temporal target-view protocol

This is an additive protocol derived from `{Path(str(manifest['base_protocol_run_dir'])).name}`.
It preserves the base temporal feature artifacts, sample rows, folds, and
partitions.  The only changed dimension is `target_view_id`:

- `temporal_online_3h`: causal current-state target;
- `temporal_event_3h`: retrospective completed-run target.

The event target may use future run completion to define the target, but that
information is forbidden from model features.  The base protocol is not
mutated.  See `paired_target_protocol_report.md` and
`run_metadata/run_manifest.json`.
"""


def _build_report(manifest: dict[str, object]) -> str:
    counts = manifest["trainable_row_counts"]
    lines = [
        "# Paired temporal target-view protocol — report",
        "",
        "> Additive protocol. Same feature artifacts and split assignments; target view is the controlled change.",
        "",
        "## Contract",
        "",
        f"- Base protocol: `{Path(str(manifest['base_protocol_run_dir'])).name}`",
        f"- Feature views: `{', '.join(manifest['feature_view_ids'])}`",
        f"- Target views: `{', '.join(manifest['target_view_ids'])}`",
        "- Future information is allowed only in retrospective event-target construction.",
        "- Event-undetermined rows are abstentions and are not trainable.",
        "",
        "## Trainable rows",
        "",
        "| target_view_id | train | validation | test |",
        "| --- | ---: | ---: | ---: |",
    ]
    for target_view_id in manifest["target_view_ids"]:
        row = counts[target_view_id]
        lines.append(f"| {target_view_id} | {row['train']} | {row['validation']} | {row['test']} |")
    lines.extend(
        [
            "",
            "The model runner must include `target_view_id` in registry selection, output paths, predictions, and pooled metrics.",
        ]
    )
    return "\n".join(lines) + "\n"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
