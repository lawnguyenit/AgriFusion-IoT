from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from .contracts import ExternalLabelConfig
from .pipeline import run_external_label_candidates


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate auditable q/tau label candidates for an external dataset.")
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--intake-manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--calibration-days", type=int, default=21)
    parser.add_argument("--tail-shares", nargs="+", type=float, default=[0.05, 0.10, 0.15, 0.20])
    parser.add_argument(
        "--tau-minutes",
        nargs="+",
        type=int,
        default=None,
        help="Persistence candidates in minutes; defaults to the dataset profile's evidence-based values.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = run_external_label_candidates(
        ExternalLabelConfig(
            canonical_path=args.canonical,
            intake_manifest_path=args.intake_manifest,
            output_root=args.output_root,
            calibration_days=args.calibration_days,
            tail_shares=tuple(args.tail_shares),
            tau_minutes=tuple(args.tau_minutes) if args.tau_minutes is not None else None,
        )
    )
    print(json.dumps({
        "dataset_id": result.dataset_id,
        "run_id": result.run_id,
        "output_dir": str(result.output_dir),
        "candidate_labels": str(result.candidate_labels_path),
        "registry": str(result.registry_path),
        "support_audit": str(result.support_audit_path),
        "rows": result.row_count,
        "candidate_count": result.candidate_count,
    }, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
