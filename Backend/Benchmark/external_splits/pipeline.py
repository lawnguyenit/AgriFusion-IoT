from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .builder import assign_timestamp_blocks
from .contracts import ExternalSplitConfig, ExternalSplitResult


def build_external_timestamp_split(config: ExternalSplitConfig) -> ExternalSplitResult:
    canonical_path = config.canonical_path.resolve()
    frame = pd.read_parquet(
        canonical_path,
        columns=["sample_id", config.timestamp_column, *config.group_columns, *config.shared_timestamp_columns],
    )
    splits, summary = assign_timestamp_blocks(
        frame,
        timestamp_column=config.timestamp_column,
        train_ratio=config.train_ratio,
        validation_ratio=config.validation_ratio,
        test_ratio=config.test_ratio,
        shared_timestamp_columns=config.shared_timestamp_columns,
    )
    dataset_id = canonical_path.parent.parent.name
    run_id = f"external_splits_{dataset_id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    output_dir = (config.output_root / dataset_id / run_id).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    splits_path = output_dir / "timestamp_block_splits.parquet"
    splits.to_parquet(splits_path, index=False)
    manifest = {
        "schema_version": 1,
        "pipeline": "external_timestamp_splits",
        "run_id": run_id,
        "dataset_id": dataset_id,
        "canonical_path": str(canonical_path),
        "canonical_sha256": _sha256(canonical_path),
        "timestamp_column": config.timestamp_column,
        "group_columns": list(config.group_columns),
        "shared_timestamp_columns": list(config.shared_timestamp_columns),
        "row_count": len(splits),
        "split_sha256": _sha256(splits_path),
        "model_fit_performed": False,
        **summary,
    }
    manifest_path = output_dir / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path = output_dir / "report.md"
    lines = [
        f"# External timestamp split: {dataset_id}", "",
        f"- Policy: `{summary['policy_id']}`",
        f"- Assignment: {summary['assignment_unit']}",
        "- This is a chronological holdout; rows are never shuffled.",
        "", "| Partition | Rows | Unique timestamps | First UTC | Last UTC |",
        "|---|---:|---:|---|---|",
    ]
    for name, item in summary["partition_summary"].items():
        lines.append(f"| {name} | {item['rows']} | {item['unique_timestamps']} | {item['start']} | {item['end']} |")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ExternalSplitResult(run_id, output_dir, splits_path, len(splits), len(splits["timestamp_block_id"].unique()))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
