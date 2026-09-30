from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_run_id(dataset_id: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"external_labels_{dataset_id}_{stamp}"


def write_label_artifacts(
    *,
    output_dir: Path,
    labels: pd.DataFrame,
    registry: pd.DataFrame,
    cadence_registry: pd.DataFrame,
    support_audit: pd.DataFrame,
    manifest: dict[str, object],
) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=False)
    paths = {
        "candidate_labels": output_dir / "candidate_labels.parquet",
        "candidate_registry": output_dir / "candidate_registry.csv",
        "entity_persistence_registry": output_dir / "entity_persistence_registry.csv",
        "candidate_support_audit": output_dir / "candidate_support_audit.csv",
    }
    labels.to_parquet(paths["candidate_labels"], index=False)
    registry.to_csv(paths["candidate_registry"], index=False)
    cadence_registry.to_csv(paths["entity_persistence_registry"], index=False)
    support_audit.to_csv(paths["candidate_support_audit"], index=False)
    manifest["artifacts"] = {
        name: {"path": str(path.resolve()), "sha256": sha256_file(path), "size_bytes": path.stat().st_size}
        for name, path in paths.items()
    }
    manifest_path = output_dir / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path = output_dir / "report.md"
    report_path.write_text(_render_report(manifest, registry, support_audit), encoding="utf-8")
    catalog = [
        {"path": path.name, "sha256": sha256_file(path), "size_bytes": path.stat().st_size}
        for path in (*paths.values(), manifest_path, report_path)
    ]
    (output_dir / "artifact_catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return paths["candidate_labels"], paths["candidate_registry"], paths["candidate_support_audit"]


def _render_report(manifest: dict[str, object], registry: pd.DataFrame, support: pd.DataFrame) -> str:
    lines = [
        f"# External label candidates: {manifest['dataset_id']}",
        "",
        f"- Run: `{manifest['run_id']}`",
        f"- Intake run: `{manifest['intake_run_id']}`",
        f"- Canonical SHA-256: `{manifest['canonical_sha256']}`",
        f"- Calibration interval: `{manifest['calibration']['calibration_start']}` to `< {manifest['calibration']['calibration_end_exclusive']}`",
        f"- Observed source end: `{manifest['calibration']['observed_data_end']}`",
        f"- Candidate target/q/tau combinations: {len(registry)}",
        "- Primary candidate selected: no",
        "",
        "## Candidate support",
        "",
        "| Target | q | τ (min) | Entity | All + | All − | All unknown | Cal + | Post-cal + | Events |",
        "|---|---:|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    keys = ["target_id", "q_id", "tau_minutes", "entity_id"]
    indexed = support.set_index([*keys, "scope"])
    for row in support.loc[support["scope"].eq("ALL")].itertuples(index=False):
        key = tuple(getattr(row, column) for column in keys)
        calibration = indexed.loc[(*key, "CALIBRATION")]
        post_calibration = indexed.loc[(*key, "POST_CALIBRATION")]
        lines.append(
            f"| {row.target_id} | {row.tail_share:.0%} | {row.tau_minutes} | {row.entity_id} "
            f"| {row.positive_count} | {row.negative_count} | {row.unknown_count} "
            f"| {calibration.positive_count} | {post_calibration.positive_count} | {row.positive_event_count} |"
        )
    lines.extend(
        [
            "",
            "Positive labels require a qualifying tail run to reach the cadence-mapped K. "
            "A current tail observation without enough continuous history is UNRES; missing target values are also UNRES. "
            "UCI REF is emitted only when both CO and NOx candidate labels are known negative.",
            "",
            "Support is reported for the whole source, the calibration interval, and the post-calibration interval. "
            "All rows are sensitivity candidates. Review `candidate_support_audit.csv` before selecting a primary target contract.",
            "",
        ]
    )
    return "\n".join(lines)
