from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .pipeline import run_external_support_audit
from .sensitivity import summarize_continuity_sensitivity


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh support summaries from existing Stuard V3 label runs without regenerating labels.")
    parser.add_argument("--previous-manifest", type=Path, required=True)
    parser.add_argument("--splits", type=Path, required=True)
    parser.add_argument("--support-output-root", type=Path, required=True)
    parser.add_argument("--summary-csv", type=Path, required=True)
    args = parser.parse_args()

    previous = json.loads(args.previous_manifest.read_text(encoding="utf-8"))
    splits_path = args.splits.resolve()
    runs: list[tuple[float, Path]] = []
    records: list[dict[str, object]] = []
    for prior in previous["runs"]:
        label_dir = Path(prior["label_run_dir"])
        label_manifest = label_dir / "run_manifest.json"
        _verify_hash(label_manifest, prior["label_manifest_sha256"])
        label_data = json.loads(label_manifest.read_text(encoding="utf-8"))
        artifacts = label_data["artifacts"]
        labels_path = Path(artifacts["candidate_labels"]["path"])
        registry_path = Path(artifacts["candidate_registry"]["path"])
        _verify_hash(labels_path, prior["candidate_labels_sha256"])
        support_dir = run_external_support_audit(
            labels_path=labels_path,
            registry_path=registry_path,
            splits_path=splits_path,
            output_root=args.support_output_root,
        )
        factor = float(prior["g_max_cadence_fraction"])
        runs.append((factor, support_dir))
        records.append({
            **{key: value for key, value in prior.items() if key not in {"support_run_id", "support_run_dir", "support_manifest_sha256"}},
            "supersedes_support_run_id": prior.get("support_run_id"),
            "support_run_id": support_dir.name,
            "support_run_dir": str(support_dir.resolve()),
            "support_manifest_sha256": _sha256(support_dir / "run_manifest.json"),
            "model_fit_performed": False,
        })

    result = summarize_continuity_sensitivity(
        runs,
        target_id="soil_moisture_low",
        tail_share=float(previous["tail_share"]),
        tau_minutes=int(previous["tau_minutes"]),
    )
    args.summary_csv.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.summary_csv, index=False)
    manifest = {
        **previous,
        "artifact_id": "stuard_continuity_support_sensitivity_v3_refreshed",
        "split_path": str(splits_path),
        "split_sha256": _sha256(splits_path),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "refresh_reason": "Regenerated B2 summaries using integer failing_partition_count schema; reused hash-verified V3 candidate labels and frozen split.",
        "model_fit_performed": False,
        "runs": records,
        "summary_csv": {
            "path": str(args.summary_csv.resolve()),
            "sha256": _sha256(args.summary_csv),
            "row_count": int(len(result)),
        },
    }
    manifest_path = args.summary_csv.with_name(args.summary_csv.stem + "_manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "summary_csv": str(args.summary_csv.resolve()),
        "manifest": str(manifest_path.resolve()),
        "rows": len(result),
        "support_run_ids": [path.name for _, path in runs],
    }, ensure_ascii=False, indent=2))


def _verify_hash(path: Path, expected: str) -> None:
    if not path.is_file() or _sha256(path) != expected:
        raise ValueError(f"Artifact is missing or checksum changed: {path}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
