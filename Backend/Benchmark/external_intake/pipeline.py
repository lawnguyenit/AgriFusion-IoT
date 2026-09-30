from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256

from .adapters.stuard import build_stuard_candidate
from .adapters.uci import build_uci_candidate
from .contracts import ExternalIntakeConfig, ExternalIntakeResult
from .persistence import make_run_id, prepare_raw_release, write_run_artifacts
from .sources import DATASET_METADATA, validate_dataset_id


def run_external_intake(config: ExternalIntakeConfig) -> ExternalIntakeResult:
    validate_dataset_id(config.dataset_id)
    raw_dir, source_files = prepare_raw_release(
        dataset_id=config.dataset_id,
        raw_root=config.raw_root,
        input_dir=config.input_dir,
        download=config.download,
        release_id=config.release_id,
    )
    raw_manifest_path = raw_dir / "raw_manifest.json"
    raw_manifest_hash = sha256(raw_manifest_path.read_bytes()).hexdigest()

    if config.dataset_id == "stuard_tomato_irrigation_2023":
        adapted = build_stuard_candidate(raw_dir)
        canonical, excluded, audit = adapted.canonical, adapted.excluded, adapted.audit
        roles = audit["feature_and_criterion_roles"]
    elif config.dataset_id == "uci_air_quality_360":
        canonical, excluded, audit = build_uci_candidate(raw_dir / "air+quality.zip")
        roles = audit["column_roles"]
    else:  # guarded by validate_dataset_id; kept explicit for a closed registry.
        raise ValueError(f"No adapter registered for {config.dataset_id!r}")

    run_id = make_run_id(config.dataset_id)
    output_dir = (config.processed_root / config.dataset_id / run_id).resolve()
    manifest = {
        "schema_version": 1,
        "pipeline": "external_intake",
        "run_id": run_id,
        "dataset_id": config.dataset_id,
        "dataset_metadata": DATASET_METADATA[config.dataset_id],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_release_dir": str(raw_dir),
        "raw_manifest_path": str(raw_manifest_path.resolve()),
        "raw_manifest_sha256": raw_manifest_hash,
        "source_files": source_files,
        "source_row_count": int(audit["raw_rows"] if "raw_rows" in audit else sum(audit["source_rows"].values())),
        "canonical_row_count": int(len(canonical)),
        "excluded_row_count": int(len(excluded)),
        "column_roles": roles,
        "adapter_audit": audit,
        "target_generation": "not_performed",
        "feature_materialization": "not_performed",
        "criterion_columns_must_not_enter_model_features": True,
    }
    report = _render_report(manifest)
    canonical_path, manifest_path = write_run_artifacts(
        output_dir=output_dir,
        canonical=canonical,
        excluded=excluded,
        manifest=manifest,
        report=report,
    )
    return ExternalIntakeResult(
        dataset_id=config.dataset_id,
        run_id=run_id,
        raw_dir=raw_dir,
        output_dir=output_dir,
        canonical_path=canonical_path,
        manifest_path=manifest_path,
        row_count=int(len(canonical)),
        excluded_row_count=int(len(excluded)),
    )


def _render_report(manifest: dict[str, object]) -> str:
    audit_json = json.dumps(manifest["adapter_audit"], ensure_ascii=False, indent=2)
    sources = manifest["source_files"]
    source_lines = [f"- `{row['name']}` — SHA-256 `{row['sha256']}`" for row in sources]
    return "\n".join(
        [
            f"# External intake: {manifest['dataset_id']}",
            "",
            f"- Run: `{manifest['run_id']}`",
            f"- Raw release: `{manifest['raw_release_dir']}`",
            f"- Source rows: {manifest['source_row_count']}",
            f"- Canonical rows: {manifest['canonical_row_count']}",
            f"- Excluded rows: {manifest['excluded_row_count']}",
            "",
            "## Source files",
            "",
            *source_lines,
            "",
            "## Adapter audit",
            "",
            "```json",
            audit_json,
            "```",
            "",
            "No labels, model features, splits, or predictions are created by intake.",
            "",
        ]
    )
