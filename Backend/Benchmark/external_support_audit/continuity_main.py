from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from Backend.Benchmark.external_labels.contracts import ExternalLabelConfig
from Backend.Benchmark.external_labels.pipeline import run_external_label_candidates

from .pipeline import run_external_support_audit
from .sensitivity import summarize_continuity_sensitivity


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate V3 Stuard continuity support sensitivities on a frozen split.")
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--intake-manifest", type=Path, required=True)
    parser.add_argument("--splits", type=Path, required=True)
    parser.add_argument("--label-output-root", type=Path, required=True)
    parser.add_argument("--support-output-root", type=Path, required=True)
    parser.add_argument("--summary-csv", type=Path, required=True)
    parser.add_argument("--calibration-days", type=int, default=21)
    parser.add_argument("--tail-share", type=float, default=0.10)
    parser.add_argument("--tau-minutes", type=int, default=1440)
    parser.add_argument("--g-max", nargs="+", type=float, default=[1.5, 2.0, 3.0])
    args = parser.parse_args()
    runs: list[tuple[float, Path]] = []
    provenance: list[dict[str, object]] = []
    for factor in args.g_max:
        label_result = run_external_label_candidates(ExternalLabelConfig(
            canonical_path=args.canonical,
            intake_manifest_path=args.intake_manifest,
            output_root=args.label_output_root,
            calibration_days=args.calibration_days,
            tail_shares=(args.tail_share,),
            tau_minutes=(args.tau_minutes,),
            max_gap_cadence_fraction=factor,
        ))
        support_dir = run_external_support_audit(
            labels_path=label_result.candidate_labels_path,
            registry_path=label_result.registry_path,
            splits_path=args.splits,
            output_root=args.support_output_root,
        )
        runs.append((factor, support_dir))
        provenance.append({
            "g_max_cadence_fraction": factor,
            "label_run_id": label_result.run_id,
            "label_run_dir": str(label_result.output_dir.resolve()),
            "label_manifest_sha256": _sha256(label_result.output_dir / "run_manifest.json"),
            "candidate_labels_sha256": _sha256(label_result.candidate_labels_path),
            "support_run_id": support_dir.name,
            "support_run_dir": str(support_dir.resolve()),
            "support_manifest_sha256": _sha256(support_dir / "run_manifest.json"),
            "model_fit_performed": False,
        })
    result = summarize_continuity_sensitivity(
        runs,
        target_id="soil_moisture_low",
        tail_share=args.tail_share,
        tau_minutes=args.tau_minutes,
    )
    args.summary_csv.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.summary_csv, index=False)
    manifest = {
        "schema_version": 1,
        "artifact_id": "stuard_continuity_support_sensitivity_v3",
        "label_semantics": "observed tail below elapsed tau remains UNRES; negative only outside tail",
        "target": "per-line soil-moisture relative LOW",
        "calibration_days": args.calibration_days,
        "tail_share": args.tail_share,
        "tau_minutes": args.tau_minutes,
        "g_max_cadence_fractions": args.g_max,
        "split_path": str(args.splits.resolve()),
        "split_sha256": _sha256(args.splits),
        "model_fit_performed": False,
        "runs": provenance,
        "summary_csv": {
            "path": str(args.summary_csv.resolve()),
            "sha256": _sha256(args.summary_csv),
            "row_count": int(len(result)),
        },
    }
    manifest_path = args.summary_csv.with_name(args.summary_csv.stem + "_manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"summary_csv": str(args.summary_csv.resolve()), "manifest": str(manifest_path.resolve()), "rows": len(result)}, ensure_ascii=False))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
