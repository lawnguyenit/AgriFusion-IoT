from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


def persist_inventory(
    inventory: pd.DataFrame,
    metadata: dict[str, Any],
    *,
    canonical_path: Path,
    manifest_path: Path,
    output_root: Path,
) -> Path:
    dataset_id = str(metadata["dataset_id"])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_id = f"claim_inventory_{dataset_id}_{stamp}"
    output_dir = output_root / dataset_id / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    metadata = {
        **metadata,
        "run_id": run_id,
        "canonical_path": str(canonical_path.resolve()),
        "canonical_sha256": _sha256(canonical_path),
        "intake_manifest_path": str(manifest_path.resolve()),
        "intake_manifest_sha256": _sha256(manifest_path),
    }
    inventory_path = output_dir / "evidence_inventory.csv"
    inventory.to_csv(inventory_path, index=False)
    (output_dir / "inventory_manifest.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "report.md").write_text(_render_report(inventory, metadata), encoding="utf-8")
    artifacts = []
    for path in sorted(output_dir.iterdir()):
        if path.is_file() and path.name != "artifact_catalog.json":
            artifacts.append({"path": path.name, "sha256": _sha256(path), "size_bytes": path.stat().st_size})
    (output_dir / "artifact_catalog.json").write_text(
        json.dumps(artifacts, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output_dir


def _render_report(inventory: pd.DataFrame, metadata: dict[str, Any]) -> str:
    lines = [
        f"# Claim evidence inventory: {metadata['dataset_id']}",
        "",
        f"- Rows: {metadata['row_count']}",
        f"- Candidate direct-measurement fields: {metadata['candidate_state_count']}",
        f"- Time coverage: {metadata['time_coverage_start']} to {metadata['time_coverage_end']}",
        f"- Entity count: {metadata['entity_count']}",
        f"- Median observed cadence (minutes): {metadata['cadence']['median_minutes']}",
        f"- Median per-entity cadence (minutes): {metadata['cadence'].get('median_entity_median_minutes', metadata['cadence']['median_minutes'])}",
        "- Semantic claims inferred automatically: **No**",
        "- Claim generation gate: **REVIEW_REQUIRED**",
        "",
        "Relative low/high state proposals describe a variable's distribution only. They do not establish a domain outcome or ground truth.",
        "Independent criteria and operational evidence remain separately inventoried and cannot silently become model targets.",
        "",
        "## Fields",
        "",
        "| Field | Role | Observed | Missing % | Range / q05–q95 | Claim status |",
        "|---|---|---:|---:|---|---|",
    ]
    for row in inventory.to_dict(orient="records"):
        span = f"{row['minimum']} / {row['q05']}–{row['q95']} / {row['maximum']}"
        lines.append(
            f"| `{row['field']}` | {row['role']} | {row['observed_count']} | "
            f"{row['missing_fraction']:.1%} | {span} | {row['candidate_status']} |"
        )
    lines.extend(["", "See `evidence_inventory.csv` for the assessment reason and detailed statistics for each field.", ""])
    return "\n".join(lines)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
