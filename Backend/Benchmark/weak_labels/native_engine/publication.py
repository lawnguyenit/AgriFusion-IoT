from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pandas as pd

from Backend.Benchmark.common.digests import file_sha256


def create_staging_directory(output_root: Path, run_id: str) -> Path:
    output_root = output_root.resolve()
    staging_root = output_root / ".staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    staging_dir = staging_root / run_id
    if staging_dir.exists():
        raise FileExistsError(staging_dir)
    staging_dir.mkdir(parents=True)
    return staging_dir


def publish_staging_directory(staging_dir: Path, final_dir: Path, manifest_path: Path) -> Path:
    staging_dir = staging_dir.resolve()
    final_dir = final_dir.resolve()
    if staging_dir.parent.parent != final_dir.parent:
        raise ValueError("Staging and final native-engine directories must share the same output root/filesystem.")
    if final_dir.exists():
        raise FileExistsError(final_dir)
    os.replace(staging_dir, final_dir)
    final_manifest = final_dir / manifest_path.relative_to(staging_dir)
    if not final_manifest.exists():
        raise RuntimeError("Final native-engine manifest was not found after atomic rename.")
    payload = json.loads(final_manifest.read_text(encoding="utf-8"))
    payload["publication_reverified_manifest_hash"] = file_sha256(final_manifest)
    marker = final_dir / "publication_success_marker.json"
    marker.write_text(json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2), encoding="utf-8")
    return final_dir


def write_artifact_catalog(run_dir: Path) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file() or path.name == "artifact_catalog.csv":
            continue
        rows.append({"artifact_path": str(path.relative_to(run_dir)), "sha256": file_sha256(path), "size_bytes": path.stat().st_size})
    catalog = pd.DataFrame(rows).convert_dtypes()
    catalog.to_csv(run_dir / "artifact_catalog.csv", index=False)
    return catalog


def copy_registry_with_native_stage(parent_registry_dir: Path, target_registry_dir: Path, native_run_dir: Path) -> Path:
    parent_registry_dir = parent_registry_dir.resolve()
    target_registry_dir = target_registry_dir.resolve()
    if target_registry_dir.exists():
        raise FileExistsError(target_registry_dir)
    shutil.copytree(parent_registry_dir, target_registry_dir)
    manifest_path = target_registry_dir / "run_metadata" / "run_manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    native_manifest = json.loads((native_run_dir / "run_metadata" / "run_manifest.json").read_text(encoding="utf-8"))
    payload.update(
        {
            "run_id": target_registry_dir.name,
            "current_stage": "NATIVE_ENGINE_IMPLEMENTED",
            "phase_a_only": False,
            "semantic_contract_frozen": True,
            "native_engine_implemented": True,
            "benchmark_release_published": False,
            "downstream_runners_unlocked": False,
            "native_engine_run_dir": str(native_run_dir),
            "native_engine_run_hash": native_manifest["native_engine_run_hash"],
            "parent_registry_run_dir": str(parent_registry_dir),
        }
    )
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2), encoding="utf-8")
    return target_registry_dir

