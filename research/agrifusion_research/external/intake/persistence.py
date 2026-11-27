from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .sources import DATASET_METADATA, SOURCE_FILES, sha256_bytes


def make_run_id(dataset_id: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"external_intake_{dataset_id}_{stamp}"


def prepare_raw_release(
    *,
    dataset_id: str,
    raw_root: Path,
    input_dir: Path | None,
    download: bool,
    release_id: str | None,
) -> tuple[Path, list[dict[str, str]]]:
    source_specs = SOURCE_FILES[dataset_id]
    release = release_id or datetime.now(timezone.utc).strftime("snapshot_%Y%m%dT%H%M%SZ")
    if Path(release).name != release or release in {"", ".", ".."}:
        raise ValueError("release_id must be one safe folder name.")
    raw_dir = (raw_root / dataset_id / release).resolve()
    payloads: list[tuple[object, bytes, str]] = []
    for source in source_specs:
        if download:
            from .sources import download_bytes

            payload = download_bytes(source.url)
            origin = source.url
        else:
            if input_dir is None:
                raise ValueError("Provide --input-dir or explicitly select --download.")
            supplied = input_dir.resolve() / source.name
            if not supplied.is_file():
                raise FileNotFoundError(f"Required source file is missing: {supplied}")
            payload = supplied.read_bytes()
            origin = str(supplied)
        payloads.append((source, payload, origin))

    raw_dir.mkdir(parents=True, exist_ok=False)
    file_records: list[dict[str, str]] = []
    for source, payload, origin in payloads:
        target = raw_dir / source.name
        target.write_bytes(payload)
        file_records.append(
            {
                "name": source.name,
                "origin_kind": "download" if download else "local_copy",
                "origin_locator": origin,
                "declared_upstream_url": source.url,
                "relative_path": source.name,
                "sha256": sha256_bytes(payload),
                "size_bytes": str(len(payload)),
            }
        )
    raw_manifest = {
        "schema_version": 1,
        "dataset_id": dataset_id,
        "release_id": release,
        "dataset_metadata": DATASET_METADATA[dataset_id],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_files": file_records,
    }
    (raw_dir / "raw_manifest.json").write_text(
        json.dumps(raw_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return raw_dir, file_records


def write_run_artifacts(
    *,
    output_dir: Path,
    canonical,
    excluded,
    manifest: dict[str, object],
    report: str,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=False)
    canonical_path = output_dir / "canonical.parquet"
    manifest_path = output_dir / "run_manifest.json"
    canonical.to_parquet(canonical_path, index=False)
    if not excluded.empty:
        excluded.to_csv(output_dir / "excluded_rows.csv", index=False)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "report.md").write_text(report, encoding="utf-8")
    artifact_rows = []
    for path in sorted(output_dir.iterdir()):
        if path.is_file() and path.name != "artifact_catalog.json":
            artifact_rows.append(
                {
                    "path": path.name,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "size_bytes": path.stat().st_size,
                }
            )
    (output_dir / "artifact_catalog.json").write_text(
        json.dumps(artifact_rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return canonical_path, manifest_path
