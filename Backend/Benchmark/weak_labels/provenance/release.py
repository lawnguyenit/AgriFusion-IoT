"""Native label-release materialization and manifest helpers.

This module is deliberately independent of evaluation and of the historical
weak-label runtime.  It converts first-class Assignment/transfer rows into a
stable consumer contract without changing their semantic decisions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import pandas as pd

from Backend.Benchmark.common.digests import file_sha256


LABEL_RELEASE_SCHEMA_VERSION = "native.label-release.v1"


def materialize_label_release_frame(
    frame: pd.DataFrame,
    *,
    task_kind: str,
    task_id: str,
    horizon_id: str,
) -> pd.DataFrame:
    """Expose a consumer-facing label schema from Assignment lineage.

    The function only renames/copies already-resolved assignment values.  It
    never computes a threshold, resolver decision, or fold status.
    """

    required = {"sample_id", "semantic_contract_hash"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Native assignment frame is missing columns: {sorted(missing)}")
    result = frame.copy()
    if task_kind == "SAME_Y":
        # A Same-Y row is a transfer projection, so its native identity is
        # the transfer object rather than a second semantic Assignment.
        if "same_y_transfer_id" not in result.columns:
            raise ValueError("Same-Y transfer frame must contain same_y_transfer_id.")
        result["assignment_id"] = result["same_y_transfer_id"]
        if "transferred_label" not in result.columns:
            raise ValueError("Same-Y transfer frame must contain transferred_label.")
        result["label_name"] = result["transferred_label"]
        result["source_assignment_id"] = result["source_assignment_id"].astype("string")
        result["label_status"] = result["intrinsic_transfer_status"].map(
            lambda value: "LABELED" if str(value) == "ELIGIBLE" else "EXCLUDED_WINDOW"
        )
        result["intrinsic_eligibility"] = result["intrinsic_transfer_status"].astype("string").eq("ELIGIBLE")
    else:
        if "label" not in result.columns:
            raise ValueError("Point/Temporal assignment frame must contain label.")
        result["label_name"] = result["label"]
        result["label_status"] = result.get("train_inclusion_status", pd.Series("EXCLUDED", index=result.index)).map(
            lambda value: "LABELED" if str(value) == "INCLUDED" else "ABSTAIN_INSUFFICIENT_EVIDENCE"
        )
        result["intrinsic_eligibility"] = result.get(
            "semantic_assignment_admissible",
            result.get("train_inclusion_status", pd.Series("EXCLUDED", index=result.index)).astype("string").eq("INCLUDED"),
        ).fillna(False).astype("boolean")
        if "source_assignment_id" not in result.columns:
            result["source_assignment_id"] = pd.NA

    result["task_id"] = task_id
    result["label_task_id"] = task_id
    result["horizon_id"] = horizon_id
    result["label_release_schema_version"] = LABEL_RELEASE_SCHEMA_VERSION
    result["native_assignment_id"] = result["assignment_id"]
    return result.convert_dtypes()


def build_label_release_manifest(
    release_dir: Path,
    *,
    semantic_contract_id: str,
    semantic_contract_hash: str,
    operationalization_id: str,
    task_paths: Mapping[str, Path],
) -> dict[str, object]:
    """Build a hash-addressed manifest for native label consumers."""

    release_dir = release_dir.resolve()
    tasks: dict[str, dict[str, object]] = {}
    for task_id, path in sorted(task_paths.items()):
        path = path.resolve()
        if not path.exists():
            raise FileNotFoundError(path)
        tasks[task_id] = {
            "relative_path": str(path.relative_to(release_dir)).replace("\\", "/"),
            "sha256": file_sha256(path),
            "row_count": int(pd.read_parquet(path, columns=["sample_id"]).shape[0]),
        }
    return {
        "pipeline": "weak_labels_native_label_release",
        "schema_version": LABEL_RELEASE_SCHEMA_VERSION,
        "semantic_contract_id": semantic_contract_id,
        "semantic_contract_hash": semantic_contract_hash,
        "operationalization_id": operationalization_id,
        "tasks": tasks,
        "evaluation_consumption_allowed": True,
        "legacy_label_builder_allowed": False,
    }
