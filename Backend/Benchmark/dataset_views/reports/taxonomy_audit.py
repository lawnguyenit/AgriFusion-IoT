from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from Backend.Benchmark.dataset_views.configs import TAXONOMY_VERSION, taxonomy_entries
from Backend.Benchmark.dataset_views.validators import hash_dataframe_rows


AUDITED_LEGACY_VIEW_IDS: tuple[str, ...] = (
    "v0_minimal_sensor",
    "v1_full_sensor",
    "v6_proxy_reduced",
)


def find_latest_audited_legacy_run(artifacts_root: Path) -> Path:
    candidates: list[Path] = []
    if not artifacts_root.exists():
        raise FileNotFoundError(f"Dataset view artifacts root not found: {artifacts_root}")
    for child in artifacts_root.iterdir():
        if not child.is_dir():
            continue
        if all((child / "views" / view_id).exists() for view_id in AUDITED_LEGACY_VIEW_IDS) and (
            child / "shared" / "source_manifest.json"
        ).exists():
            candidates.append(child)
    if not candidates:
        raise FileNotFoundError(
            "No historical dataset_views run contains v0_minimal_sensor, v1_full_sensor, v6_proxy_reduced, and shared/source_manifest.json."
        )
    return sorted(candidates, key=lambda path: path.name)[-1]


def build_taxonomy_drift_audit_payload(audited_run_dir: Path) -> dict[str, Any]:
    current_views: dict[str, Any] = {}
    for view_id in AUDITED_LEGACY_VIEW_IDS:
        manifest = json.loads((audited_run_dir / "views" / view_id / "manifest.json").read_text(encoding="utf-8"))
        schema = json.loads((audited_run_dir / "views" / view_id / "schema.json").read_text(encoding="utf-8"))
        dataframe = pd.read_parquet(audited_run_dir / "views" / view_id / "X.parquet")
        current_views[view_id] = {
            "semantic_meaning": manifest.get("description", ""),
            "ordered_feature_list": manifest.get("ordered_feature_list", []),
            "feature_count": schema.get("feature_count"),
            "row_count": schema.get("row_count"),
            "x_data_hash": hash_dataframe_rows(dataframe),
        }

    v0_features = current_views["v0_minimal_sensor"]["ordered_feature_list"]
    v6_features = current_views["v6_proxy_reduced"]["ordered_feature_list"]
    v0_hash = current_views["v0_minimal_sensor"]["x_data_hash"]
    v6_hash = current_views["v6_proxy_reduced"]["x_data_hash"]

    return {
        "taxonomy_version": TAXONOMY_VERSION,
        "audited_run": {
            "run_id": audited_run_dir.name,
            "run_path": str(audited_run_dir.resolve()),
        },
        "current_views": current_views,
        "approved_taxonomy": [
            {
                "semantic_view_id": entry.semantic_view_id,
                "numeric_alias": entry.numeric_alias,
                "status": entry.status,
                "batch": entry.batch,
                "grain": entry.grain,
                "selection_kind": entry.selection_kind,
                "public_selectable": entry.public_selectable,
                "notes": entry.notes,
            }
            for entry in taxonomy_entries()
        ],
        "required_renames": [
            {
                "from": "v1_full_sensor",
                "to": "v1_sensor_row",
                "reason": "Current v1 mixes measurement features with diagnostics; approved v1 must be measurement-only.",
            },
            {
                "from": "v6_proxy_reduced",
                "to": None,
                "reason": "This historical proxy-reduced output has no current public replacement in the active scope.",
            },
        ],
        "outputs_retained_as_valid": ["v0_minimal_sensor"],
        "outputs_requiring_rebuild": ["v1_sensor_row"],
        "outputs_deprecated_or_draft": [
            {
                "view_id": "v1_full_sensor",
                "status": "HISTORICAL_DEPRECATED",
                "reason": "Diagnostic fields make it semantically inconsistent with approved v1_sensor_row.",
            },
            {
                "view_id": "v6_proxy_reduced",
                "status": "INVALID_INDEPENDENT_VIEW",
                "reason": "The historical v6 proxy-reduced output is outside the current public scope and has no current public replacement.",
            },
        ],
        "drift_findings": {
            "current_v1_contains_sensor_diagnostics": True,
            "current_v6_matches_v0_ordered_features": bool(v0_features == v6_features),
            "current_v6_matches_v0_x_hash": bool(v0_hash == v6_hash),
            "current_v6_candidate_universe_status": "incorrectly_defined",
        },
    }
