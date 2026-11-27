from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .inventory import build_evidence_inventory
from .persistence import persist_inventory


@dataclass(frozen=True)
class ClaimInventoryResult:
    dataset_id: str
    output_dir: Path
    row_count: int
    candidate_state_count: int


def run_claim_inventory(
    *,
    canonical_path: Path,
    manifest_path: Path,
    output_root: Path,
    min_observations: int = 100,
    dataset_id: str | None = None,
    feature_catalog_path: Path | None = None,
    timestamp_column: str | None = None,
    entity_column: str | None = None,
) -> ClaimInventoryResult:
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    frame = _read_canonical(canonical_path)
    feature_catalog = pd.read_csv(feature_catalog_path) if feature_catalog_path else None
    inventory, metadata = build_evidence_inventory(
        frame,
        manifest,
        min_observations=min_observations,
        dataset_id=dataset_id,
        feature_catalog=feature_catalog,
        timestamp_column=timestamp_column,
        entity_column=entity_column,
    )
    output_dir = persist_inventory(
        inventory,
        metadata,
        canonical_path=canonical_path,
        manifest_path=manifest_path,
        output_root=output_root,
    )
    return ClaimInventoryResult(
        dataset_id=str(metadata["dataset_id"]),
        output_dir=output_dir,
        row_count=int(len(frame)),
        candidate_state_count=int(metadata["candidate_state_count"]),
    )


def _read_canonical(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, low_memory=False)
    raise ValueError(f"Unsupported canonical format {path.suffix!r}; expected .parquet or .csv.")
